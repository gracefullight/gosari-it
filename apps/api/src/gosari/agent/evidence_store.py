"""공개 근거 저장소 — 분석 결과와 분리된 영속화 담당 (SRS §4.1)."""

import json
import threading
from typing import Any

from psycopg.types.json import Jsonb

from gosari.db import connection, db_available
from gosari.logging import get_logger
from gosari.sources import json_hash

logger = get_logger(__name__)


class EvidenceStore:
    """공개 근거 저장소. 개인 수첩 ID·별칭·세션 ID를 포함하지 않는다."""

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def put(self, evidence: dict[str, Any]) -> str:
        evidence_id = f"ev-{json_hash(evidence)[:24]}"
        with self._lock:
            self._entries[evidence_id] = evidence
        if db_available():
            try:
                payload = json.loads(json.dumps(evidence, ensure_ascii=False, default=str))
                with connection() as conn:
                    conn.execute(
                        """INSERT INTO public_evidence
                        (evidence_id, public_query_spec, quality_summary, effective_scope,
                         formula_version, result_values)
                        VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (evidence_id) DO NOTHING""",
                        (
                            evidence_id,
                            Jsonb(payload.get("public_query_spec", {})),
                            Jsonb({"evidence_payload": payload}),
                            Jsonb(payload.get("effective_scope", {})),
                            payload.get("formula_version", "calc-v1"),
                            Jsonb(payload.get("result_values", {})),
                        ),
                    )
                    conn.commit()
            except Exception:
                logger.warning("public evidence persistence unavailable")
        return evidence_id

    def get(self, evidence_id: str) -> dict[str, Any] | None:
        with self._lock:
            cached = self._entries.get(evidence_id)
        if cached is not None:
            return cached
        if db_available():
            try:
                with connection() as conn:
                    row = conn.execute(
                        "SELECT public_query_spec, quality_summary, effective_scope, "
                        "formula_version, "
                        "result_values, created_at FROM public_evidence WHERE evidence_id=%s",
                        (evidence_id,),
                    ).fetchone()
                if row:
                    payload = row[1].get("evidence_payload") if isinstance(row[1], dict) else None
                    if payload is None:
                        payload = {
                            "public_query_spec": row[0],
                            "effective_scope": row[2],
                            "formula_version": row[3],
                            "result_values": row[4],
                            "created_at": row[5].isoformat(),
                        }
                    with self._lock:
                        self._entries[evidence_id] = payload
                    return payload
            except Exception:
                logger.warning("public evidence retrieval unavailable")
        return None


_evidence_store = EvidenceStore()


def get_evidence_store() -> EvidenceStore:
    return _evidence_store
