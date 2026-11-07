"""aT 정산·표준코드. 공식 명세: data.go.kr/15141809, /15141818.

katSale/trades의 평균가는 단위물량(unit_qty)당 원, 총물량은 unit_tot_qty다.
서로 다른 생/건·등급·포장 행을 합산 평균하지 않는다.
"""

import threading
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from gosari.config import Settings, get_settings
from gosari.domain.errors import GosariError
from gosari.sources import SourceManifest, json_hash, now_utc
from gosari.sources.live import TransmissionGate

CATALOG_URL = "https://apis.data.go.kr/B552845/katCode"
SETTLEMENT_URL = "https://apis.data.go.kr/B552845/katSale/trades"
_CODE_CACHE: dict[str, tuple[float, dict[str, list[dict[str, Any]]]]] = {}
_CODE_LOCK = threading.Lock()


def _number(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value).strip())
        return result if result.is_finite() and result >= 0 else None
    except InvalidOperation, ValueError, TypeError:
        return None


def _body(data: Any) -> tuple[list[dict[str, Any]], int]:
    try:
        response = data["response"]
        code = str(response["header"]["resultCode"])
        if code not in {"0", "00", "0000"}:
            raise GosariError("UPSTREAM_FAILED", {"reason": "AT_RESPONSE_ERROR"})
        body = response["body"]
        items = (body.get("items") or {}).get("item") or []
        if isinstance(items, dict):
            items = [items]
        total = int(body["totalCount"])
        if not isinstance(items, list) or total < 0 or not all(isinstance(x, dict) for x in items):
            raise ValueError
        return items, total
    except KeyError, TypeError, AttributeError, ValueError:
        raise GosariError("UPSTREAM_SCHEMA_CHANGED") from None


class AtAdapter:
    def __init__(self, gate: TransmissionGate, settings: Settings | None = None) -> None:
        self.gate = gate
        self.settings = settings or get_settings()

    def _key(self) -> str:
        if not self.settings.at_service_key:
            raise GosariError("CAPABILITY_DISABLED", {"reason": "AT_KEY_MISSING"})
        return unquote(self.settings.at_service_key)

    def catalog(self) -> dict[str, list[dict[str, Any]]]:
        """현재 표준코드 확인. 성공한 완전한 목록만 한 시간 재사용한다."""
        cache_key = json_hash(self._key())
        with _CODE_LOCK:
            cached = _CODE_CACHE.get(cache_key)
            if cached and time.monotonic() - cached[0] < 3600:
                return cached[1]
        result = {}
        for resource in ("goods", "wholesaleMarkets", "grades", "packagings"):
            params: dict[str, Any] = {
                "serviceKey": self._key(),
                "pageNo": 1,
                "numOfRows": 1000,
                "returnType": "json",
            }
            if resource == "goods":
                params.update({"cond[gds_lclsf_cd::EQ]": "14", "cond[gds_mclsf_cd::EQ]": "02"})
            data, _ = self.gate.get_json(f"{CATALOG_URL}/{resource}", params)
            rows, total = _body(data)
            if len(rows) != total:
                raise GosariError("UPSTREAM_SCHEMA_CHANGED", {"reason": "AT_CODES_INCOMPLETE"})
            prefix = {
                "goods": "gds_sclsf",
                "wholesaleMarkets": "whsl_mrkt",
                "grades": "grd",
                "packagings": "pkg",
            }[resource]
            if any(
                not isinstance(row.get(f"{prefix}_cd"), str)
                or not isinstance(row.get(f"{prefix}_nm"), str)
                for row in rows
            ):
                raise GosariError("UPSTREAM_SCHEMA_CHANGED")
            result[resource] = rows
        if not result["goods"] or any(
            row.get("gds_lclsf_cd") != "14"
            or row.get("gds_mclsf_cd") != "02"
            or row.get("gds_mclsf_nm") != "고사리"
            for row in result["goods"]
        ):
            raise GosariError("UPSTREAM_SCHEMA_CHANGED", {"reason": "AT_ITEM_CODE_UNVERIFIED"})
        with _CODE_LOCK:
            _CODE_CACHE[cache_key] = time.monotonic(), result
        return result

    def settlement(
        self,
        settlement_date: date,
        market_code: str,
        *,
        page: int = 1,
        per_page: int = 1000,
        small_code: str | None = None,
    ) -> tuple[list[dict[str, Any]], SourceManifest]:
        params: dict[str, Any] = {
            "serviceKey": self._key(),
            "returnType": "json",
            "pageNo": page,
            "numOfRows": per_page,
            "cond[trd_clcln_ymd::EQ]": settlement_date.isoformat(),
            "cond[whsl_mrkt_cd::EQ]": market_code,
            "cond[gds_lclsf_cd::EQ]": "14",
            "cond[gds_mclsf_cd::EQ]": "02",
        }
        if small_code:
            params["cond[gds_sclsf_cd::EQ]"] = small_code
        data, digest = self.gate.get_json(SETTLEMENT_URL, params)
        items, total = _body(data)
        try:
            actual_size = int(data["response"]["body"].get("numOfRows", per_page))
            actual_page = int(data["response"]["body"].get("pageNo", page))
            if actual_size <= 0 or actual_page != page or len(items) > actual_size:
                raise ValueError
        except ValueError, TypeError:
            raise GosariError("UPSTREAM_SCHEMA_CHANGED") from None
        manifest = SourceManifest(
            source_id="at_settlement",
            dataset_id="15141809",
            operation="katSale/trades",
            sanitized_parameters={k: v for k, v in params.items() if k != "serviceKey"},
            page_number=page,
            page_size=actual_size,
            returned_count=len(items),
            total_count=total,
            has_more=page * actual_size < total,
            fetched_at=now_utc(),
            content_hash=digest,
            observed_period={"settlement_date": settlement_date.isoformat()},
            source_mode="fetched",
        )
        return items, manifest


def settlement_card(row: dict[str, Any]) -> dict[str, Any]:
    """원자료 평균가와 단량 환산을 분리한다. 불명 단위는 환산하지 않는다."""
    average = _number(row.get("avgprc"))
    quantity = _number(row.get("unit_qty"))
    unit = str(row.get("unit_nm", "")).strip()
    grams = None
    if quantity and unit.lower() in {"kg", "㎏", "킬로그램"}:
        grams = quantity * 1000
    elif quantity and unit.lower() in {"g", "그램"}:
        grams = quantity
    per_kg = average * 1000 / grams if average is not None and grams else None
    option = " · ".join(
        str(row.get(k) or "").strip()
        for k in ("grd_nm", "pkg_nm", "sz_nm")
        if row.get(k) and str(row[k]).strip() != "."
    )
    return {
        "channel": "wholesale",
        "row_id": json_hash(row),
        "source_id": "at_settlement",
        "source_url": "https://www.data.go.kr/data/15141809/openapi.do",
        "product": f"{row.get('whsl_mrkt_nm', '')} · {row.get('gds_sclsf_nm', '고사리')}",
        "form": row.get("gds_sclsf_nm"),
        "product_option": option,
        "price_as_of": row.get("trd_clcln_ymd"),
        "price_basis": "정산 평균가",
        "price_value": float(average) if average is not None else None,
        "price_per_kg_value": round(float(per_kg), 2) if per_kg is not None else None,
        "net_weight_value": float(grams) if grams is not None else None,
        "original_quantity": str(quantity) if quantity is not None else None,
        "original_unit": unit,
        "origin_label_raw": str(row.get("plor_nm") or "").strip(),
        "market_code": row.get("whsl_mrkt_cd"),
        "market_name": row.get("whsl_mrkt_nm"),
        "corporation": row.get("corp_nm"),
        "grade": row.get("grd_nm"),
        "package": row.get("pkg_nm"),
        "minimum_price": str(_number(row.get("lwprc")))
        if _number(row.get("lwprc")) is not None
        else None,
        "maximum_price": str(_number(row.get("hgprc")))
        if _number(row.get("hgprc")) is not None
        else None,
        "total_quantity": str(_number(row.get("unit_tot_qty")))
        if _number(row.get("unit_tot_qty")) is not None
        else None,
        "total_price": str(_number(row.get("totprc")))
        if _number(row.get("totprc")) is not None
        else None,
        "conversion_formula": f"{average:,}원 ÷ {grams / 1000:g}kg = {per_kg:,.2f}원/kg"
        if per_kg is not None and grams
        else None,
        "price_state": "valid" if average is not None else "missing",
        "source_mode": "fetched",
    }


def query_settlements(
    spec: dict[str, Any], settings: Settings, checkpoint: Callable[[], None] | None = None
) -> tuple[dict[str, Any], list[SourceManifest], list[dict[str, Any]], list[dict[str, Any]]]:
    """시장·날짜마다 페이지를 끝까지 대조하고 실패한 범위를 별도로 반환한다."""
    checkpoint = checkpoint or (lambda: None)
    checkpoint()
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    try:
        start = date.fromisoformat(str(spec.get("settlement_date") or today.isoformat()))
        end = date.fromisoformat(str(spec.get("settlement_date_end") or start.isoformat()))
    except ValueError:
        raise GosariError("INVALID_INPUT", {"fields": ["settlement_date"]}) from None
    if end < start or end > today:
        raise GosariError("INVALID_INPUT", {"fields": ["settlement_date_end"]})
    if spec.get("item_codes") not in (None, {"large": "14", "middle": "02"}):
        raise GosariError("INVALID_INPUT", {"fields": ["item_codes"]})
    adapter = AtAdapter(TransmissionGate(settings, checkpoint=checkpoint), settings)
    codes = adapter.catalog()
    markets = spec.get("market_ids", ["110001"])
    if (
        not isinstance(markets, list)
        or not markets
        or any(
            not isinstance(m, str)
            or m not in {r["whsl_mrkt_cd"] for r in codes["wholesaleMarkets"]}
            for m in markets
        )
    ):
        raise GosariError("INVALID_INPUT", {"fields": ["market_ids"]})
    markets = list(dict.fromkeys(markets))
    form = spec.get("fresh_or_dried") or ""
    if not isinstance(form, str):
        raise GosariError("INVALID_INPUT", {"fields": ["fresh_or_dried"]})
    form_aliases = {"fresh": "생고사리", "dried": "건고사리"}
    form = form_aliases.get(form, form)
    goods = [r for r in codes["goods"] if r["gds_sclsf_nm"] == form]
    if form and not goods:
        raise GosariError("INVALID_INPUT", {"fields": ["fresh_or_dried"]})
    small_code = goods[0]["gds_sclsf_cd"] if form else None
    grade = str(spec.get("grade") or "")
    package = str(spec.get("package_code") or "")
    weight = str(spec.get("package_weight_unit") or "")
    if grade and grade not in {r["grd_cd"] for r in codes["grades"]}:
        raise GosariError("INVALID_INPUT", {"fields": ["grade"]})
    if package and package not in {r["pkg_cd"] for r in codes["packagings"]}:
        raise GosariError("INVALID_INPUT", {"fields": ["package_code"]})
    cards: list[dict[str, Any]] = []
    manifests: list[SourceManifest] = []
    failed: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    weights: set[str] = set()
    started = time.monotonic()
    day = start
    stopped = False
    while day <= end and not stopped:
        for market in markets:
            checkpoint()
            scope = {"settlement_date": day.isoformat(), "market_code": market}
            scope_start = len(cards)
            count, total, page, seen = 0, None, 1, set()
            try:
                while True:
                    checkpoint()
                    if time.monotonic() - started >= settings.job_deadline:
                        raise GosariError("JOB_DEADLINE_EXCEEDED")
                    rows, manifest = adapter.settlement(
                        day, market, page=page, small_code=small_code
                    )
                    manifests.append(manifest)
                    if total is not None and total != manifest.total_count:
                        raise GosariError("QUALITY_CONFLICT", {"reason": "TOTAL_COUNT_CHANGED"})
                    total = manifest.total_count
                    digest = json_hash(rows)
                    if rows and digest in seen:
                        raise GosariError("QUALITY_CONFLICT", {"reason": "REPEATED_PAGE"})
                    seen.add(digest)
                    for row in rows:
                        if (
                            row.get("trd_clcln_ymd") != day.isoformat()
                            or row.get("whsl_mrkt_cd") != market
                            or row.get("gds_lclsf_cd") != "14"
                            or row.get("gds_mclsf_cd") != "02"
                            or (small_code and row.get("gds_sclsf_cd") != small_code)
                        ):
                            raise GosariError("QUALITY_CONFLICT", {"reason": "ROW_SCOPE_MISMATCH"})
                    count += len(rows)
                    for row in rows:
                        raw_weight = _number(row.get("unit_qty"))
                        weight_option = (
                            f"{raw_weight:g} {str(row.get('unit_nm') or '').strip()}"
                            if raw_weight is not None
                            else ""
                        )
                        if weight_option:
                            weights.add(weight_option)
                        if grade and row.get("grd_cd") != grade:
                            continue
                        if package and row.get("pkg_cd") != package:
                            continue
                        if weight and weight_option != weight:
                            continue
                        if spec.get("origin_filter") and str(spec["origin_filter"]) not in str(
                            row.get("plor_nm") or ""
                        ):
                            continue
                        cards.append(settlement_card(row))
                    if not manifest.has_more:
                        if count != total:
                            raise GosariError("QUALITY_CONFLICT", {"reason": "PAGE_COUNT_MISMATCH"})
                        completed.append({**scope, "returned_count": count, "total_count": total})
                        break
                    if not rows:
                        raise GosariError("QUALITY_CONFLICT", {"reason": "EMPTY_PAGE"})
                    page += 1
            except GosariError as exc:
                if exc.code == "ACTION_NOT_ALLOWED":
                    exc.extra["fetched_scope"] = completed
                    raise
                del cards[scope_start:]
                failed.append(
                    {
                        **scope,
                        "page": page,
                        "returned_count": count,
                        "total_count": total,
                        "reason": exc.extra.get("reason", exc.code),
                    }
                )
                if exc.code in {"JOB_DEADLINE_EXCEEDED", "BUDGET_EXCEEDED", "SOURCE_RATE_LIMIT"}:
                    failed[-1]["remaining_scope"] = {
                        "from": day.isoformat(),
                        "through": end.isoformat(),
                        "market_codes": markets[markets.index(market) :],
                        "following_day_market_codes": markets,
                    }
                    stopped = True
                    break
        day += timedelta(days=1)
    result = {
        "channel": "wholesale",
        "code_catalog_hash": json_hash(codes),
        "price_cards": sorted(
            cards, key=lambda c: (c["price_as_of"], c["product"], c["row_id"]), reverse=True
        ),
        "completed_scope": completed,
        "failed_scope": failed,
        "options": {
            "weights": [{"value": value, "label": value} for value in sorted(weights)],
            "markets": [
                {"value": r["whsl_mrkt_cd"], "label": r["whsl_mrkt_nm"]}
                for r in codes["wholesaleMarkets"]
            ],
            "forms": [
                {"value": r["gds_sclsf_nm"], "label": r["gds_sclsf_nm"]} for r in codes["goods"]
            ],
            "grades": [{"value": r["grd_cd"], "label": r["grd_nm"]} for r in codes["grades"]],
            "packages": [{"value": r["pkg_cd"], "label": r["pkg_nm"]} for r in codes["packagings"]],
        },
    }
    return result, manifests, failed, completed
