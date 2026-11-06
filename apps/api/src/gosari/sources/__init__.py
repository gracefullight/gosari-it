"""원천 어댑터 계약 (SRS §7.2). 키는 서버에서만 주입, 매니페스트 URL은 인증정보 제거."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class SourceManifest:
    source_id: str
    dataset_id: str
    operation: str
    sanitized_parameters: dict[str, Any]
    requested_scope: dict[str, Any] = field(default_factory=dict)
    fetched_scope: dict[str, Any] = field(default_factory=dict)
    failed_scope: dict[str, Any] = field(default_factory=dict)
    page_number: int | None = None
    page_size: int | None = None
    returned_count: int | None = None
    total_count: int | None = None
    has_more: bool | None = None
    fetched_at: datetime | None = None
    verified_on: str | None = None
    observed_period: dict[str, Any] = field(default_factory=dict)
    content_hash: str | None = None
    parser_version: str = "1"
    schema_version: str = "1"
    rights_status: str = "public_api"
    transport_status: str = "ok"
    source_mode: str = "fetched"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "dataset_id": self.dataset_id,
            "operation": self.operation,
            "sanitized_parameters": self.sanitized_parameters,
            "requested_scope": self.requested_scope,
            "fetched_scope": self.fetched_scope,
            "failed_scope": self.failed_scope,
            "page_number": self.page_number,
            "page_size": self.page_size,
            "returned_count": self.returned_count,
            "total_count": self.total_count,
            "has_more": self.has_more,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "verified_on": self.verified_on,
            "observed_period": self.observed_period,
            "content_hash": self.content_hash,
            "parser_version": self.parser_version,
            "schema_version": self.schema_version,
            "rights_status": self.rights_status,
            "transport_status": self.transport_status,
            "source_mode": self.source_mode,
        }


def content_hash(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def json_hash(obj: Any) -> str:
    return content_hash(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str))


def now_utc() -> datetime:
    return datetime.now(UTC)
