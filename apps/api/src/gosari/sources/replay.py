"""고정 검증 입력 재생 (SRS §10.6, §16.3 replay). 실시간 원천 주장 금지."""

import csv
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from gosari.quality import interpret_numeric
from gosari.quality.calculation import Observation
from gosari.sources import content_hash

SEONHEUL_FILE = "제주허브_579_선흘_2023-2024봄_호출검증.csv"
KMA184_FILE = "기상청_ASOS_제주184_2026봄_61일_표추출.csv"
CURRENT_FILE = "기상청_제주_당일관측_20261105_1843KST_검증.csv"
AT_FILE = "aT_고사리정산_시장별_봄_표본검증.csv"
RETAIL_FILE = "제주산_고사리_상품표시가_검증.json"

VERIFIED_ON = "2026-11-05"


def load_seonheul(fixtures_dir: Path) -> tuple[list[Observation], dict[str, Any]]:
    """선흘 579 표본. 행 부재는 coverage 부재이지 필드 공란이 아니다."""
    path = fixtures_dir / SEONHEUL_FILE
    observations: list[Observation] = []
    absent_dates: list[str] = []
    page_checks: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            search_date = datetime.strptime(row["search_date"], "%Y%m%d").date()
            page_checks.append(
                {
                    "search_date": search_date.isoformat(),
                    "total_count": int(row["api_total_rows"]),
                    "returned_count": int(row["returned_rows"]),
                    "has_more": row["has_more"] == "true",
                }
            )
            if int(row["seonheul_row_count"]) == 0:
                absent_dates.append(search_date.isoformat())
                continue
            obs_date = (
                datetime.strptime(row["seonheul_base_date"], "%Y%m%d").date()
                if row["seonheul_base_date"]
                else search_date
            )
            for element, column in (
                ("daily_rainfall", "daily_rainfall"),
                ("average_temperature", "average_temperature"),
            ):
                iv = interpret_numeric(row[column])
                observations.append(
                    Observation(
                        source_id="jeju_579",
                        station_key="선흘",
                        observation_date=obs_date,
                        element=element,
                        raw=iv.raw,
                        numeric=iv.numeric,
                        value_state=iv.state,
                    )
                )
    meta = {
        "file_hash": content_hash(path.read_bytes()),
        "absent_dates": absent_dates,
        "page_checks": page_checks,
        "verified_on": VERIFIED_ON,
    }
    return observations, meta


def load_kma184(fixtures_dir: Path) -> tuple[list[Observation], dict[str, Any]]:
    """제주184 공개 표 61일. 공란 의미 확정 전 0/결측 치환 금지."""
    path = fixtures_dir / KMA184_FILE
    observations: list[Observation] = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            obs_date = date.fromisoformat(row["시간"])
            for element, column in (
                ("average_temperature", "평균기온(°C)"),
                ("daily_rainfall", "일강수량(mm)"),
            ):
                iv = interpret_numeric(row[column])
                observations.append(
                    Observation(
                        source_id="kma_asos",
                        station_key="제주(184)",
                        observation_date=obs_date,
                        element=element,
                        raw=iv.raw,
                        numeric=iv.numeric,
                        value_state=iv.state,
                    )
                )
    return observations, {
        "file_hash": content_hash(path.read_bytes()),
        "verified_on": VERIFIED_ON,
    }


def load_current_observations(
    fixtures_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """당일 공개 표 43지점 — 현재 API 호출 결과로 표시하지 않는다."""
    path = fixtures_dir / CURRENT_FILE
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    stations = [
        {
            "station_code": r["stationCode"],
            "station_name": r["stationName"],
            "altitude_m": Decimal(r["altitude_m"]) if r["altitude_m"] else None,
            "location": r["location"],
            "observation_time": r["observation_time_KST"],
            "temperature_c": interpret_numeric(r["temperature_C"] or None).numeric,
            "day_rain_mm": interpret_numeric(r["dayRain_mm"] or None).numeric,
        }
        for r in rows
    ]
    return stations, {
        "file_hash": content_hash(path.read_bytes()),
        "verified_on": VERIFIED_ON,
    }


def load_at_summary(fixtures_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = fixtures_dir / AT_FILE
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows, {
        "file_hash": content_hash(path.read_bytes()),
        "verified_on": VERIFIED_ON,
    }


def load_retail_products(
    fixtures_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = fixtures_dir / RETAIL_FILE
    products = json.loads(path.read_text(encoding="utf-8"))
    return products, {
        "file_hash": content_hash(path.read_bytes()),
        "verified_on": VERIFIED_ON,
    }


class ReplaySource:
    """replay 프로파일의 공개 자료원. 모든 결과에 source_mode=replay를 표시한다."""

    def __init__(self, fixtures_dir: Path) -> None:
        self.fixtures_dir = fixtures_dir
        self._seonheul: tuple[list[Observation], dict[str, Any]] | None = None
        self._kma184: tuple[list[Observation], dict[str, Any]] | None = None

    def seonheul(self) -> tuple[list[Observation], dict[str, Any]]:
        if self._seonheul is None:
            self._seonheul = load_seonheul(self.fixtures_dir)
        return self._seonheul

    def kma184(self) -> tuple[list[Observation], dict[str, Any]]:
        if self._kma184 is None:
            self._kma184 = load_kma184(self.fixtures_dir)
        return self._kma184

    def all_observations(self) -> list[Observation]:
        return self.seonheul()[0] + self.kma184()[0]

    def stations(self) -> list[dict[str, Any]]:
        current, _ = load_current_observations(self.fixtures_dir)
        return [
            {
                "source_id": "kma_aws",
                "station_code": s["station_code"],
                "station_name": s["station_name"],
                "altitude_m": float(s["altitude_m"]) if s["altitude_m"] is not None else None,
                "location": s["location"],
            }
            for s in current
        ] + [
            {
                "source_id": "jeju_579",
                "station_code": None,
                "station_name": "선흘",
                "altitude_m": None,
                "location": "제주특별자치도 제주시 조천읍 선흘리",
            }
        ]
