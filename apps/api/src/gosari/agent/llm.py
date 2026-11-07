"""GPT-6 Luna 클라이언트 — 공개 조건 계획·검증된 결과 설명만 (SRS §5.9).

키 미설정/차단 시 MODEL_UNAVAILABLE → 제한 모드(결정론 카드만).
개인 원문은 어떤 요청에도 포함하지 않는다.
"""

import json
import re
import threading
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from gosari.config import Settings, get_settings
from gosari.domain.errors import GosariError
from gosari.logging import get_logger

logger = get_logger(__name__)

OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def runtime_system_prompt(prompt: str, now: datetime | None = None) -> str:
    current = (now or datetime.now(ZoneInfo("Asia/Seoul"))).astimezone(ZoneInfo("Asia/Seoul"))
    weekday = ("월", "화", "수", "목", "금", "토", "일")[current.weekday()]
    return (
        f"현재 기준 날짜: {current:%Y-%m-%d} ({weekday}요일)\n"
        f"현재 기준 시각: {current:%H:%M:%S} (Asia/Seoul, UTC+09:00)\n"
        "오늘·내일·모레는 이 한국 시간 기준으로 해석하세요. "
        "입력에 명시된 날짜와 자료의 관측·발표·조사 시점은 그대로 유지하세요.\n\n"
        f"{prompt}"
    )


def public_model_data(value: Any) -> Any:
    """Allow numbers, fixed public terms and dates; never arbitrary user prose."""
    from gosari.agent import ALLOWED_OPERATIONS
    from gosari.sources.weather import JEJU_LOCATIONS

    terms = set(ALLOWED_OPERATIONS) | {
        "jeju_579",
        "jeju_578",
        "kma_aws",
        "kma_asos",
        "open_meteo",
        "at_settlement",
        "forestinfo",
        "retail_sample",
        "daily_rainfall",
        "average_temperature",
        "wind_speed",
        "low_rain",
        "mild_temperature",
        "low_wind",
        "common_valid_month_days",
        "count_positive_days",
        "day",
        "Asia/Seoul",
        "retail",
        "survey",
        "wholesale",
        "complete",
        "partial",
        "no_data",
        "fetched",
        "replay",
        "link",
        "forecast",
        "historical",
        "선흘",
        "제주",
        "제주(184)",
        "clear",
        "cloudy",
        "rain",
        "snow",
        "unknown",
        "kg",
        "g",
        "mm",
        "℃",
    }
    terms.update(str(part) for row in JEJU_LOCATIONS for part in row[:2])
    if isinstance(value, dict):
        return {
            str(key): public_model_data(item)
            for key, item in value.items()
            if re.fullmatch(r"[a-z_][a-z_0-9]*|\d{4}", str(key))
        }
    if isinstance(value, list):
        return [public_model_data(item) for item in value]
    if isinstance(value, str):
        return value if value in terms or re.fullmatch(r"[\d.,:T+Z /-]+", value) else None
    return value if value is None or isinstance(value, (bool, int, float)) else None


STRUCTURE_SYSTEM_PROMPT = """당신은 고사리잇의 공개 질문 구조화 도구입니다.
사용자의 공개 분석 질문을 아래 JSON 스키마의 QuerySpec으로 변환하세요.
허용 operation: history_compare, region_compare, current_observation,
forecast_compare, market_query, survey_link, retail_lookup, station_search.
개인 기록·별칭·정확 위치·연락처가 섞이면 {"private": true}만 반환하세요.
조건이 모호하면 {"clarify": ["질문1", ...]}를 반환하세요.
숫자 계산이나 자료 조회를 수행하지 마세요. JSON만 출력하세요."""

EXPLAIN_SYSTEM_PROMPT = """당신은 고사리잇의 결과 설명 도구입니다.
주어진 검증된 결정론 결과(JSON)의 핵심 차이를 한국어 한두 문장으로 설명하세요.
포함된 숫자·단위·기간·출처·시점을 바꾸지 마세요. 새로운 수치를 만들지 마세요.
고사리 출현량·수확량·채취 허가·안전도를 예측하거나 판정하지 마세요.
자료가 불완전하면 누락된 범위만 짧게 적으세요.
카드에 있는 출처·날짜를 반복하거나 서론·면책·권유·기술 용어를 덧붙이지 마세요."""


class LlmClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._local = threading.local()
        self._slots = threading.BoundedSemaphore(max(1, self.settings.model_concurrency))

    def begin_job(self) -> None:
        self._local.records = []
        self._local.remaining = self.settings.model_job_token_budget

    def usage_snapshot(self) -> dict[str, Any]:
        records = list(getattr(self._local, "records", []))
        sent = [record for record in records if record["request_sent"]]

        def total(field: str) -> int | None:
            values = [record.get(field) for record in sent]
            return sum(values) if all(isinstance(value, int) for value in values) else None

        return {
            "calls": len(sent),
            "usage_status": "not_used"
            if not sent
            else "reported"
            if all(record["usage_status"] == "reported" for record in sent)
            else "unknown",
            "input_tokens": total("input_tokens"),
            "output_tokens": total("output_tokens"),
            "reasoning_tokens": total("reasoning_tokens"),
            "provider_cached_input_tokens": total("provider_cached_input_tokens"),
            "total_tokens": total("total_tokens"),
            "token_budget": self.settings.model_job_token_budget,
            "remaining_token_budget": getattr(
                self._local, "remaining", self.settings.model_job_token_budget
            ),
            "elapsed_ms": sum(record["elapsed_ms"] for record in sent),
            "cost_status": "not_calculated",
            "cost_usd": None,
            "records": records,
        }

    def _post(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if not hasattr(self._local, "records"):
            self.begin_job()
        records = self._local.records
        remaining = self._local.remaining
        # 사전 검사는 UTF-8 바이트 기반 보수 추정이며 실제 provider usage와 분리한다.
        estimated_input = len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) + 256
        reservation = estimated_input + int(payload["max_completion_tokens"])
        if (
            remaining is None
            or reservation > remaining
            or len(records) >= self.settings.max_plan_steps
        ):
            raise GosariError("BUDGET_EXCEEDED", {"reason": "MODEL_JOB_BUDGET"})
        if not self._slots.acquire(blocking=False):
            raise GosariError("LOCAL_BUSY", {"retry_after_seconds": 1})
        started = time.monotonic()
        record: dict[str, Any] = {
            "model": self.settings.llm_model,
            "request_sent": True,
            "status": "failed",
            "usage_status": "unknown",
            "input_tokens_estimate": estimated_input,
            "input_tokens": None,
            "output_tokens": None,
            "reasoning_tokens": None,
            "provider_cached_input_tokens": None,
            "total_tokens": None,
            "elapsed_ms": 0,
        }
        try:
            response = httpx.post(
                OPENAI_URL,
                headers={"Authorization": f"Bearer {self.settings.resolved_openai_api_key}"},
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            usage = data.get("usage") if isinstance(data, dict) else None
            if isinstance(usage, dict):

                def count(value: Any) -> int | None:
                    return (
                        value
                        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
                        else None
                    )

                record["input_tokens"] = count(usage.get("prompt_tokens"))
                record["output_tokens"] = count(usage.get("completion_tokens"))
                record["total_tokens"] = count(usage.get("total_tokens"))
                output_details = usage.get("completion_tokens_details")
                input_details = usage.get("prompt_tokens_details")
                record["reasoning_tokens"] = (
                    count(output_details.get("reasoning_tokens"))
                    if isinstance(output_details, dict)
                    else None
                )
                record["provider_cached_input_tokens"] = (
                    count(input_details.get("cached_tokens"))
                    if isinstance(input_details, dict)
                    else None
                )
                input_tokens = record["input_tokens"]
                output_tokens = record["output_tokens"]
                total_tokens = record["total_tokens"]
                if (
                    input_tokens is not None
                    and output_tokens is not None
                    and total_tokens is not None
                    and total_tokens == input_tokens + output_tokens
                ):
                    record["usage_status"] = "reported"
                else:
                    record["total_tokens"] = None
            if not isinstance(data, dict):
                raise GosariError("MODEL_UNAVAILABLE")
            record["status"] = "completed"
            return data
        except httpx.HTTPError, ValueError, TypeError:
            raise GosariError("MODEL_UNAVAILABLE") from None
        finally:
            record["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            records.append(record)
            self._local.remaining = (
                max(0, remaining - record["total_tokens"])
                if record["total_tokens"] is not None
                else None
            )
            self._slots.release()
            logger.info("model usage", **record)

    @property
    def available(self) -> bool:
        return (
            bool(self.settings.resolved_openai_api_key) and self.settings.external_requests_enabled
        )

    def _chat(self, system: str, user: str, *, max_tokens: int = 1200) -> str:
        if not self.available:
            raise GosariError("MODEL_UNAVAILABLE")
        try:
            data = self._post(
                {
                    "model": self.settings.llm_model,
                    "messages": [
                        {"role": "system", "content": runtime_system_prompt(system)},
                        {"role": "user", "content": user},
                    ],
                    "max_completion_tokens": max_tokens,
                },
                60.0,
            )
            return str(data["choices"][0]["message"]["content"])
        except httpx.HTTPError as exc:
            logger.warning("llm call failed", error_type=type(exc).__name__)
            raise GosariError("MODEL_UNAVAILABLE") from None
        except KeyError, IndexError, ValueError:
            raise GosariError("MODEL_UNAVAILABLE") from None

    def structure_question(self, public_conditions: dict[str, Any]) -> dict[str, Any]:
        """Model chooses an allowed public tool; all conditions are locally rebuilt first."""
        if not self.available or not isinstance(public_conditions, dict):
            raise GosariError("MODEL_UNAVAILABLE")
        from gosari.agent import build_public_spec

        safe = build_public_spec(public_conditions)
        operation = safe["operation"]
        tool = {
            "type": "function",
            "function": {
                "name": "run_public_analysis",
                "description": "확인된 공개 조건의 분석 도구를 실행합니다.",
                "parameters": {
                    "type": "object",
                    "properties": {"operation": {"type": "string", "enum": [operation]}},
                    "required": ["operation"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        }
        try:
            data = self._post(
                {
                    "model": self.settings.llm_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": runtime_system_prompt(
                                "확인된 공개 조건만 사용하여 지정된 분석 도구를 호출하세요. "
                                "조건을 추가하거나 개인 자료를 요청하지 마세요."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(public_model_data(safe), ensure_ascii=False),
                        },
                    ],
                    "tools": [tool],
                    "reasoning_effort": "none",
                    "tool_choice": {
                        "type": "function",
                        "function": {"name": "run_public_analysis"},
                    },
                    "max_completion_tokens": 800,
                },
                30.0,
            )
            calls = data["choices"][0]["message"]["tool_calls"]
            if not isinstance(calls, list) or len(calls) != 1:
                raise GosariError("MODEL_UNAVAILABLE")
            call = calls[0]["function"]
            args = json.loads(call["arguments"])
            if call["name"] != "run_public_analysis" or args != {"operation": operation}:
                raise GosariError("MODEL_UNAVAILABLE")
            return safe
        except httpx.HTTPError, KeyError, IndexError, ValueError, TypeError:
            raise GosariError("MODEL_UNAVAILABLE") from None

    def explain(self, envelope_dict: dict[str, Any]) -> str:
        safe = {
            k: envelope_dict.get(k)
            for k in (
                "data_status",
                "source_mode",
                "requested_scope",
                "effective_scope",
                "observed_period",
                "verified_on",
                "result",
                "warnings",
            )
        }
        result = envelope_dict.get("result", {})
        try:
            proposed = self._chat(
                EXPLAIN_SYSTEM_PROMPT,
                json.dumps(public_model_data(safe), ensure_ascii=False, default=str),
            )
        except GosariError:
            return public_fact_summary(result)
        if explanation_matches(proposed, result):
            return proposed
        return public_fact_summary(result)


def explanation_matches(explanation: str, result: dict[str, Any]) -> bool:
    """자유문장의 숫자 집합만으로 연도·단위·허가 결론을 검증하지 않는다."""
    expected = public_fact_summary(result)
    return bool(expected) and explanation.strip() == expected


def public_fact_summary(result: dict[str, Any]) -> str:
    """검증된 결과 필드에 결합된 짧은 설명. 새 추론이나 임의 원문을 넣지 않는다."""
    for element, label, metric, unit in (
        ("daily_rainfall", "비가 온 날", "positive_days", "일"),
        ("average_temperature", "평균기온", "average", "℃"),
    ):
        data = result.get(element)
        if not isinstance(data, dict):
            continue
        common = data.get("common_day_count")
        periods = data.get("per_year", {})
        if not isinstance(common, int) or not isinstance(periods, dict):
            continue
        facts = []
        for year, values in sorted(periods.items()):
            if not re.fullmatch(r"\d{4}", str(year)) or not isinstance(values, dict):
                continue
            value = values.get(metric)
            if value is not None and re.fullmatch(r"-?\d+(?:\.\d+)?", str(value)):
                facts.append(f"{year}년 {value}{unit}")
        if facts:
            return f"공통 {common}일의 {label}: {' · '.join(facts)}."
    candidates = result.get("candidates")
    if isinstance(candidates, list) and candidates:
        return f"날짜와 시간별 후보 {len(candidates)}곳을 같은 기상 기준으로 비교했습니다."
    stations = result.get("stations")
    if isinstance(stations, list) and stations:
        return f"{len(stations)}개 지역의 기온과 강수 실황을 확인했습니다."
    return ""
