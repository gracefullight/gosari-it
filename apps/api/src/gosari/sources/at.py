"""aT 도매 정산 어댑터 (15141809). 세부 operation 경로는 어댑터 매뉴얼에서 고정한다.

거래일·시장코드가 필수 조건. 단가/총액 의미가 미확정이면 환산·가중 평균을 보류한다.
"""

from datetime import date
from typing import Any

from gosari.config import Settings, get_settings
from gosari.domain.errors import GosariError
from gosari.sources import SourceManifest, now_utc
from gosari.sources.live import TransmissionGate


class AtAdapter:
    def __init__(
        self,
        gate: TransmissionGate,
        settings: Settings | None = None,
        *,
        base_url: str = "https://apis.data.go.kr/B552845",
        settlement_path: str = "wholesaleMarketSettlementService/getWholesaleMarketSettlement",
    ) -> None:
        self.gate = gate
        self.settings = settings or get_settings()
        self.base_url = base_url
        self.settlement_path = settlement_path

    def settlement(
        self,
        settlement_date: date,
        market_code: str,
        *,
        page: int = 1,
        per_page: int = 100,
    ) -> tuple[list[dict[str, Any]], SourceManifest]:
        key = self.settings.at_service_key
        if not key:
            raise GosariError("CAPABILITY_DISABLED", {"reason": "AT_KEY_MISSING"})
        url = f"{self.base_url}/{self.settlement_path}"
        params = {
            "serviceKey": key,
            "settlementDate": settlement_date.strftime("%Y%m%d"),
            "marketCode": market_code,
            "pageNo": page,
            "numOfRows": per_page,
            "dataType": "JSON",
        }
        data, digest = self.gate.get_json(url, params)
        try:
            body = data["response"]["body"]
            items = body.get("items", {}).get("item", [])
            total_count = body.get("totalCount")
        except KeyError, TypeError, AttributeError:
            raise GosariError("UPSTREAM_SCHEMA_CHANGED") from None
        if isinstance(items, dict):
            items = [items]
        manifest = SourceManifest(
            source_id="at_settlement",
            dataset_id="15141809",
            operation="settlement",
            sanitized_parameters={
                "settlementDate": settlement_date.isoformat(),
                "marketCode": market_code,
            },
            page_number=page,
            page_size=per_page,
            returned_count=len(items),
            total_count=int(total_count) if total_count is not None else None,
            fetched_at=now_utc(),
            content_hash=digest,
            source_mode="fetched",
        )
        return items, manifest
