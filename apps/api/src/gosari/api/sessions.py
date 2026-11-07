"""세션 생성·종료. 개인 데이터는 세션 메모리 한정."""

from typing import Any

from litestar import Controller, Request, delete, post
from litestar.response import Response

from gosari.api.deps import SESSION_COOKIE, SESSION_HEADER, check_origin, current_session
from gosari.config import get_settings
from gosari.domain.envelope import SessionClosed, SessionCreated
from gosari.sessions import get_session_store


class SessionsController(Controller):
    path = "/sessions"

    @post("/", sync_to_thread=True)
    def create(self, request: Request[Any, Any, Any]) -> Response[SessionCreated]:
        check_origin(request)
        settings = get_settings()
        existing_sid = request.cookies.get(SESSION_COOKIE) or request.headers.get(SESSION_HEADER)
        session = get_session_store().get_or_create(existing_sid)
        response = Response(
            SessionCreated(
                session_id=session.session_id,
                created_at=session.created_at,
                expires_at=session.expires_at,
                idle_ttl_seconds=settings.session_idle_ttl,
                notice="",
            ),
            status_code=201,
        )
        response.set_cookie(
            SESSION_COOKIE,
            session.session_id,
            httponly=True,
            samesite="strict",
            secure=False,
            path="/",
            max_age=settings.session_absolute_ttl,
        )
        return response

    @delete("/current", sync_to_thread=True, status_code=200)
    def end(self, request: Request[Any, Any, Any]) -> Response[SessionClosed]:
        check_origin(request)
        session = current_session(request)
        get_session_store().end(session.session_id)
        response = Response(
            SessionClosed(
                status="closed",
                notice="개인 기록이 삭제되었습니다.",
            )
        )
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response
