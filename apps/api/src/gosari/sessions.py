"""서버 세션 및 개인 기록 저장소 (PostgreSQL 18 영속화 지원 — 재방문·재시작 시 복원)."""

import logging
import secrets
import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg
import psycopg.sql
from psycopg.types.json import Jsonb

from gosari.config import Settings, get_settings
from gosari.db import connection, db_available
from gosari.domain.errors import GosariError
from gosari.personal import (
    ActionResult,
    Consent,
    NotebookEntry,
    PersonalContact,
    Preview,
    PrivateRegion,
    ShareDraft,
    ShareItem,
)

logger = logging.getLogger(__name__)


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_urlsafe(16)}"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Session:
    def __init__(self, settings: Settings, session_id: str | None = None) -> None:
        now = utcnow()
        self.session_id = session_id or new_id("sess")
        self.created_at = now
        self.expires_at = now + timedelta(seconds=settings.session_absolute_ttl)
        self.last_activity_at = now
        self.lifecycle = "active"
        self.onboarding_state = "welcome"
        self.active_conversation_id: str | None = None
        self.member_id: str | None = None
        self.login_id: str | None = None
        self.notebook: dict[str, NotebookEntry] = {}
        self.contacts: dict[str, PersonalContact] = {}
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
            self.contacts.clear()
            self.regions.clear()
            self.share_drafts.clear()
            self.previews.clear()
            self.consents.clear()
            self.actions.clear()
            self.jobs.clear()


class SessionStore:
    """PostgreSQL 18 (app_session + personal_* 3NF 테이블) 및 인메모리 캐시 연동 세션 저장소."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()

    def save(self, session: Session) -> None:
        if not db_available():
            if self._settings.resolved_db_password:
                raise GosariError("DATABASE_UNAVAILABLE")
            return
        with session.lock:
            try:
                with connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO app_session (
                            session_id, created_at, expires_at, last_activity_at,
                            lifecycle, member_id, control_state
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (session_id) DO UPDATE SET
                            expires_at = EXCLUDED.expires_at,
                            last_activity_at = EXCLUDED.last_activity_at,
                            lifecycle = EXCLUDED.lifecycle,
                            member_id = EXCLUDED.member_id,
                            control_state = EXCLUDED.control_state
                        """,
                        (
                            session.session_id,
                            session.created_at,
                            session.expires_at,
                            session.last_activity_at,
                            session.lifecycle,
                            session.member_id,
                            Jsonb(
                                {
                                    "previews": {
                                        key: value.model_dump(mode="json")
                                        for key, value in session.previews.items()
                                    },
                                    "consents": {
                                        key: value.model_dump(mode="json")
                                        for key, value in session.consents.items()
                                    },
                                    "actions": {
                                        key: value.model_dump(mode="json")
                                        for key, value in session.actions.items()
                                    },
                                    "onboarding_state": session.onboarding_state,
                                }
                            ),
                        ),
                    )
                    conn.execute(
                        "DELETE FROM personal_notebook_entry WHERE session_id = %s",
                        (session.session_id,),
                    )
                    for entry in session.notebook.values():
                        conn.execute(
                            """
                            INSERT INTO personal_notebook_entry (
                                record_id, session_id, revision, experience_date,
                                companion_aliases, activity_text, amount_value, amount_unit,
                                created_at, updated_at, location_address, latitude, longitude,
                                private_region_id, public_evidence_ids
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                entry.record_id,
                                session.session_id,
                                entry.revision,
                                entry.experience_date,
                                Jsonb(entry.companion_aliases),
                                entry.activity_text,
                                str(entry.amount_value) if entry.amount_value is not None else None,
                                entry.amount_unit,
                                entry.created_at,
                                entry.updated_at,
                                entry.location_address,
                                entry.latitude,
                                entry.longitude,
                                entry.private_region_id,
                                Jsonb(entry.public_evidence_ids),
                            ),
                        )
                    conn.execute(
                        "DELETE FROM personal_private_region WHERE session_id = %s",
                        (session.session_id,),
                    )
                    for reg in session.regions.values():
                        conn.execute(
                            """
                            INSERT INTO personal_private_region (
                                region_id, session_id, revision, kind,
                                public_area_code, coarse_grid, local_alias,
                                selected_station_mapping_ids, created_at, updated_at,
                                latitude, longitude, visited_on
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                reg.region_id,
                                session.session_id,
                                reg.revision,
                                reg.kind,
                                reg.public_area_code,
                                reg.coarse_grid,
                                reg.local_alias,
                                Jsonb(reg.selected_station_mapping_ids),
                                reg.created_at,
                                reg.updated_at,
                                reg.latitude,
                                reg.longitude,
                                reg.visited_on,
                            ),
                        )
                    conn.execute(
                        "DELETE FROM personal_share_draft WHERE session_id = %s",
                        (session.session_id,),
                    )
                    for draft in session.share_drafts.values():
                        conn.execute(
                            """
                            INSERT INTO personal_share_draft (
                                share_draft_id, session_id, revision, items,
                                message_enabled, editable_message, source_record_ids,
                                public_evidence_ids, prepared_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                draft.share_draft_id,
                                session.session_id,
                                draft.revision,
                                Jsonb([it.model_dump(mode="json") for it in draft.items]),
                                draft.message_enabled,
                                draft.editable_message,
                                Jsonb(draft.source_record_ids),
                                Jsonb(draft.public_evidence_ids),
                                draft.prepared_at,
                            ),
                        )
                    conn.execute(
                        "DELETE FROM personal_contact WHERE session_id = %s", (session.session_id,)
                    )
                    for contact in session.contacts.values():
                        conn.execute(
                            """INSERT INTO personal_contact
                            (contact_id, session_id, revision, name, relationship, notes,
                             created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                            (
                                contact.contact_id,
                                session.session_id,
                                contact.revision,
                                contact.name,
                                contact.relationship,
                                contact.notes,
                                contact.created_at,
                                contact.updated_at,
                            ),
                        )
                    conn.commit()
            except Exception as exc:
                logger.warning(
                    "personal session save failed", extra={"error_type": type(exc).__name__}
                )
                raise GosariError("DATABASE_UNAVAILABLE") from exc

    def _load_from_db(self, session_id: str) -> Session | None:
        if not db_available():
            if self._settings.resolved_db_password:
                raise GosariError("DATABASE_UNAVAILABLE")
            return None
        try:
            with connection() as conn:
                row = conn.execute(
                    """
                    SELECT s.session_id, s.created_at, s.expires_at, s.last_activity_at,
                           s.lifecycle, s.control_state, s.member_id, m.login_id
                    FROM app_session s
                    LEFT JOIN app_member m ON m.member_id = s.member_id
                    WHERE s.session_id = %s
                    """,
                    (session_id,),
                ).fetchone()
                if not row or row[4] != "active":
                    return None
                s = Session(self._settings, session_id=str(row[0]))
                s.member_id = str(row[6]) if len(row) > 6 and row[6] is not None else None
                s.login_id = str(row[7]) if len(row) > 7 and row[7] is not None else None
                s.created_at = (
                    row[1] if isinstance(row[1], datetime) else datetime.fromisoformat(str(row[1]))
                )
                s.expires_at = (
                    row[2] if isinstance(row[2], datetime) else datetime.fromisoformat(str(row[2]))
                )
                s.last_activity_at = (
                    row[3] if isinstance(row[3], datetime) else datetime.fromisoformat(str(row[3]))
                )
                s.lifecycle = str(row[4])
                state = row[5] if len(row) > 5 and isinstance(row[5], dict) else {}
                s.previews = {
                    key: Preview.model_validate(value)
                    for key, value in state.get("previews", {}).items()
                }
                s.consents = {
                    key: Consent.model_validate(value)
                    for key, value in state.get("consents", {}).items()
                }
                s.actions = {
                    key: ActionResult.model_validate(value)
                    for key, value in state.get("actions", {}).items()
                }
                s.onboarding_state = state.get("onboarding_state", "welcome")

                nb_rows = conn.execute(
                    """
                    SELECT record_id, revision, experience_date, companion_aliases,
                           activity_text, amount_value, amount_unit, created_at, updated_at,
                           location_address, latitude, longitude, private_region_id,
                           public_evidence_ids
                    FROM personal_notebook_entry
                    WHERE session_id = %s
                    ORDER BY experience_date DESC, created_at DESC
                    """,
                    (session_id,),
                ).fetchall()
                for nr in nb_rows:
                    exp_date = nr[2] if isinstance(nr[2], date) else date.fromisoformat(str(nr[2]))
                    s.notebook[str(nr[0])] = NotebookEntry(
                        record_id=str(nr[0]),
                        revision=int(nr[1]),
                        experience_date=exp_date,
                        companion_aliases=list(nr[3] or []),
                        activity_text=str(nr[4]),
                        amount_value=Decimal(str(nr[5])) if nr[5] is not None else None,
                        amount_unit=str(nr[6]) if nr[6] is not None else None,
                        location_address=str(nr[9]) if len(nr) > 9 and nr[9] is not None else None,
                        latitude=float(nr[10]) if len(nr) > 10 and nr[10] is not None else None,
                        longitude=float(nr[11]) if len(nr) > 11 and nr[11] is not None else None,
                        private_region_id=str(nr[12])
                        if len(nr) > 12 and nr[12] is not None
                        else None,
                        public_evidence_ids=list(nr[13] or []) if len(nr) > 13 else [],
                        created_at=nr[7]
                        if isinstance(nr[7], datetime)
                        else datetime.fromisoformat(str(nr[7])),
                        updated_at=nr[8]
                        if isinstance(nr[8], datetime)
                        else datetime.fromisoformat(str(nr[8])),
                    )

                reg_rows = conn.execute(
                    """
                    SELECT region_id, revision, kind, public_area_code, coarse_grid,
                           local_alias, selected_station_mapping_ids, created_at, updated_at,
                           latitude, longitude, visited_on
                    FROM personal_private_region
                    WHERE session_id = %s
                    ORDER BY created_at DESC
                    """,
                    (session_id,),
                ).fetchall()
                for rr in reg_rows:
                    s.regions[str(rr[0])] = PrivateRegion(
                        region_id=str(rr[0]),
                        revision=int(rr[1]),
                        kind="existing" if rr[2] == "existing" else "interest",
                        public_area_code=str(rr[3]) if rr[3] is not None else None,
                        coarse_grid=str(rr[4]) if rr[4] is not None else None,
                        latitude=float(rr[9]) if len(rr) > 9 and rr[9] is not None else None,
                        longitude=float(rr[10]) if len(rr) > 10 and rr[10] is not None else None,
                        visited_on=(
                            rr[11] if isinstance(rr[11], date) else date.fromisoformat(str(rr[11]))
                        )
                        if len(rr) > 11 and rr[11] is not None
                        else None,
                        local_alias=str(rr[5]),
                        selected_station_mapping_ids=list(rr[6] or []),
                        created_at=rr[7]
                        if isinstance(rr[7], datetime)
                        else datetime.fromisoformat(str(rr[7])),
                        updated_at=rr[8]
                        if isinstance(rr[8], datetime)
                        else datetime.fromisoformat(str(rr[8])),
                    )

                sh_rows = conn.execute(
                    """
                    SELECT share_draft_id, revision, items, message_enabled,
                           editable_message, source_record_ids, public_evidence_ids, prepared_at
                    FROM personal_share_draft
                    WHERE session_id = %s
                    ORDER BY prepared_at DESC
                    """,
                    (session_id,),
                ).fetchall()
                for sr in sh_rows:
                    s.share_drafts[str(sr[0])] = ShareDraft(
                        share_draft_id=str(sr[0]),
                        revision=int(sr[1]),
                        items=[ShareItem.model_validate(it) for it in (sr[2] or [])],
                        message_enabled=bool(sr[3]),
                        editable_message=str(sr[4]) if sr[4] is not None else None,
                        source_record_ids=list(sr[5] or []),
                        public_evidence_ids=list(sr[6] or []),
                        prepared_at=sr[7]
                        if isinstance(sr[7], datetime)
                        else datetime.fromisoformat(str(sr[7])),
                    )
                contact_rows = conn.execute(
                    """SELECT contact_id, revision, name, relationship, notes,
                    created_at, updated_at
                    FROM personal_contact WHERE session_id = %s ORDER BY name""",
                    (session_id,),
                ).fetchall()
                for contact in contact_rows:
                    s.contacts[str(contact[0])] = PersonalContact(
                        contact_id=str(contact[0]),
                        revision=int(contact[1]),
                        name=str(contact[2]),
                        relationship=str(contact[3]),
                        notes=str(contact[4] or ""),
                        created_at=contact[5]
                        if isinstance(contact[5], datetime)
                        else datetime.fromisoformat(str(contact[5])),
                        updated_at=contact[6]
                        if isinstance(contact[6], datetime)
                        else datetime.fromisoformat(str(contact[6])),
                    )
                return s
        except Exception as exc:
            logger.warning("personal session load failed", extra={"error_type": type(exc).__name__})
            raise GosariError("DATABASE_UNAVAILABLE") from exc

    def create(self) -> Session:
        with self._lock:
            self._sweep()
            session = Session(self._settings)
            self.save(session)
            self._sessions[session.session_id] = session
            return session

    def get_or_create(self, session_id: str | None) -> Session:
        if session_id:
            try:
                return self.get(session_id)
            except GosariError as exc:
                if exc.code not in {"SESSION_REQUIRED", "SESSION_EXPIRED"}:
                    raise
        return self.create()

    def get(self, session_id: str | None) -> Session:
        if not session_id:
            raise GosariError("SESSION_REQUIRED")
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = self._load_from_db(session_id)
                if session is not None:
                    self._sessions[session_id] = session
        if session is None:
            raise GosariError("SESSION_REQUIRED")
        session.touch()
        return session

    def end(self, session_id: str | None) -> None:
        session = self.get(session_id)
        # Match _sweep's store -> session lock order. Delete only after any active
        # commit/save has completed, so its UPSERT cannot recreate a deleted row.
        with self._lock, session.lock:
            session.touch()
            if db_available():
                try:
                    with connection() as conn:
                        conn.execute(
                            "DELETE FROM app_session WHERE session_id = %s",
                            (session.session_id,),
                        )
                        conn.commit()
                except Exception as exc:
                    logger.warning(
                        "personal session delete failed", extra={"error_type": type(exc).__name__}
                    )
                    raise GosariError("DATABASE_UNAVAILABLE") from exc
            elif self._settings.resolved_db_password:
                raise GosariError("DATABASE_UNAVAILABLE")
            session.close()
            self._sessions.pop(session.session_id, None)

    def find_member_session(self, member_id: str) -> Session | None:
        """회원의 기본 세션(가장 먼저 연결된 활성 세션)을 찾는다."""
        with self._lock:
            cached = sorted(
                (
                    s
                    for s in self._sessions.values()
                    if s.member_id == member_id and s.lifecycle == "active"
                ),
                key=lambda s: s.created_at,
            )
            if cached:
                return cached[0]
        if not db_available():
            if self._settings.resolved_db_password:
                raise GosariError("DATABASE_UNAVAILABLE")
            return None
        try:
            with connection() as conn:
                row = conn.execute(
                    """SELECT session_id FROM app_session
                    WHERE member_id = %s AND lifecycle = 'active'
                    ORDER BY created_at ASC LIMIT 1""",
                    (member_id,),
                ).fetchone()
        except Exception as exc:
            logger.warning("member session lookup failed", extra={"error_type": type(exc).__name__})
            raise GosariError("DATABASE_UNAVAILABLE") from exc
        if not row:
            return None
        try:
            return self.get(str(row[0]))
        except GosariError:
            return None

    def attach_member(self, session: Session, member_id: str, login_id: str) -> Session:
        """현재 세션을 회원에 연결한다. 회원의 기본 세션이 따로 있으면 현재 세션의 개인 기록을
        그 세션으로 합치고 현재 세션은 종료한다. 반환값이 이후 쿠키에 실릴 세션이다."""
        home = self.find_member_session(member_id)
        if home is None or home.session_id == session.session_id:
            with session.lock:
                session.member_id = member_id
                session.login_id = login_id
                self.save(session)
            return session
        with self._lock, home.lock, session.lock:
            session.touch()
            # 개인 기록의 기본키는 세션과 무관하게 전역이므로, 익명 세션의 행을 먼저 회원 세션으로
            # 옮긴 뒤 회원 세션을 저장해야 같은 키가 두 번 들어가지 않는다.
            self._rekey_rows(session.session_id, home.session_id)
            home.notebook.update(session.notebook)
            home.contacts.update(session.contacts)
            home.regions.update(session.regions)
            home.share_drafts.update(session.share_drafts)
            home.login_id = login_id
            self.save(home)
            session.close()
            self._sessions.pop(session.session_id, None)
        return home

    def _rekey_rows(self, source_session_id: str, target_session_id: str) -> None:
        """익명 세션의 개인 기록 행을 회원 세션으로 옮기고 익명 세션 행을 지운다 (단일 트랜잭션)."""
        if not db_available():
            if self._settings.resolved_db_password:
                raise GosariError("DATABASE_UNAVAILABLE")
            return
        try:
            with connection() as conn:
                for table in (
                    "personal_notebook_entry",
                    "personal_private_region",
                    "personal_share_draft",
                    "personal_contact",
                ):
                    conn.execute(
                        psycopg.sql.SQL(
                            "UPDATE {} SET session_id = %s WHERE session_id = %s"
                        ).format(psycopg.sql.Identifier(table)),
                        (target_session_id, source_session_id),
                    )
                conn.execute("DELETE FROM app_session WHERE session_id = %s", (source_session_id,))
                conn.commit()
        except Exception as exc:
            logger.warning(
                "personal session merge failed", extra={"error_type": type(exc).__name__}
            )
            raise GosariError("DATABASE_UNAVAILABLE") from exc

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
