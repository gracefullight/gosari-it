"""조정자 — 요청 분류·조건 확인·허용 도구 계획·작업 상태 (SRS §4.1, §5.9).

공개 분석: 조건 확인 → 캐시 → 취득 → 품질 → 계산 → 근거 → (선택) LLM 설명 → 대조.
개인 작업은 로컬 폼과 승인 프로토콜로만 처리하며 LLM 도구 목록에서 제외된다.
"""

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import timedelta
from typing import Any

from gosari.agent import build_public_spec, detect_out_of_scope, detect_personal_hint
from gosari.agent.analysis import AnalysisEngine
from gosari.agent.llm import LlmClient, explanation_matches, public_fact_summary
from gosari.agent.public_planner import public_plan
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
        }


class Coordinator:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.engine = AnalysisEngine(self.settings)
        self.llm = LlmClient(self.settings)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._job_sessions: dict[str, Session] = {}
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
        if local_plan is not None:
            spec = build_public_spec(local_plan)
            return {"classification": "public", "needs_confirmation": True, "spec": spec}
        if feature in ("market_query", "survey_link", "retail_lookup"):
            return {
                "classification": "public",
                "feature": "price",
                "needs_confirmation": True,
                "form": {
                    "questions": [
                        "도매·조사가·상품 중 어떤 가격을 볼까요? "
                        "생고사리 또는 건고사리도 선택해 주세요."
                    ],
                    "feature_hint": feature,
                },
            }
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

    def start_job(self, session: Session, spec_payload: dict[str, Any]) -> Job:
        if not self._admission.acquire(blocking=False):
            raise GosariError("LOCAL_BUSY", {"retry_after_seconds": 1})
        try:
            job, spec = self._new_job(session, spec_payload)
            self._executor.submit(self._run_admitted, session, job, spec)
        except Exception:
            self._admission.release()
            raise
        return job

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
            resolution, cached = lookup(spec, safe_text, now=utcnow())
            if cached is not None:
                answer = cached["answer"]
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
            else:
                checkpoint()
                if self.llm.available:
                    with suppress(GosariError):
                        public_conditions = {
                            key: value
                            for key, value in spec.items()
                            if key != "contains_personal_hint"
                        }
                        planned = build_public_spec(self.llm.structure_question(public_conditions))
                        if planned != public_conditions:
                            raise GosariError("MODEL_UNAVAILABLE")
                    checkpoint()
                engine = AnalysisEngine(self.settings, checkpoint=checkpoint)
                envelope = engine.run(spec, request_id)
                checkpoint()
                envelope.cache_resolution = resolution
                if (
                    self.llm.available
                    and envelope.data_status == "complete"
                    and public_fact_summary(envelope.result)
                ):
                    job.emit("calculated", "계산을 마쳤습니다.")
                    try:
                        explanation = self.llm.explain(envelope.model_dump(mode="json"))
                        if explanation_matches(explanation, envelope.result):
                            envelope.result["explanation"] = explanation
                            job.emit("explained", "결과를 정리했습니다.")
                        else:
                            envelope.warnings.append(
                                "설명을 작성하지 못했습니다. 표에서 결과를 확인하세요."
                            )
                    except GosariError:
                        envelope.warnings.append(
                            "설명을 작성하지 못했습니다. 표에서 결과를 확인하세요."
                        )
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
