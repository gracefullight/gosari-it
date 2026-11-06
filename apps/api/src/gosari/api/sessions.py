"""세션 생성·종료. 개인 데이터는 세션 메모리 한정."""

from typing import Any

from litestar import Controller, Request, delete, post
from litestar.response import Response

from gosari.api.deps import SESSION_COOKIE, check_origin, current_session
from gosari.config import get_settings
from gosari.sessions import get_session_store


class SessionsController(Controller):
    path = "/sessions"

    @post("/")
    async def create(self, request: Request[Any, Any, Any]) -> Response[dict[str, Any]]:
        check_origin(request)
        settings = get_settings()
        session = get_session_store().create()
        response = Response(
            {
                "session_id": session.session_id,
                "created_at": session.created_at.isoformat(),
                "expires_at": session.expires_at.isoformat(),
                "idle_ttl_seconds": settings.session_idle_ttl,
                "notice": "개인 기록은 현재 세션에서만 유지되며 "
                "종료·만료·재시작 시 복구되지 않습니다.",
            },
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

    @delete("/current", status_code=200)
    async def end(self, request: Request[Any, Any, Any]) -> Response[dict[str, Any]]:
        check_origin(request)
        session = current_session(request)
        get_session_store().end(session.session_id)
        response = Response(
            {
                "status": "closed",
                "notice": "세션의 개인 기록·초안·승인이 정리되었습니다.",
            }
        )
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response
