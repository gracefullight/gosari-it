"""SRS §10.2 값 해석 순서: 원문 보존 → 의미 검사 → 파싱 → 단위 → 상태 부여."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from gosari.domain import ValueState


@dataclass(frozen=True)
class InterpretedValue:
    raw: str | None
    numeric: Decimal | None
    state: ValueState
    error_code: str | None = None


def interpret_numeric(
    raw: str | None, *, blank_state: ValueState = ValueState.UNRESOLVED_BLANK
) -> InterpretedValue:
    """숫자 0은 valid_zero, 의미 미확정 공란은 unresolved_blank. 공란을 0으로 치환하지 않는다."""
    if raw is None:
        return InterpretedValue(raw=None, numeric=None, state=ValueState.MISSING)
    text = raw.strip()
    if text == "":
        return InterpretedValue(raw=raw, numeric=None, state=blank_state)
    try:
        value = Decimal(text)
    except InvalidOperation:
        return InterpretedValue(
            raw=raw, numeric=None, state=ValueState.ERROR, error_code="PARSE_FAILED"
        )
    if not value.is_finite():
        return InterpretedValue(
            raw=raw, numeric=None, state=ValueState.ERROR, error_code="NON_FINITE"
        )
    if value == 0:
        return InterpretedValue(raw=raw, numeric=value, state=ValueState.VALID_ZERO)
    return InterpretedValue(raw=raw, numeric=value, state=ValueState.VALID)


def is_usable(state: ValueState) -> bool:
    return state in (ValueState.VALID, ValueState.VALID_ZERO)
