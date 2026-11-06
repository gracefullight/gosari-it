"""GPT-6 Luna 클라이언트 — 공개 조건 계획·검증된 결과 설명만 (SRS §5.9).

키 미설정/차단 시 MODEL_UNAVAILABLE → 제한 모드(결정론 카드만).
개인 원문은 어떤 요청에도 포함하지 않는다.
"""

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from gosari.config import Settings, get_settings
from gosari.domain.errors import GosariError
from gosari.logging import get_logger

logger = get_logger(__name__)

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

STRUCTURE_SYSTEM_PROMPT = """당신은 고사리잇의 공개 질문 구조화 도구입니다.
사용자의 공개 분석 질문을 아래 JSON 스키마의 QuerySpec으로 변환하세요.
허용 operation: history_compare, region_compare, current_observation,
forecast_compare, market_query, survey_link, retail_lookup, station_search.
개인 기록·별칭·정확 위치·연락처가 섞이면 {"private": true}만 반환하세요.
조건이 모호하면 {"clarify": ["질문1", ...]}를 반환하세요.
숫자 계산이나 자료 조회를 수행하지 마세요. JSON만 출력하세요."""

EXPLAIN_SYSTEM_PROMPT = """당신은 고사리잇의 결과 설명 도구입니다.
주어진 검증된 결정론 결과(JSON)만 근거로 한국어로 짧게 설명하세요.
포함된 숫자·단위·기간·출처·시점을 바꾸지 마세요. 새로운 수치를 만들지 마세요.
고사리 출현량·수확량·채취 허가·안전도를 예측하거나 판정하지 마세요.
자료의 한계(분모·공통기간·재생 여부)를 한 문장으로 알리세요."""


class LlmClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def available(self) -> bool:
        return (
            bool(self.settings.resolved_openai_api_key) and self.settings.external_requests_enabled
        )

    def _chat(self, system: str, user: str, *, max_tokens: int = 1200) -> str:
        if not self.available:
            raise GosariError("MODEL_UNAVAILABLE")
        key = self.settings.resolved_openai_api_key
        try:
            response = httpx.post(
                OPENAI_URL,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": self.settings.llm_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "max_completion_tokens": max_tokens,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            return str(data["choices"][0]["message"]["content"])
        except httpx.HTTPError as exc:
            logger.warning("llm call failed", error_type=type(exc).__name__)
            raise GosariError("MODEL_UNAVAILABLE") from None
        except KeyError, IndexError, ValueError:
            raise GosariError("MODEL_UNAVAILABLE") from None

    def structure_question(self, safe_text: str) -> dict[str, Any]:
        content = self._chat(STRUCTURE_SYSTEM_PROMPT, safe_text)
        try:
            parsed = json.loads(content)
        except ValueError:
            raise GosariError("MODEL_UNAVAILABLE") from None
        if not isinstance(parsed, dict):
            raise GosariError("MODEL_UNAVAILABLE")
        return parsed

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
        return self._chat(EXPLAIN_SYSTEM_PROMPT, json.dumps(safe, ensure_ascii=False, default=str))


def explanation_matches(explanation: str, result: dict[str, Any]) -> bool:
    """§10.8 설명 대조: 설명에 등장하는 숫자가 결정론 결과에 없으면 실패 처리."""
    numbers = re.findall(r"\d+(?:\.\d+)?", explanation)
    if not numbers:
        return True
    result_text = json.dumps(result, ensure_ascii=False, default=str)
    result_numbers = set(re.findall(r"\d+(?:\.\d+)?", result_text))
    for number in numbers:
        if number in result_numbers:
            continue
        try:
            if str(Decimal(number).normalize()) in {
                str(Decimal(r).normalize()) for r in result_numbers
            }:
                continue
        except InvalidOperation:
            pass
        return False
    return True
