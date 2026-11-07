"""Keep personal input outside the public conversation model and shared caches."""

import re

from gosari.agent import PERSONAL_HINT_MARKERS

_PRIVATE_VALUES = re.compile(
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"
    r"|(?:\+?82[- ]?)?01[016789][- ]?\d{3,4}[- ]?\d{4}"
    r"|\b\d{2,3}\.\d{3,}\s*[,/ ]\s*\d{2,3}\.\d{3,}\b"
    r"|(?:[가-힣]+(?:로|길)\s*\d+(?:-\d+)?|\d+동\s*\d+호)"
    r"|(?:/Users/|/home/|[A-Z]:\\Users\\)"
    r"|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_PRIVATE_MARKERS = tuple(
    marker
    for marker in PERSONAL_HINT_MARKERS
    if marker not in {"그곳", "그때", "내 수첩", "나의 기록"}
)
_FAMILY = re.compile(r"엄마|어머니|아빠|아버지|할머니|할아버지|남편|아내|동생|누나|언니|오빠")
_PERSONAL_ENTITY = re.compile(
    r"수첩|지인|관심\s*지역|방문\s*지역|스팟|나눔\s*이력|나의\s*기록|내\s*기록"
)


def contains_sensitive_dialogue(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    return (
        any(re.sub(r"\s+", "", marker) in compact for marker in _PRIVATE_MARKERS)
        or bool(_FAMILY.search(text))
        or bool(_PRIVATE_VALUES.search(text))
    )


def requires_private_dialogue(text: str) -> bool:
    """Exclude personal references from shared plans, even without private values."""
    return contains_sensitive_dialogue(text) or bool(_PERSONAL_ENTITY.search(text))
