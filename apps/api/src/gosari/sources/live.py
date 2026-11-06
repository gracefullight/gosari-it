"""라이브 원천 어댑터 (SRS §7). 전송 게이트·허용 도메인·키 서버 주입·페이지 대조."""

import time
from datetime import date
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
    {"open.jejudatahub.net", "apis.data.go.kr", "apihub.kma.go.kr", "api.openai.com"}
)

JEJU_578_PATH = "t1bab75a555a15715btaa7a5abaa1aab"
JEJU_579_PATH = "1aD5taat1attaa51Db1511b51ab9Da19"


class TransmissionGate:
    """공개 조건만 허용 도메인으로 전송한다. 개인 원문은 이 경로를 탈 수 없다."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._daily_calls = 0
        self._day = now_utc().date()

    def check(self, url: str) -> None:
        if not self.settings.external_requests_enabled:
            raise GosariError("POLICY_BLOCKED", {"reason": "EXTERNAL_REQUESTS_DISABLED"})
        host = urlsplit(url).hostname or ""
        if host not in ALLOWED_DOMAINS:
            raise GosariError("ORIGIN_DENIED")
        today = now_utc().date()
        if today != self._day:
            self._day = today
            self._daily_calls = 0
        if self._daily_calls >= self.settings.source_daily_budget:
            raise GosariError("BUDGET_EXCEEDED")
        self._daily_calls += 1

    def get_json(
        self, url: str, params: dict[str, Any], *, timeout: float = 20.0
    ) -> tuple[Any, str]:
        self.check(url)
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = httpx.get(url, params=params, timeout=timeout)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    delay = min(float(retry_after) if retry_after else 2.0 * (attempt + 1), 30.0)
                    if attempt >= self.settings.max_retries:
                        raise GosariError("SOURCE_RATE_LIMIT")
                    time.sleep(delay)
                    continue
                if response.status_code in (401, 403):
                    raise GosariError("POLICY_BLOCKED", {"reason": "SOURCE_AUTH_DENIED"})
                response.raise_for_status()
                return response.json(), content_hash(response.content)
            except GosariError:
                raise
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self.settings.max_retries:
                    break
                time.sleep(1.0 * (attempt + 1))
        logger.warning(
            "source fetch failed",
            error_type=type(last_error).__name__ if last_error else None,
        )
        raise GosariError("UPSTREAM_FAILED")


def sanitized_url(url: str) -> str:
    """매니페스트용 — path/query의 인증정보를 제거한다."""
    parts = urlsplit(url)
    path = parts.path
    for secret_segment in ("projectKey", "serviceKey", "authKey"):
        if secret_segment in path:
            path = "/[REDACTED_PATH]"
            break
    return f"{parts.scheme}://{parts.netloc}{path}"


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
        params: dict[str, Any] = {}
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
        while page <= max_pages:
            params["number"] = page
            data, digest = self.gate.get_json(url, params)
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
        if total_count is not None and returned != int(total_count):
            logger.warning("page count mismatch", returned=returned, total=total_count)
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

    def __init__(self, gate: TransmissionGate, settings: Settings | None = None) -> None:
        self.gate = gate
        self.settings = settings or get_settings()

    def _key(self) -> str:
        key = self.settings.kma_service_key
        if not key:
            raise GosariError("CAPABILITY_DISABLED", {"reason": "KMA_KEY_MISSING"})
        return key

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
