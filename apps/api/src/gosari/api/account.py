"""회원 가입·로그인·로그아웃. 로그인하면 익명 세션의 개인 기록을 회원 세션으로 합친다."""

import threading
import time
from collections import deque
from typing import Any

from litestar import Controller, Request, get, post
from litestar.response import Response
from pydantic import BaseModel, Field

from gosari.api.deps import SESSION_COOKIE, check_origin, current_session
from gosari.config import get_settings
from gosari.domain.errors import GosariError
from gosari.members import Member, get_member_store
from gosari.sessions import Session, get_session_store

AUTH_ATTEMPT_LIMIT = 10
AUTH_ATTEMPT_WINDOW = 300.0


class _AttemptLimiter:
    """클라이언트 주소별 가입·로그인 시도 횟수를 창 단위로 제한한다."""

    def __init__(
        self, limit: int = AUTH_ATTEMPT_LIMIT, window: float = AUTH_ATTEMPT_WINDOW
    ) -> None:
        self._limit = limit
        self._window = window
        self._attempts: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._attempts.setdefault(key, deque())
            while bucket and now - bucket[0] > self._window:
                bucket.popleft()
            if len(bucket) >= self._limit:
                raise GosariError("LOCAL_BUSY")
            bucket.append(now)

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()


limiter = _AttemptLimiter()


class CredentialsBody(BaseModel):
    login_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class AccountState(BaseModel):
    """현재 세션의 회원 상태. 익명이면 login_id가 비어 있다."""

    login_id: str | None
    session_id: str
    merged: dict[str, int] = Field(default_factory=dict)


def _client_key(request: Request[Any, Any, Any]) -> str:
    return request.client.host if request.client else "unknown"


def _state(session: Session, merged: dict[str, int] | None = None) -> AccountState:
    return AccountState(
        login_id=session.login_id, session_id=session.session_id, merged=merged or {}
    )


def _with_cookie(session: Session, body: AccountState, status_code: int) -> Response[AccountState]:
    response = Response(body, status_code=status_code, headers={"Cache-Control": "no-store"})
    response.set_cookie(
        SESSION_COOKIE,
        session.session_id,
        httponly=True,
        samesite="strict",
        secure=False,
        path="/",
        max_age=get_settings().session_absolute_ttl,
    )
    return response


def _attach(session: Session, member: Member) -> tuple[Session, dict[str, int]]:
    before = {
        "notebook": len(session.notebook),
        "regions": len(session.regions),
        "contacts": len(session.contacts),
    }
    home = get_session_store().attach_member(session, member.member_id, member.login_id)
    merged = before if home.session_id != session.session_id else {}
    return home, merged


class AccountController(Controller):
    path = "/account"

    @get("/", sync_to_thread=True)
    def me(self, request: Request[Any, Any, Any]) -> Response[AccountState]:
        session = current_session(request)
        return Response(_state(session), headers={"Cache-Control": "no-store"})

    @post("/signup", sync_to_thread=True, status_code=201)
    def signup(
        self, request: Request[Any, Any, Any], data: CredentialsBody
    ) -> Response[AccountState]:
        check_origin(request)
        session = current_session(request)
        if session.member_id:
            raise GosariError("ACTION_NOT_ALLOWED")
        limiter.check(_client_key(request))
        member = get_member_store().create(data.login_id.strip().lower(), data.password)
        home, merged = _attach(session, member)
        return _with_cookie(home, _state(home, merged), 201)

    @post("/login", sync_to_thread=True, status_code=200)
    def login(
        self, request: Request[Any, Any, Any], data: CredentialsBody
    ) -> Response[AccountState]:
        check_origin(request)
        session = current_session(request)
        limiter.check(_client_key(request))
        member = get_member_store().authenticate(data.login_id.strip().lower(), data.password)
        if session.member_id and session.member_id != member.member_id:
            raise GosariError("ACTION_NOT_ALLOWED")
        home, merged = _attach(session, member)
        return _with_cookie(home, _state(home, merged), 200)

    @post("/logout", sync_to_thread=True, status_code=200)
    def logout(self, request: Request[Any, Any, Any]) -> Response[AccountState]:
        """회원 세션은 그대로 두고 새 익명 세션을 발급한다."""
        check_origin(request)
        current_session(request)
        fresh = get_session_store().create()
        return _with_cookie(fresh, _state(fresh), 200)
