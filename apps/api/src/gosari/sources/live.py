"""라이브 원천 어댑터 (SRS §7). 전송 게이트·허용 도메인·키 서버 주입·페이지 대조."""

import math
import threading
import time
from collections.abc import Callable
from datetime import date
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from gosari.config import Settings, get_settings
from gosari.domain.errors import GosariError
from gosari.logging import get_logger
from gosari.quality import interpret_numeric
from gosari.quality.calculation import Observation
from gosari.sources import SourceManifest, content_hash, now_utc

logger = get_logger(__name__)

ALLOWED_DOMAINS = frozenset(
    {
        "open.jejudatahub.net",
        "apis.data.go.kr",
        "apihub.kma.go.kr",
        "api.openai.com",
        "api.open-meteo.com",
        "archive-api.open-meteo.com",
        "api.vworld.kr",
    }
)

JEJU_578_PATH = "t1bab75a555a15715btaa7a5abaa1aab"
JEJU_579_PATH = "1aD5taat1attaa51Db1511b51ab9Da19"


class SourceBudget:
    """한 프로세스의 공급자별 일일 호출량. 어댑터/작업을 새로 만들어도 공유한다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day = now_utc().date()
        self._counts: dict[str, int] = {}

    def check(self, host: str, limit: int, *, charge: bool = False) -> None:
        with self._lock:
            today = now_utc().date()
            if today != self._day:
                self._day = today
                self._counts.clear()
            count = self._counts.get(host, 0)
            if count >= limit:
                raise GosariError("BUDGET_EXCEEDED")
            if charge:
                self._counts[host] = count + 1


_source_budget = SourceBudget()


class TransmissionGate:
    """공개 조건만 허용 도메인으로 전송한다. 개인 원문은 이 경로를 탈 수 없다."""

    def __init__(
        self,
        settings: Settings | None = None,
        checkpoint: Callable[[], None] | None = None,
        budget: SourceBudget | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.checkpoint = checkpoint or (lambda: None)
        self._daily_calls = 0
        self._day = now_utc().date()
        self._budget = budget or _source_budget
        self._budget_host = ""

    def check(self, url: str) -> None:
        self.checkpoint()
        if not self.settings.external_requests_enabled:
            raise GosariError("POLICY_BLOCKED", {"reason": "EXTERNAL_REQUESTS_DISABLED"})
        host = urlsplit(url).hostname or ""
        if host not in ALLOWED_DOMAINS:
            raise GosariError("ORIGIN_DENIED")
        self._budget_host = host
        self._budget.check(host, self.settings.source_daily_budget, charge=True)
        self._daily_calls += 1

    def _check_budget(self) -> None:
        today = now_utc().date()
        if today != self._day:
            self._day = today
            self._daily_calls = 0
        self._budget.check(self._budget_host, self.settings.source_daily_budget)

    @staticmethod
    def _retry_delay(value: str | None, attempt: int) -> float:
        if value:
            try:
                delay = float(value)
                if math.isfinite(delay):
                    return max(0.0, delay)
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(value)
                    return max(0.0, (retry_at - now_utc()).total_seconds())
                except ValueError, TypeError, OverflowError:
                    pass
        return 2.0 * (attempt + 1)

    def _pause(self, delay: float) -> None:
        until = time.monotonic() + delay
        while time.monotonic() < until:
            self.checkpoint()
            time.sleep(min(0.1, max(0, until - time.monotonic())))

    def get_json(
        self, url: str, params: dict[str, Any], *, timeout: float = 20.0
    ) -> tuple[Any, str]:
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            self.check(url)
            self.checkpoint()
            try:
                response = httpx.get(url, params=params, timeout=timeout)
                if response.status_code == 429:
                    if attempt >= self.settings.max_retries:
                        raise GosariError("SOURCE_RATE_LIMIT")
                    self._check_budget()
                    delay = self._retry_delay(response.headers.get("Retry-After"), attempt)
                    self._pause(delay)
                    continue
                if response.status_code in (401, 403):
                    raise GosariError("POLICY_BLOCKED", {"reason": "SOURCE_AUTH_DENIED"})
                response.raise_for_status()
                try:
                    payload = response.json()
                except ValueError:
                    if "firewall" in response.text.lower():
                        raise GosariError("POLICY_BLOCKED", {"reason": "SOURCE_FIREWALL"}) from None
                    raise GosariError("UPSTREAM_SCHEMA_CHANGED") from None
                return payload, content_hash(response.content)
            except GosariError:
                raise
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self.settings.max_retries:
                    break
                self._check_budget()
                self._pause(1.0 * (attempt + 1))
        logger.warning(
            "source fetch failed",
            error_type=type(last_error).__name__ if last_error else None,
        )
        raise GosariError("UPSTREAM_FAILED")


def sanitized_url(url: str) -> str:
    """매니페스트용 — path/query의 인증정보를 제거한다."""
    parts = urlsplit(url)
    path = parts.path
    if parts.hostname == "open.jejudatahub.net" and path.startswith("/api/proxy/"):
        path = path.rsplit("/", 1)[0] + "/[REDACTED]"
    for secret_segment in ("projectKey", "serviceKey", "authKey"):
        if secret_segment in path:
            path = "/[REDACTED_PATH]"
            break
    return f"{parts.scheme}://{parts.hostname or ''}{path}"


class JejuHubAdapter:
    """제주데이터허브 578 관측소·579 일별 기상. 페이지 수·반환 수·전체 건수를 대조한다."""

    def __init__(self, gate: TransmissionGate, settings: Settings | None = None) -> None:
        self.gate = gate
        self.settings = settings or get_settings()

    def _url(self, dataset_path: str) -> str:
        key = self.settings.jeju_project_key
        if not key:
            raise GosariError("CAPABILITY_DISABLED", {"reason": "JEJU_KEY_MISSING"})
        return f"https://open.jejudatahub.net/api/proxy/{dataset_path}/{key}"

    def stations(
        self, observatory_name: str | None = None
    ) -> tuple[list[dict[str, Any]], SourceManifest]:
        params: dict[str, Any] = {"limit": 100, "number": 1}
        if observatory_name:
            params["observatoryName"] = observatory_name
        url = self._url(JEJU_578_PATH)
        data, digest = self.gate.get_json(url, params)
        rows = data if isinstance(data, list) else data.get("data", data.get("rows", []))
        if not isinstance(rows, list):
            raise GosariError("UPSTREAM_SCHEMA_CHANGED")
        manifest = SourceManifest(
            source_id="jeju_578",
            dataset_id="578",
            operation="stations",
            sanitized_parameters={"observatoryName": observatory_name},
            returned_count=len(rows),
            fetched_at=now_utc(),
            content_hash=digest,
            source_mode="fetched",
        )
        return rows, manifest

    def daily_weather(
        self,
        search_date: date,
        observatory_name: str | None = None,
        *,
        max_pages: int = 10,
    ) -> tuple[list[Observation], SourceManifest]:
        params: dict[str, Any] = {
            "searchDate": search_date.strftime("%Y%m%d"),
            "limit": 100,
        }
        if observatory_name:
            params["observatoryName"] = observatory_name
        url = self._url(JEJU_579_PATH)
        observations: list[Observation] = []
        page = 1
        total_count: int | None = None
        returned = 0
        has_more = False
        digest_parts: list[str] = []
        failed_scope: dict[str, Any] = {}
        while page <= max_pages:
            params["number"] = page
            try:
                data, digest = self.gate.get_json(url, params)
            except GosariError as error:
                if error.code in ("ACTION_NOT_ALLOWED", "JOB_DEADLINE_EXCEEDED", "BUDGET_EXCEEDED"):
                    raise
                failed_scope = {"date": search_date.isoformat(), "page": page, "reason": error.code}
                break
            digest_parts.append(digest)
            if not isinstance(data, dict):
                raise GosariError("UPSTREAM_SCHEMA_CHANGED")
            rows = data.get("data", data.get("rows", []))
            if not isinstance(rows, list):
                raise GosariError("UPSTREAM_SCHEMA_CHANGED")
            total_count = data.get("totCnt", total_count)
            has_more = bool(data.get("hasMore", False))
            returned += len(rows)
            for row in rows:
                name = row.get("observatoryName")
                base_raw = row.get("baseDate")
                if not name or not base_raw:
                    continue
                obs_date = _parse_base_date(str(base_raw))
                if obs_date is None:
                    continue
                for element, field in (
                    ("daily_rainfall", "dailyRainfall"),
                    ("average_temperature", "averageTemperature"),
                ):
                    raw = row.get(field)
                    iv = interpret_numeric(None if raw is None else str(raw))
                    observations.append(
                        Observation(
                            source_id="jeju_579",
                            station_key=str(name),
                            observation_date=obs_date,
                            element=element,
                            raw=iv.raw,
                            numeric=iv.numeric,
                            value_state=iv.state,
                        )
                    )
            if not has_more:
                break
            page += 1
        if has_more and not failed_scope:
            failed_scope = {
                "date": search_date.isoformat(),
                "page": page,
                "reason": "PAGE_LIMIT_REACHED",
            }
        if total_count is not None and returned != int(total_count):
            logger.warning("page count mismatch", returned=returned, total=total_count)
            failed_scope = failed_scope or {
                "date": search_date.isoformat(),
                "page": page,
                "reason": "PAGE_COUNT_MISMATCH",
            }
        manifest = SourceManifest(
            source_id="jeju_579",
            dataset_id="579",
            operation="daily_weather",
            sanitized_parameters={
                "searchDate": search_date.isoformat(),
                "observatoryName": observatory_name,
            },
            page_number=page,
            page_size=100,
            returned_count=returned,
            total_count=int(total_count) if total_count is not None else None,
            has_more=has_more,
            requested_scope={"date": search_date.isoformat(), "station": observatory_name},
            fetched_scope={"pages": len(digest_parts), "returned_count": returned},
            failed_scope=failed_scope,
            transport_status="partial" if failed_scope else "ok",
            fetched_at=now_utc(),
            content_hash=content_hash(":".join(digest_parts)),
            source_mode="fetched",
        )
        return observations, manifest


def _parse_base_date(raw: str) -> date | None:
    from datetime import datetime

    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


class KmaAdapter:
    """기상청 ASOS 일자료·단기예보 (공공데이터포털 경유). 관측·발표·대상시각을 구분한다."""

    ASOS_URL = "https://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList"
    VILAGE_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
    CURRENT_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"

    def __init__(self, gate: TransmissionGate, settings: Settings | None = None) -> None:
        self.gate = gate
        self.settings = settings or get_settings()

    def _key(self) -> str:
        key = self.settings.kma_service_key
        if not key:
            raise GosariError("CAPABILITY_DISABLED", {"reason": "KMA_KEY_MISSING"})
        return key

    def current_grid(
        self, nx: int, ny: int, base_date: date, base_time: str
    ) -> tuple[list[dict[str, Any]], SourceManifest]:
        data, digest = self.gate.get_json(
            self.CURRENT_URL,
            {
                "serviceKey": self._key(),
                "base_date": base_date.strftime("%Y%m%d"),
                "base_time": base_time,
                "nx": nx,
                "ny": ny,
                "numOfRows": 100,
                "pageNo": 1,
                "dataType": "JSON",
            },
        )
        try:
            response = data["response"]
            if str(response["header"]["resultCode"]) != "00":
                raise GosariError("UPSTREAM_FAILED")
            items = response["body"]["items"]["item"]
            if not isinstance(items, list) or not items:
                raise GosariError("UPSTREAM_FAILED")
            for item in items:
                if (
                    str(item["baseDate"]) != base_date.strftime("%Y%m%d")
                    or str(item["baseTime"]) != base_time
                    or int(item["nx"]) != nx
                    or int(item["ny"]) != ny
                ):
                    raise GosariError("UPSTREAM_SCHEMA_CHANGED")
        except KeyError, TypeError, ValueError:
            raise GosariError("UPSTREAM_SCHEMA_CHANGED") from None
        return items, SourceManifest(
            source_id="kma_ultra_short",
            dataset_id="15084084",
            operation="getUltraSrtNcst",
            sanitized_parameters={
                "nx": nx,
                "ny": ny,
                "base_date": base_date.isoformat(),
                "base_time": base_time,
            },
            returned_count=len(items),
            fetched_at=now_utc(),
            content_hash=digest,
            source_mode="fetched",
        )

    def asos_daily(
        self, stn_ids: str, start_dt: date, end_dt: date
    ) -> tuple[list[Observation], SourceManifest]:
        params = {
            "serviceKey": self._key(),
            "dataCd": "ASOS",
            "dateCd": "DAY",
            "startDt": start_dt.strftime("%Y%m%d"),
            "endDt": end_dt.strftime("%Y%m%d"),
            "stnIds": stn_ids,
            "numOfRows": 500,
            "pageNo": 1,
            "dataType": "JSON",
        }
        data, digest = self.gate.get_json(self.ASOS_URL, params)
        try:
            items = data["response"]["body"]["items"]["item"]
        except KeyError, TypeError:
            raise GosariError("UPSTREAM_SCHEMA_CHANGED") from None
        observations: list[Observation] = []
        for item in items:
            obs_date = _parse_base_date(str(item.get("tm", "")))
            if obs_date is None:
                continue
            station = str(item.get("stnId", ""))
            for element, field in (
                ("average_temperature", "avgTa"),
                ("daily_rainfall", "sumRn"),
            ):
                raw = item.get(field)
                iv = interpret_numeric(None if raw is None else str(raw))
                observations.append(
                    Observation(
                        source_id="kma_asos",
                        station_key=station,
                        observation_date=obs_date,
                        element=element,
                        raw=iv.raw,
                        numeric=iv.numeric,
                        value_state=iv.state,
                    )
                )
        manifest = SourceManifest(
            source_id="kma_asos",
            dataset_id="15059093",
            operation="getWthrDataList",
            sanitized_parameters={
                "stnIds": stn_ids,
                "startDt": start_dt.isoformat(),
                "endDt": end_dt.isoformat(),
            },
            returned_count=len(items),
            fetched_at=now_utc(),
            content_hash=digest,
            source_mode="fetched",
        )
        return observations, manifest

    def vilage_forecast(
        self, nx: int, ny: int, base_date: date, base_time: str
    ) -> tuple[list[dict[str, Any]], SourceManifest]:
        params = {
            "serviceKey": self._key(),
            "base_date": base_date.strftime("%Y%m%d"),
            "base_time": base_time,
            "nx": nx,
            "ny": ny,
            "numOfRows": 1000,
            "pageNo": 1,
            "dataType": "JSON",
        }
        data, digest = self.gate.get_json(self.VILAGE_URL, params)
        try:
            items = data["response"]["body"]["items"]["item"]
        except KeyError, TypeError:
            raise GosariError("UPSTREAM_SCHEMA_CHANGED") from None
        rows = [
            {
                "published_at": f"{item.get('baseDate')} {item.get('baseTime')}",
                "target_at": f"{item.get('fcstDate')} {item.get('fcstTime')}",
                "grid": f"{nx},{ny}",
                "category": item.get("category"),
                "value": item.get("fcstValue"),
            }
            for item in items
        ]
        manifest = SourceManifest(
            source_id="kma_vilage",
            dataset_id="15084084",
            operation="getVilageFcst",
            sanitized_parameters={
                "nx": nx,
                "ny": ny,
                "base_date": base_date.isoformat(),
                "base_time": base_time,
            },
            returned_count=len(rows),
            fetched_at=now_utc(),
            content_hash=digest,
            source_mode="fetched",
        )
        return rows, manifest
