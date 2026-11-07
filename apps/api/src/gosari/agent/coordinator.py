"""조정자 — 요청 분류·조건 확인·허용 도구 계획·작업 상태 (SRS §4.1, §5.9).

공개 분석: 조건 확인 → 캐시 → 취득 → 품질 → 계산 → 근거 → (선택) LLM 설명 → 대조.
개인 검색은 로컬에서 실행하고 건수만 모델에 전달하며, 변경은 폼과 승인을 거친다.
"""

import hashlib
import json
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import timedelta
from typing import Any, Literal

from gosari.agent import build_public_spec, detect_out_of_scope, detect_personal_hint
from gosari.agent.analysis import AnalysisEngine
from gosari.agent.llm import LlmClient
from gosari.agent.public_planner import (
    is_price_question,
    outing_initial_values,
    price_initial_values,
    public_plan,
)
from gosari.cache.semantic import canonical_public_spec, lookup, store
from gosari.config import Settings, get_settings
from gosari.domain import CacheResolution, DataStatus, JobStage
from gosari.domain.envelope import PersonalSearchSelection, ProgressEvent, ResultEnvelope, UiSpec
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
        self.ui_spec: UiSpec | None = None
        self.ui_results: dict[str, ResultEnvelope] = {}
        self.personal_search: PersonalSearchSelection | None = None
        self.personal_form: Literal["notebook", "region_compare", "share"] | None = None
        self.private_tools_used = False
        self.link_tools_used = False
        self.conversation_id = "default"
        self.general_help = False
        self.dialogue_messages: list[dict[str, Any]] | None = None
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
            "ui_spec": self.ui_spec.model_dump(mode="json") if self.ui_spec else None,
            "ui_results": {
                ref: result.model_dump(mode="json") for ref, result in self.ui_results.items()
            },
            "personal_search": self.personal_search.model_dump() if self.personal_search else None,
            "personal_form": self.personal_form,
        }

    def emit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if event_type == "ui_spec":
            from gosari.agent.ui import restore_ui

            self.ui_spec, self.ui_results = restore_ui(payload.get("spec"), payload.get("results"))
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
        dialogue_messages: list[dict[str, Any]] | None = None,
    ) -> Job:
        if not self._admission.acquire(blocking=False):
            raise GosariError("LOCAL_BUSY", {"retry_after_seconds": 1})
        try:
            job, spec = self._new_job(session, spec_payload)
            job.conversation_id = conversation_id or "default"
            job.general_help = general_help
            job.dialogue_messages = dialogue_messages
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
        from gosari.agent.dialogue_privacy import contains_sensitive_dialogue

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
        if contains_sensitive_dialogue(text):
            return None, self.prepare(session, {**payload, "personal": True})
        context = self._public_contexts.get((session.session_id, conversation), {})
        previous = context.get("dialogue_messages", [])
        if not previous:
            history = payload.get("history")
            if isinstance(history, list):
                previous = [
                    {"role": message["role"], "content": message["content"]}
                    for message in history[-12:]
                    if isinstance(message, dict)
                    and message.get("role") in ("user", "assistant")
                    and isinstance(message.get("content"), str)
                    and 0 < len(message["content"]) <= self.settings.max_text_length
                    and not contains_sensitive_dialogue(message["content"])
                ]
        messages = [*previous, {"role": "user", "content": text}]
        return self.start_job(
            session,
            {"operation": "station_search", "source_ids": ["jeju_578"]},
            conversation_id=conversation,
            general_help=True,
            dialogue_messages=messages,
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
            from gosari.agent.ui import build_ui

            outputs: dict[str, ResultEnvelope] = {}
            facts: dict[str, dict[str, Any]] = {}
            for name, scope in scopes.items():
                call_id = new_id("tool")
                job.emit_event(
                    "tool_started",
                    {
                        "tool_call_id": call_id,
                        "name": name,
                        "label": LABELS.get(name, name),
                        "conditions": scope,
                    },
                )
                try:
                    output = execute(scope)
                except GosariError as error:
                    if len(scopes) == 1 or job.cancelled or error.code == "JOB_DEADLINE_EXCEEDED":
                        raise
                    checkpoint()
                    job.emit_event(
                        "tool_failed",
                        {
                            "tool_call_id": call_id,
                            "name": name,
                            "code": error.code,
                            "message": error.safe_message,
                        },
                    )
                    continue
                outputs[name] = output
                compact_result(output, facts)
                job.emit_event(
                    "tool_completed",
                    {
                        "tool_call_id": call_id,
                        "name": name,
                        "summary": LABELS.get(name, name),
                        "result": output.model_dump(mode="json"),
                    },
                )
            envelope = outputs.get(public["operation"]) or next(
                iter(outputs.values()),
                ResultEnvelope(request_id=job.request_id, data_status="unavailable"),
            )
            ui_spec, ui_results, source = build_ui(outputs, scopes)
            if ui_spec is not None:
                job.emit_event(
                    "ui_spec",
                    {
                        "spec": ui_spec.model_dump(mode="json"),
                        "results": {
                            ref: value.model_dump(mode="json") for ref, value in ui_results.items()
                        },
                        "selection_source": source,
                    },
                )
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
        key = (session.session_id, job.conversation_id)
        previous = self._public_contexts.get(key, {}).get("dialogue_messages", [])
        cursor = 0
        for message in previous:
            if message.get("role") != "tool":
                continue
            try:
                prior = json.loads(str(message.get("content") or "{}"))
                for fact_id in prior.get("facts", {}):
                    if re.fullmatch(r"f\d+", fact_id):
                        cursor = max(cursor, int(fact_id[1:]))
            except ValueError, TypeError, AttributeError:
                continue
        reference["facts"] = {
            f"f{cursor + index}": value for index, value in enumerate(facts.values(), start=1)
        }
        call_id = new_id("confirmed_tool")
        messages = [
            *previous,
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": spec["operation"],
                            "arguments": "{}",
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(
                    {**reference, "conditions": spec, "operation": spec["operation"]},
                    ensure_ascii=False,
                ),
            },
            {"role": "assistant", "content": job.assistant_text},
        ]
        self._public_contexts[(session.session_id, job.conversation_id)] = {
            "spec": {key: value for key, value in spec.items() if key != "contains_personal_hint"},
            "reference": reference,
            "dialogue_messages": self._recent_dialogue(messages),
        }
        if len(self._public_contexts) > self.settings.job_retention_limit:
            self._public_contexts.pop(next(iter(self._public_contexts)))

    def _restore_job_ui(
        self,
        job: Job,
        spec: dict[str, Any],
        envelope: ResultEnvelope,
        cached_answer: dict[str, Any] | None = None,
    ) -> None:
        from gosari.agent.ui import build_ui, restore_ui

        if job.general_help and job.dialogue_messages is None:
            return
        selection_source = "fallback"
        if cached_answer is not None:
            cached_spec, cached_results = restore_ui(
                cached_answer.get("ui_spec"), cached_answer.get("ui_results")
            )
            if cached_spec is not None:
                selection_source = "cache"
                job.ui_spec = cached_spec
                job.ui_results = {
                    ref: value.model_copy(update={"request_id": job.request_id}, deep=True)
                    for ref, value in cached_results.items()
                }
        if job.ui_spec is None:
            job.ui_spec, job.ui_results, _ = build_ui(
                {spec["operation"]: envelope}, {spec["operation"]: spec}
            )
        if job.ui_spec is not None:
            job.emit_event(
                "ui_spec",
                {
                    "spec": job.ui_spec.model_dump(mode="json"),
                    "results": {
                        ref: value.model_dump(mode="json") for ref, value in job.ui_results.items()
                    },
                    "selection_source": selection_source,
                },
            )

    def _run_admitted(self, session: Session, job: Job, spec: dict[str, Any]) -> None:
        try:
            if job.dialogue_messages is not None:
                self._execute_dialogue_job(session, job)
            else:
                self._execute_job(session, job, spec)
        finally:
            self._admission.release()

    def _publish_done(self, session: Session, job: Job) -> None:
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
                    "ui_spec": job.ui_spec.model_dump(mode="json") if job.ui_spec else None,
                    "ui_results": {
                        ref: value.model_dump(mode="json") for ref, value in job.ui_results.items()
                    },
                    "personal_search": job.personal_search.model_dump()
                    if job.personal_search
                    else None,
                    "personal_form": job.personal_form,
                },
            )
            if session.lifecycle == "active":
                session.jobs[job.job_id] = job.to_dict()
            else:
                self._jobs.pop(job.job_id, None)
                self._job_sessions.pop(job.job_id, None)

    @staticmethod
    def _recent_dialogue(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Cut at complete user-turn boundaries, preserving assistant/tool pairs.
        turns = [index for index, message in enumerate(messages) if message.get("role") == "user"]
        start = turns[-8] if len(turns) > 8 else 0
        return [dict(message) for message in messages[start:]]

    def _execute_dialogue_job(self, session: Session, job: Job) -> Job:
        from gosari.cache.public_source import (
            get_source_result,
            public_source_singleflight,
            put_source_result,
        )

        deadline = time.monotonic() + self.settings.job_deadline
        last_result: ResultEnvelope | None = None

        def checkpoint() -> None:
            if session.lifecycle != "active":
                job.cancelled = True
            if job.cancelled:
                raise GosariError("ACTION_NOT_ALLOWED", {"reason": "CANCELLED"})
            if time.monotonic() >= deadline:
                raise GosariError("JOB_DEADLINE_EXCEEDED")

        def execute(arguments: dict[str, Any]) -> ResultEnvelope:
            nonlocal last_result
            checkpoint()
            if arguments.get("operation") == "open_street_view":
                from gosari.agent.street_view import build_street_view_links
                from gosari.sources.locations import resolve_public_place

                identifier = arguments.get("location_id")
                if not isinstance(identifier, str):
                    raise GosariError("INVALID_INPUT")
                place = resolve_public_place(identifier)
                links = build_street_view_links(
                    {"id": place[0], "name": place[1], "latitude": place[2], "longitude": place[3]}
                )
                job.link_tools_used = True
                last_result = ResultEnvelope(
                    request_id=job.request_id,
                    data_status="complete",
                    source_mode="link",
                    requested_scope={"operation": "open_street_view", "location_id": place[0]},
                    result={"street_view_links": links},
                )
                return last_result
            if arguments.get("operation") == "search_personal_records":
                from gosari.personal.search import search_personal

                selection = PersonalSearchSelection.model_validate(
                    {"query": arguments.get("query", ""), "kind": arguments.get("kind"), "count": 0}
                )
                if len(selection.query) > self.settings.max_text_length:
                    raise GosariError("INVALID_INPUT")
                job.private_tools_used = True
                found = search_personal(session, selection.query, kind=selection.kind)
                job.personal_search = selection.model_copy(update={"count": len(found.items)})
                return ResultEnvelope(
                    request_id=job.request_id,
                    data_status="complete" if found.items else "no_data",
                    result={
                        "count": len(found.items),
                        "kinds": sorted({item.kind for item in found.items}),
                        "ui_query": selection.query,
                    },
                )
            if arguments.get("operation") == "open_personal_form":
                feature = arguments.get("feature")
                if feature not in ("notebook", "region_compare", "share"):
                    raise GosariError("INVALID_INPUT")
                job.private_tools_used = True
                job.personal_form = feature
                return ResultEnvelope(request_id=job.request_id, result={"feature": feature})
            public = build_public_spec(arguments)
            with public_source_singleflight(public, checkpoint=checkpoint):
                cached = get_source_result(public)
                if cached is not None:
                    result = ResultEnvelope.model_validate({**cached, "request_id": job.request_id})
                else:
                    result = AnalysisEngine(self.settings, checkpoint=checkpoint).run(
                        public, job.request_id
                    )
                    checkpoint()
                    put_source_result(public, result, ttl_seconds=300)
            last_result = result
            return result

        job.stage = JobStage.RUNNING
        job.emit("accepted", "요청을 받았습니다.")
        self.llm.begin_job()
        try:
            from gosari.agent.dialogue import run_dialogue
            from gosari.agent.dialogue_privacy import requires_private_dialogue
            from gosari.cache.dialogue_plan import read_plan, store_plan

            checkpoint()
            incoming = job.dialogue_messages or []
            fresh = len(incoming) == 1 and incoming[0].get("role") == "user"
            question = str(incoming[-1].get("content") or "") if incoming else ""
            cacheable_fresh = fresh and not requires_private_dialogue(question)

            def resolve() -> tuple[ResultEnvelope | None, str, list[dict[str, Any]]]:
                plan = read_plan(question, now=utcnow()) if cacheable_fresh else None
                cached = None
                resolution = CacheResolution.BYPASS
                if plan:
                    resolution, cached = lookup(
                        plan[0],
                        json.dumps(plan[0], ensure_ascii=False, sort_keys=True),
                        now=utcnow(),
                    )
                if cached is not None and plan:
                    from gosari.agent.runtime import compact_result

                    payload = cached["answer"]
                    envelope = ResultEnvelope.model_validate(
                        {
                            **payload,
                            "request_id": job.request_id,
                            "cache_resolution": resolution,
                            "evidence_ids": cached.get("evidence_ids", []),
                        }
                    )
                    answer = str(payload.get("assistant_text") or "")
                    self._restore_job_ui(job, plan[0], envelope, payload)
                    facts: dict[str, dict[str, Any]] = {}
                    reference = compact_result(envelope, facts)
                    call_id = new_id("cached_tool")
                    messages = [
                        *incoming,
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": call_id,
                                    "type": "function",
                                    "function": {"name": plan[0]["operation"], "arguments": "{}"},
                                }
                            ],
                        },
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": json.dumps(
                                {**reference, "conditions": plan[0]}, ensure_ascii=False
                            ),
                        },
                        {"role": "assistant", "content": answer},
                    ]
                    job.emit_event(
                        "assistant_completed",
                        {"text": answer, "replacement": True, "cache_hit": True},
                    )
                else:
                    envelope, answer, messages, specs = run_dialogue(
                        self.llm,
                        incoming,
                        execute,
                        job.emit_event,
                        checkpoint,
                        max_steps=self.settings.max_plan_steps,
                    )
                    checkpoint()
                    if (
                        cacheable_fresh
                        and not job.private_tools_used
                        and not job.link_tools_used
                        and envelope is not None
                        and len(specs) == 1
                    ):
                        spec = canonical_public_spec(specs[0])
                        payload = {
                            **envelope.model_dump(mode="json"),
                            "assistant_text": answer,
                            "ui_spec": job.ui_spec.model_dump(mode="json") if job.ui_spec else None,
                            "ui_results": {
                                ref: value.model_dump(mode="json")
                                for ref, value in job.ui_results.items()
                            },
                        }
                        valid_until = utcnow() + timedelta(
                            minutes=5
                            if spec["operation"] == "outing_compare"
                            else 15
                            if spec["operation"] in ("current_observation", "forecast_compare")
                            else 30
                        )
                        if store(
                            spec,
                            json.dumps(spec, ensure_ascii=False, sort_keys=True),
                            payload,
                            envelope.evidence_ids,
                            now=utcnow(),
                            valid_until=valid_until,
                        ):
                            store_plan(question, specs, now=utcnow(), valid_until=valid_until)
                return envelope, answer, messages

            from gosari.cache.semantic import response_cache_singleflight
            from gosari.sources.weather import korea_today

            normalized = unicodedata.normalize("NFC", question.strip())
            digest = hashlib.sha256(normalized.encode()).hexdigest()
            flight = (
                response_cache_singleflight(
                    {"operation": "station_search", "source_ids": ["jeju_578"]},
                    f"dialogue:{korea_today().isoformat()}:{digest}",
                    checkpoint=checkpoint,
                )
                if cacheable_fresh
                else nullcontext()
            )
            with flight:
                checkpoint()
                envelope, answer, messages = resolve()
            checkpoint()
            job.assistant_text = answer
            job.result = envelope or ResultEnvelope(request_id=job.request_id)
            self._public_contexts[(session.session_id, job.conversation_id)] = {
                "dialogue_messages": self._recent_dialogue(messages)
            }
            if len(self._public_contexts) > self.settings.job_retention_limit:
                self._public_contexts.pop(next(iter(self._public_contexts)))
            job.stage = JobStage.COMPLETED
            job.emit("result_ready", "결과가 준비되었습니다.")
        except GosariError as exc:
            job.stage = JobStage.CANCELLED if job.cancelled else JobStage.FAILED
            job.error = None if job.cancelled else exc.code
            if last_result is not None:
                job.result = last_result.model_copy(
                    update={"data_status": DataStatus.PARTIAL}, deep=True
                )
            job.emit(
                "cancelled" if job.cancelled else "failed",
                "취소되었습니다." if job.cancelled else exc.safe_message,
            )
        except Exception:
            job.stage = JobStage.FAILED
            job.error = "INTERNAL_ERROR"
            job.emit("failed", "작업을 완료하지 못했습니다.")
        self._publish_done(session, job)
        return job

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
                self._restore_job_ui(job, spec, envelope, answer)
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
                        self._restore_job_ui(job, spec, envelope, answer)
                        job.emit_event(
                            "assistant_completed",
                            {"text": job.assistant_text, "replacement": True, "cache_hit": True},
                        )
                    else:
                        envelope = self._execute_agent_turn(session, job, spec, checkpoint)
                        if job.ui_spec is None:
                            self._restore_job_ui(job, spec, envelope)
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
                                "ui_spec": job.ui_spec.model_dump(mode="json")
                                if job.ui_spec
                                else None,
                                "ui_results": {
                                    ref: value.model_dump(mode="json")
                                    for ref, value in job.ui_results.items()
                                },
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
        self._publish_done(session, job)
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
