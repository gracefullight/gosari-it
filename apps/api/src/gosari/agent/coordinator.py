"""조정자 — 요청 분류·조건 확인·허용 도구 계획·작업 상태 (SRS §4.1, §5.9).

공개 분석: 조건 확인 → 캐시 → 취득 → 품질 → 계산 → 근거 → (선택) LLM 설명 → 대조.
개인 작업은 로컬 폼과 승인 프로토콜로만 처리하며 LLM 도구 목록에서 제외된다.
"""

import threading
from datetime import timedelta
from typing import Any

from gosari.agent import build_public_spec, detect_personal_hint
from gosari.agent.analysis import AnalysisEngine
from gosari.agent.llm import LlmClient, explanation_matches
from gosari.cache.semantic import lookup, store
from gosari.config import Settings, get_settings
from gosari.domain import CacheResolution, JobStage
from gosari.domain.envelope import ProgressEvent, ResultEnvelope
from gosari.domain.errors import GosariError
from gosari.logging import get_logger
from gosari.sessions import Session, new_id, utcnow

logger = get_logger(__name__)

FEATURE_HINTS = {
    "나들이": "outing",
    "날씨": "outing",
    "예보": "forecast_compare",
    "지역": "region_compare",
    "관측소": "station_search",
    "비교": "history_compare",
    "수첩": "notebook",
    "기록": "notebook",
    "나눔": "share",
    "나눌": "share",
    "가격": "market_query",
    "도매": "market_query",
    "얼마": "market_query",
    "판매": "retail_lookup",
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
        }


class Coordinator:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.engine = AnalysisEngine(self.settings)
        self.llm = LlmClient(self.settings)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def prepare(self, session: Session, payload: dict[str, Any]) -> dict[str, Any]:
        """공개/개인 분류와 조건 확인. 원천 호출·개인 변경 전 단계."""
        text = str(payload.get("text", ""))[: self.settings.max_text_length]
        if not text.strip() and not payload.get("spec"):
            raise GosariError("INVALID_INPUT")
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
                    "note": "개인 기록·나눔은 로컬 확인 폼에서 처리합니다. "
                    "외부로 전송되지 않습니다.",
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
        if self.llm.available:
            try:
                structured = self.llm.structure_question(text)
                if structured.get("private"):
                    return {
                        "classification": "personal",
                        "needs_confirmation": True,
                        "form": {"fields": []},
                    }
                if structured.get("clarify"):
                    return {
                        "classification": "public",
                        "needs_confirmation": True,
                        "form": {"questions": structured["clarify"]},
                    }
                spec = build_public_spec(structured)
                return {
                    "classification": "public",
                    "needs_confirmation": True,
                    "spec": spec,
                }
            except GosariError:
                pass
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

    def run_job(self, session: Session, spec_payload: dict[str, Any]) -> Job:
        spec = build_public_spec(spec_payload)
        request_id = new_id("req")
        job = Job(new_id("job"), request_id)
        with self._lock:
            session.jobs[job.job_id] = job.to_dict()
            self._jobs[job.job_id] = job
        job.stage = JobStage.RUNNING
        job.emit("accepted", "요청을 받았습니다.")
        try:
            safe_text = str(spec_payload.get("safe_text", ""))
            spec["contains_personal_hint"] = detect_personal_hint(safe_text)
            job.emit("cache_checked", "응답 캐시를 확인했습니다.")
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
                )
            else:
                envelope = self.engine.run(spec, request_id)
                envelope.cache_resolution = resolution
                if self.llm.available and envelope.data_status == "complete":
                    job.emit("calculated", "결정론 계산을 마쳤습니다.")
                    try:
                        explanation = self.llm.explain(envelope.model_dump(mode="json"))
                        if explanation_matches(explanation, envelope.result):
                            envelope.result["explanation"] = explanation
                            job.emit("explained", "설명을 검증했습니다.")
                        else:
                            envelope.warnings.append("설명 대조 불일치 — 검증된 표·근거만 제공")
                    except GosariError:
                        envelope.warnings.append("모델 사용 불가 — 검증된 표·근거만 제공")
                if resolution == CacheResolution.MISS:
                    store(
                        spec,
                        safe_text,
                        {
                            "data_status": envelope.data_status,
                            "source_mode": envelope.source_mode,
                            "result": envelope.result,
                            "warnings": envelope.warnings,
                        },
                        envelope.evidence_ids,
                        now=utcnow(),
                        valid_until=utcnow() + timedelta(hours=24),
                    )
            job.result = envelope
            job.stage = JobStage.COMPLETED
            job.emit("result_ready", "결과가 준비되었습니다.")
        except GosariError as exc:
            job.stage = JobStage.FAILED
            job.error = exc.code
            job.emit("failed", exc.safe_message)
        with self._lock:
            session.jobs[job.job_id] = job.to_dict()
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
            job.stage = JobStage.CANCELLED
            job.emit(
                "cancelled",
                "취소 요청됨 — 이미 전달된 외부 요청의 과금 취소는 보장하지 않음",
            )
        return job


_coordinator: Coordinator | None = None


def get_coordinator() -> Coordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = Coordinator()
    return _coordinator
