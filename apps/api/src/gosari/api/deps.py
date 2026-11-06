"""세션·CSRF 검사 헬퍼. 클라이언트 본문 session_id를 신뢰하지 않는다."""

from typing import Any
from urllib.parse import urlsplit

from litestar import Request

from gosari.domain.errors import GosariError
from gosari.sessions import Session, get_session_store

SESSION_COOKIE = "gosari_session"


def current_session(request: Request[Any, Any, Any]) -> Session:
    session_id = request.cookies.get(SESSION_COOKIE)
    return get_session_store().get(session_id)


def check_origin(request: Request[Any, Any, Any]) -> None:
    """localhost CSRF/재바인딩 방어 — 변경 요청의 Origin/Host를 검사한다."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("origin")
    host = request.headers.get("host", "")
    if origin:
        origin_host = urlsplit(origin).netloc
        if origin_host != host:
            raise GosariError("ORIGIN_DENIED")
    hostname = urlsplit(f"http://{host}").hostname or ""
    # 바인딩이 아니라 허용 호스트 이름 검사다 (Compose 내부 DNS app 포함).
    if hostname not in ("127.0.0.1", "localhost", "::1", "0.0.0.0", "app", ""):  # noqa: S104
        raise GosariError("ORIGIN_DENIED")
