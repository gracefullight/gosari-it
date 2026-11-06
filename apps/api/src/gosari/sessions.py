"""격리된 로컬 세션 저장소 (SRS §9.3). 휘발성 RAM 한정, 불투명 ID, 소유권 전면 검사."""

import secrets
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from gosari.config import Settings, get_settings
from gosari.domain.errors import GosariError
from gosari.personal import (
    ActionResult,
    Consent,
    NotebookEntry,
    Preview,
    PrivateRegion,
    ShareDraft,
)


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_urlsafe(16)}"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Session:
    def __init__(self, settings: Settings) -> None:
        now = utcnow()
        self.session_id = new_id("sess")
        self.created_at = now
        self.expires_at = now + timedelta(seconds=settings.session_absolute_ttl)
        self.last_activity_at = now
        self.lifecycle = "active"
        self.onboarding_state = "welcome"
        self.active_conversation_id: str | None = None
        self.notebook: dict[str, NotebookEntry] = {}
        self.regions: dict[str, PrivateRegion] = {}
        self.share_drafts: dict[str, ShareDraft] = {}
        self.previews: dict[str, Preview] = {}
        self.consents: dict[str, Consent] = {}
        self.actions: dict[str, ActionResult] = {}
        self.jobs: dict[str, dict[str, Any]] = {}
        self.lock = threading.RLock()
        self._idle_ttl = settings.session_idle_ttl

    def touch(self) -> None:
        now = utcnow()
        if self.lifecycle != "active":
            raise GosariError("SESSION_EXPIRED")
        if now > self.expires_at or now - self.last_activity_at > timedelta(seconds=self._idle_ttl):
            self.lifecycle = "expired"
            raise GosariError("SESSION_EXPIRED")
        self.last_activity_at = now

    def close(self) -> None:
        with self.lock:
            self.lifecycle = "closed"
            self.notebook.clear()
            self.regions.clear()
            self.share_drafts.clear()
            self.previews.clear()
            self.consents.clear()
            self.actions.clear()
            self.jobs.clear()


class SessionStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()

    def create(self) -> Session:
        with self._lock:
            self._sweep()
            session = Session(self._settings)
            self._sessions[session.session_id] = session
            return session

    def get(self, session_id: str | None) -> Session:
        if not session_id:
            raise GosariError("SESSION_REQUIRED")
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise GosariError("SESSION_REQUIRED")
        session.touch()
        return session

    def end(self, session_id: str | None) -> None:
        session = self.get(session_id)
        with self._lock:
            session.close()
            self._sessions.pop(session.session_id, None)

    def _sweep(self) -> None:
        now = utcnow()
        expired = [
            sid
            for sid, s in self._sessions.items()
            if s.lifecycle != "active"
            or now > s.expires_at
            or now - s.last_activity_at > timedelta(seconds=s._idle_ttl)
        ]
        for sid in expired:
            self._sessions[sid].close()
            del self._sessions[sid]


_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store
