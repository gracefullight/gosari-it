"""공개 근거 조회 — 개인 기록 연결 정보 제외."""

from typing import Any

from litestar import Controller, Request, get

from gosari.agent.analysis import get_evidence_store
from gosari.domain.errors import GosariError


class EvidenceController(Controller):
    path = "/evidence"

    @get("/{evidence_id:str}")
    async def get_evidence(
        self, request: Request[Any, Any, Any], evidence_id: str
    ) -> dict[str, Any]:
        evidence = get_evidence_store().get(evidence_id)
        if evidence is None:
            raise GosariError("RESOURCE_NOT_FOUND")
        return evidence
