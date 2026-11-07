"""비식별 운영 로깅. 개인 원문·비밀·URL 쿼리를 기록하지 않는다 (SRS §12.5)."""

import logging
import re
from typing import cast

import structlog

_SECRET_PATTERN = re.compile(
    r"(serviceKey|authKey|apiKey|api_key|token|password|secret|projectKey)[=:]\s*\S+",
    re.IGNORECASE,
)


def redact(value: str) -> str:
    return _SECRET_PATTERN.sub(lambda m: f"{m.group(1)}=[REDACTED]", value)


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
