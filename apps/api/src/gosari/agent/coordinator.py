"""조정자 — 요청 분류·조건 확인·허용 도구 계획·작업 상태 (SRS §4.1, §5.9).

공개 분석: 조건 확인 → 캐시 → 취득 → 품질 → 계산 → 근거 → (선택) LLM 설명 → 대조.
개인 작업은 로컬 폼과 승인 프로토콜로만 처리하며 LLM 도구 목록에서 제외된다.
"""

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

from gosari.agent import build_public_spec, detect_out_of_scope, detect_personal_hint
from gosari.agent.analysis import AnalysisEngine
from gosari.agent.llm import LlmClient
from gosari.agent.public_planner import (
    continue_public_price,
    is_price_question,
    outing_initial_values,
    price_initial_values,
    public_dialogue_intent,
    public_plan,
)
from gosari.cache.semantic import lookup, store
from gosari.config import Settings, get_settings
from gosari.domain import CacheResolution, JobStage
from gosari.domain.envelope import ProgressEvent, ResultEnvelope
from gosari.domain.errors import GosariError
from gosari.logging import get_logger
from gosari.personal.search import is_personal_search
from gosari.sessions import Session, new_id, utcnow

logger = get_logger(__name__)

FEATURE_HINTS = {
    "나들이": "outing",
    "준비": "outing",
    "주말": "outing",
    "날씨": "outing",
    "예보": "forecast_compare",
    "지역": "region_compare",
    "관측소": "station_search",
    "지도": "station_search",
    "비교": "history_compare",
    "수첩": "notebook",
    "기록": "notebook",
    "회고": "notebook",
    "나눔": "share",
    "나눌": "share",
    "봉지": "share",
    "가격": "market_query",
    "도매": "market_query",
    "조사가": "survey_link",
    "산림조합": "survey_link",
    "얼마": "market_query",
    "판매": "retail_lookup",
    "탐나오": "retail_lookup",
    "상품": "retail_lookup",
}


class Job:
    def __init__(self, job_id: str, request_id: str) -> None:
        self.job_id = job_id
        self.request_id = request_id
        self.stage = JobStage.CREATED
        self.events: list[ProgressEvent] = []
        self.result: ResultEnvelope | None = None
        self.error: str | None = None
        self.cancelled = False
        self.created_at = utcnow()
        self.model_usage: dict[str, Any] = {}
        self.assistant_text = ""
        self.conversation_id = "default"
        self.general_help = False
        self.public_intent: dict[str, Any] = {}
        self.extra_scopes: dict[str, dict[str, Any]] = {}

    def emit(
        self,
        stage: str,
        message: str,
        completed: int | None = None,
        total: int | None = None,
    ) -> None:
        self.events.append(
            ProgressEvent(
                event_id=new_id("evt"),
                job_id=self.job_id,
                stage=stage,
                timestamp=utcnow(),
                completed_units=completed,
                total_units=total,
                safe_message=message,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "request_id": self.request_id,
            "stage": self.stage.value,
            "created_at": self.created_at.isoformat(),
            "result": self.result.model_dump(mode="json") if self.result else None,
            "error": self.error,
            "events": [e.model_dump(mode="json") for e in self.events],
            "model_usage": self.model_usage,
            "assistant_text": self.assistant_text,
        }

    def emit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append(
            ProgressEvent(
                event_id=new_id("evt"),
                job_id=self.job_id,
                stage=self.stage.value,
                timestamp=utcnow(),
                event_type=event_type,
                payload=payload,
            )
        )


class Coordinator:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.engine = AnalysisEngine(self.settings)
        self.llm = LlmClient(self.settings)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._job_sessions: dict[str, Session] = {}
        self._public_contexts: dict[tuple[str, str], dict[str, Any]] = {}
        concurrency = max(1, self.settings.analysis_concurrency)
        self._admission = threading.BoundedSemaphore(
            concurrency + max(0, self.settings.analysis_queue_limit)
        )
        self._executor = ThreadPoolExecutor(
            max_workers=concurrency, thread_name_prefix="gosari-analysis"
        )

    def prepare(self, session: Session, payload: dict[str, Any]) -> dict[str, Any]:
        """공개/개인 분류와 조건 확인. 원천 호출·개인 변경 전 단계."""
        text = str(payload.get("text", ""))[: self.settings.max_text_length]
        if not text.strip() and not payload.get("spec"):
            raise GosariError("INVALID_INPUT")
        if is_personal_search(text):
            return {
                "classification": "personal",
                "feature": "personal_search",
                "needs_confirmation": False,
                "form": {"query": text},
            }
        if text.strip() and detect_out_of_scope(text):
            return {
                "classification": "public",
                "feature": "out_of_scope",
                "needs_confirmation": True,
                "form": {
                    "questions": [
                        "대신 지원되는 기상 관측·예보 비교나 "
                        "공영도매·상품 표시가 조사를 진행할까요?",
                    ],
                    "feature_hint": "outing",
                },
            }
        personal_hint = detect_personal_hint(text) or bool(payload.get("personal"))
        feature = None
        for hint, feat in FEATURE_HINTS.items():
            if hint in text:
                feature = feat
                break
        if personal_hint or feature in ("notebook", "share"):
            return {
                "classification": "personal",
                "feature": feature,
                "needs_confirmation": True,
                "form": {
                    "note": "아래 내용을 입력해 주세요.",
                    "fields": self._personal_form_fields(feature),
                },
            }
        if payload.get("spec"):
            spec = build_public_spec(payload["spec"])
            return {
                "classification": "public",
                "needs_confirmation": False,
                "spec": spec,
            }
        local_plan = public_plan(text)
        if is_price_question(text) or feature in ("market_query", "survey_link", "retail_lookup"):
            initial_values = price_initial_values(text)
            if local_plan is not None:
                spec = build_public_spec(local_plan)
                initial_values = {
                    key: value
                    for key, value in spec.items()
                    if key not in ("operation", "source_ids", "schema_version")
                }
                missing: list[str] = []
                if spec["operation"] == "market_query":
                    missing = [
                        field for field in ("settlement_date", "market_ids") if not spec.get(field)
                    ]
                if not missing:
                    return {
                        "classification": "public",
                        "feature": "price",
                        "needs_confirmation": False,
                        "spec": spec,
                    }
            else:
                missing = ["price_channel"]
                if "fresh_or_dried" not in initial_values:
                    missing.append("fresh_or_dried")
            questions = ["가격 종류와 고사리 종류를 선택해 주세요."]
            if initial_values.get("price_channel") == "wholesale":
                questions = ["도매 거래일과 시장을 선택해 주세요."]
            return {
                "classification": "public",
                "feature": "price",
                "needs_confirmation": True,
                "form": {
                    "kind": "price_conditions",
                    "inline": True,
                    "feature_hint": "price",
                    "questions": questions,
                    "missing_fields": missing,
                    "price_channels": [
                        {"value": "wholesale", "label": "도매"},
                        {"value": "survey", "label": "조사가"},
                        {"value": "retail", "label": "판매가"},
                    ],
                    "product_forms": [
                        {"value": "생고사리", "label": "생고사리"},
                        {"value": "건고사리", "label": "건고사리"},
                        {"value": "", "label": "모두"},
                    ],
                    "initial_values": initial_values,
                },
            }
        if local_plan is not None:
            spec = build_public_spec(local_plan)
            return {"classification": "public", "needs_confirmation": True, "spec": spec}
        if feature in ("outing", "forecast_compare") or (
            (
                any(word in text for word in ("오늘", "내일", "모레"))
                or re.search(r"\d{4}-\d{2}-\d{2}", text)
            )
            and any(word in text for word in ("날씨", "나들이", "예보", "비교"))
        ):
            return {
                "classification": "public",
                "feature": "outing",
                "needs_confirmation": True,
                "form": {
                    "questions": ["날짜·지역·정확한 시각(오전/오후)을 선택해 주세요."],
                    "feature_hint": "outing",
                    "initial_values": outing_initial_values(text),
                },
            }
        return {
            "classification": "public",
            "needs_confirmation": True,
            "form": {
                "questions": [
                    "어떤 지역의 관측을 비교할까요? (예: 선흘)",
                    "비교할 연도와 기간을 알려주세요. (예: 2023·2024년 4~5월)",
                ],
                "feature_hint": feature,
            },
        }

    def _personal_form_fields(self, feature: str | None) -> list[dict[str, str]]:
        if feature == "share":
            return [
                {"name": "recipient_alias", "label": "나눌 대상 별칭", "type": "text"},
                {"name": "amount_value", "label": "분량", "type": "number"},
                {"name": "amount_unit", "label": "단위 (봉지 등)", "type": "text"},
                {"name": "planned_delivery", "label": "전달 시점", "type": "text"},
            ]
        return [
            {"name": "experience_date", "label": "활동 날짜", "type": "date"},
            {"name": "activity_text", "label": "경험 내용", "type": "textarea"},
            {"name": "companion_aliases", "label": "동행 별칭", "type": "text"},
        ]

    def _new_job(
        self, session: Session, spec_payload: dict[str, Any]
    ) -> tuple[Job, dict[str, Any]]:
        spec = build_public_spec(spec_payload)
        job = Job(new_id("job"), new_id("req"))
        with self._lock:
            self._prune_jobs()
            session.jobs[job.job_id] = job.to_dict()
            self._jobs[job.job_id] = job
            self._job_sessions[job.job_id] = session
        return job, spec

    def _prune_jobs(self) -> None:
        for key, owner in list(self._job_sessions.items()):
            if owner.lifecycle != "active":
                self._jobs[key].cancelled = True
                self._jobs.pop(key, None)
                self._job_sessions.pop(key, None)
        terminal = [
            key
            for key, job in self._jobs.items()
            if job.stage
            in (JobStage.COMPLETED, JobStage.FAILED, JobStage.CANCELLED, JobStage.PARTIAL)
        ]
        excess = len(self._jobs) - max(1, self.settings.job_retention_limit) + 1
        for key in terminal[: max(0, excess)]:
            self._jobs.pop(key, None)
            owner = self._job_sessions.pop(key, None)
            if owner is not None:
                owner.jobs.pop(key, None)

    def start_job(
        self,
        session: Session,
        spec_payload: dict[str, Any],
        *,
        conversation_id: str | None = None,
        general_help: bool = False,
    ) -> Job:
        if not self._admission.acquire(blocking=False):
            raise GosariError("LOCAL_BUSY", {"retry_after_seconds": 1})
        try:
            job, spec = self._new_job(session, spec_payload)
            job.conversation_id = conversation_id or "default"
            job.general_help = general_help
            context = self._public_contexts.get((session.session_id, job.conversation_id), {})
            job.extra_scopes = {
                name: scope
                for name, scope in context.get("pending_scopes", {}).items()
                if name != spec["operation"]
            }
            self._executor.submit(self._run_admitted, session, job, spec)
        except Exception:
            self._admission.release()
            raise
        return job

    def start_chat(
        self, session: Session, payload: dict[str, Any]
    ) -> tuple[Job | None, dict[str, Any] | None]:
        text = payload.get("text")
        conversation = payload.get("conversation_id") or "default"
        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text) > self.settings.max_text_length
        ):
            raise GosariError("INVALID_INPUT")
        if not isinstance(conversation, str) or len(conversation) > 128:
            raise GosariError("INVALID_INPUT")
        context = self._public_contexts.get((session.session_id, conversation), {})
        private = detect_personal_hint(text) or is_personal_search(text)
        previous = context.get("spec", {})
        extras: dict[str, dict[str, Any]] = {}
        if not private and any(word in text for word in ("날씨", "기상", "기온", "강수")):
            if any(word in text for word in ("현재", "지금", "당일")):
                extras["current_observation"] = {
                    "operation": "current_observation",
                    "source_ids": ["kma_aws"],
                }
            for clause in re.split(r"그리고|하고|및", text):
                weather = public_plan(clause)
                if weather and weather["operation"] in (
                    "outing_compare",
                    "history_compare",
                    "forecast_compare",
                ):
                    extras[weather["operation"]] = build_public_spec(weather)
        context = {**context, "pending_scopes": extras, "request": public_dialogue_intent(text)}
        self._public_contexts[(session.session_id, conversation)] = context
        continuation = (
            None if private or detect_out_of_scope(text) else continue_public_price(previous, text)
        )
        if continuation is not None and (
            not is_price_question(text)
            or any(word in text for word in ("그럼", "그러면", "이번엔", "다시"))
        ):
            preparation = {
                "classification": "public",
                "feature": "price",
                "needs_confirmation": False,
                "spec": build_public_spec(continuation),
            }
        else:
            preparation = self.prepare(session, payload)
        ready_spec = preparation.get("spec")
        local_plan = None if private else public_plan(text)
        if isinstance(ready_spec, dict) and (
            not preparation.get("needs_confirmation") or local_plan is not None
        ):
            return self.start_job(session, ready_spec, conversation_id=conversation), None
        if extras and not is_price_question(text) and not private:
            return self.start_job(
                session, next(iter(extras.values())), conversation_id=conversation
            ), None
        if context["request"]["intent"] == "preparation_help" and not private:
            preparation = {"classification": "public", "needs_confirmation": False}
        if (
            preparation.get("classification") == "personal"
            or preparation.get("feature") in ("price", "outing", "out_of_scope")
            or preparation.get("spec")
        ):
            return None, preparation
        return self.start_job(
            session,
            {"operation": "station_search", "source_ids": ["jeju_578"]},
            conversation_id=conversation,
            general_help=True,
        ), None

    def _execute_agent_turn(
        self, session: Session, job: Job, spec: dict[str, Any], checkpoint: Any
    ) -> ResultEnvelope:
        from gosari.agent.runtime import LABELS, compact_result, fallback, run_agent
        from gosari.cache.public_source import (
            get_source_result,
            public_source_singleflight,
            put_source_result,
        )

        def execute(public: dict[str, Any]) -> ResultEnvelope:
            with public_source_singleflight(public, checkpoint=checkpoint):
                cached_source = get_source_result(public)
                if cached_source is not None:
                    cached_source = {**cached_source, "request_id": job.request_id}
                    return ResultEnvelope.model_validate(cached_source)
                output = AnalysisEngine(self.settings, checkpoint=checkpoint).run(
                    public, job.request_id
                )
                checkpoint()
                put_source_result(public, output, ttl_seconds=300)
                return output

        public = {key: value for key, value in spec.items() if key != "contains_personal_hint"}
        scopes = {} if job.general_help else {public["operation"]: public, **job.extra_scopes}
        context = self._public_contexts.get((session.session_id, job.conversation_id), {})
        if self.llm.available:
            output, answer = run_agent(
                self.llm,
                scopes,
                execute,
                job.emit_event,
                checkpoint,
                max_steps=self.settings.max_plan_steps,
                public_context={
                    "request": context.get("request", {}),
                    "previous_result": context.get("reference", {}),
                },
            )
            envelope = output or ResultEnvelope(request_id=job.request_id)
        elif job.general_help:
            envelope = ResultEnvelope(request_id=job.request_id)
            answer = "날씨나 고사리 가격 중 무엇을 확인할까요?"
            job.emit_event("assistant_completed", {"text": answer, "replacement": True})
        else:
            name = public["operation"]
            call_id = new_id("tool")
            job.emit_event(
                "tool_started",
                {
                    "tool_call_id": call_id,
                    "name": name,
                    "label": LABELS.get(name, name),
                    "conditions": public,
                },
            )
            envelope = execute(public)
            job.emit_event(
                "tool_completed",
                {
                    "tool_call_id": call_id,
                    "name": name,
                    "summary": LABELS.get(name, name),
                    "result": envelope.model_dump(mode="json"),
                },
            )
            facts: dict[str, dict[str, Any]] = {}
            compact_result(envelope, facts)
            answer = fallback(facts)
            job.emit_event("assistant_completed", {"text": answer, "replacement": True})
        job.assistant_text = answer
        return envelope

    def _remember_public(
        self, session: Session, job: Job, spec: dict[str, Any], envelope: ResultEnvelope
    ) -> None:
        from gosari.agent.runtime import compact_result

        if job.general_help or session.lifecycle != "active":
            return
        facts: dict[str, dict[str, Any]] = {}
        reference = compact_result(envelope, facts)
        self._public_contexts[(session.session_id, job.conversation_id)] = {
            "spec": {key: value for key, value in spec.items() if key != "contains_personal_hint"},
            "reference": reference,
        }
        if len(self._public_contexts) > self.settings.job_retention_limit:
            self._public_contexts.pop(next(iter(self._public_contexts)))

    def _run_admitted(self, session: Session, job: Job, spec: dict[str, Any]) -> None:
        try:
            self._execute_job(session, job, spec)
        finally:
            self._admission.release()

    def run_job(self, session: Session, spec_payload: dict[str, Any]) -> Job:
        job, spec = self._new_job(session, spec_payload)
        self._execute_job(session, job, spec)
        return job

    def _execute_job(self, session: Session, job: Job, spec: dict[str, Any]) -> Job:
        request_id = job.request_id
        deadline = time.monotonic() + self.settings.job_deadline

        def checkpoint() -> None:
            if session.lifecycle != "active":
                job.cancelled = True
            if job.cancelled:
                raise GosariError("ACTION_NOT_ALLOWED", {"reason": "CANCELLED"})
            if time.monotonic() >= deadline:
                raise GosariError("JOB_DEADLINE_EXCEEDED")

        job.stage = JobStage.RUNNING
        job.emit("accepted", "요청을 받았습니다.")
        begin_usage = getattr(self.llm, "begin_job", None)
        if callable(begin_usage):
            begin_usage()
        try:
            checkpoint()
            safe_text = json.dumps(spec, ensure_ascii=False, sort_keys=True)
            spec["contains_personal_hint"] = False
            job.emit("cache_checked", "자료를 확인하고 있습니다.")
            resolution, cached = (
                (CacheResolution.BYPASS, None)
                if job.general_help or job.extra_scopes
                else lookup(spec, safe_text, now=utcnow())
            )
            if cached is not None:
                answer = cached["answer"]
                job.assistant_text = str(answer.get("assistant_text") or "")
                envelope = ResultEnvelope(
                    request_id=request_id,
                    data_status=answer.get("data_status"),
                    source_mode=answer.get("source_mode"),
                    cache_resolution=resolution,
                    result=answer.get("result", {}),
                    evidence_ids=cached.get("evidence_ids", []),
                    warnings=answer.get("warnings", []),
                    requested_scope=answer.get("requested_scope", {}),
                    effective_scope=answer.get("effective_scope", {}),
                    observed_period=answer.get("observed_period", {}),
                    fetched_at=answer.get("fetched_at"),
                    verified_on=answer.get("verified_on"),
                )
                job.emit_event(
                    "assistant_completed",
                    {"text": job.assistant_text, "replacement": True, "cache_hit": True},
                )
            else:
                checkpoint()
                from gosari.cache.semantic import response_cache_singleflight

                with response_cache_singleflight(spec, safe_text, checkpoint=checkpoint):
                    # Recheck inside the shared flight before any model request.
                    second_resolution, second_cached = (
                        (CacheResolution.BYPASS, None)
                        if job.general_help or job.extra_scopes
                        else lookup(spec, safe_text, now=utcnow())
                    )
                    if second_cached is not None:
                        answer = {
                            **second_cached["answer"],
                            "request_id": request_id,
                            "cache_resolution": second_resolution,
                            "evidence_ids": second_cached.get("evidence_ids", []),
                        }
                        job.assistant_text = str(answer.get("assistant_text") or "")
                        envelope = ResultEnvelope.model_validate(answer)
                        resolution = second_resolution
                        job.emit_event(
                            "assistant_completed",
                            {"text": job.assistant_text, "replacement": True, "cache_hit": True},
                        )
                    else:
                        envelope = self._execute_agent_turn(session, job, spec, checkpoint)
                    checkpoint()
                    envelope.cache_resolution = resolution
                    if resolution == CacheResolution.MISS:
                        store(
                            spec,
                            safe_text,
                            {
                                "data_status": envelope.data_status,
                                "source_mode": envelope.source_mode,
                                "result": envelope.result,
                                "warnings": envelope.warnings,
                                "requested_scope": envelope.requested_scope,
                                "effective_scope": envelope.effective_scope,
                                "observed_period": envelope.observed_period,
                                "fetched_at": envelope.fetched_at,
                                "verified_on": envelope.verified_on,
                                "assistant_text": job.assistant_text,
                            },
                            envelope.evidence_ids,
                            now=utcnow(),
                            valid_until=utcnow()
                            + timedelta(
                                minutes=5
                                if spec["operation"] == "outing_compare"
                                else 15
                                if spec["operation"] in ("current_observation", "forecast_compare")
                                else 60
                                if spec["operation"] in ("market_query", "retail_lookup")
                                else 1440
                            ),
                        )
            checkpoint()
            self._remember_public(session, job, spec, envelope)
            job.result = envelope
            job.stage = JobStage.COMPLETED
            job.emit("result_ready", "결과가 준비되었습니다.")
        except GosariError as exc:
            job.stage = JobStage.CANCELLED if job.cancelled else JobStage.FAILED
            job.error = None if job.cancelled else exc.code
            fetched_scope = exc.extra.get("fetched_scope", [])
            if fetched_scope:
                job.result = ResultEnvelope(
                    request_id=request_id,
                    data_status="partial",
                    source_mode="fetched",
                    requested_scope={"operation": spec["operation"]},
                    effective_scope={"completed_units": fetched_scope},
                    result={"completed_scope": fetched_scope, "cancelled": job.cancelled},
                )
                job.emit("scope_retained", "확인한 범위를 보관했습니다.", len(fetched_scope))
            job.emit(
                "cancelled" if job.cancelled else "failed",
                "취소되었습니다." if job.cancelled else exc.safe_message,
            )
        except Exception:
            job.stage = JobStage.FAILED
            job.error = "INTERNAL_ERROR"
            job.emit("failed", "작업을 완료하지 못했습니다.")
        with self._lock:
            usage_snapshot = getattr(self.llm, "usage_snapshot", None)
            if callable(usage_snapshot):
                job.model_usage = usage_snapshot()
            job.emit_event(
                "done",
                {
                    "stage": job.stage.value,
                    "result": job.result.model_dump(mode="json") if job.result else None,
                    "error": job.error,
                    "assistant_text": job.assistant_text,
                    "model_usage": job.model_usage,
                },
            )
            if session.lifecycle == "active":
                session.jobs[job.job_id] = job.to_dict()
            else:
                self._jobs.pop(job.job_id, None)
                self._job_sessions.pop(job.job_id, None)
        return job

    def get_job(self, session: Session, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None or job.job_id not in session.jobs:
            raise GosariError("RESOURCE_NOT_FOUND")
        return job

    def cancel_job(self, session: Session, job_id: str) -> Job:
        job = self.get_job(session, job_id)
        job.cancelled = True
        if job.stage in (JobStage.CREATED, JobStage.READY, JobStage.RUNNING):
            if job.stage != JobStage.RUNNING:
                job.stage = JobStage.CANCELLED
            job.emit(
                "cancel_requested",
                "취소를 요청했습니다.",
            )
        return job


_coordinator: Coordinator | None = None


def get_coordinator() -> Coordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = Coordinator()
    return _coordinator
