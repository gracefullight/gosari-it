"""회원 계정 저장소. 비밀번호는 Argon2id 해시로만 보관하고 로그에 남기지 않는다."""

import logging
import re
import threading
from dataclasses import dataclass
from datetime import datetime

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from gosari.config import Settings, get_settings
from gosari.db import connection, db_available
from gosari.domain.errors import GosariError
from gosari.sessions import new_id, utcnow

logger = logging.getLogger(__name__)

LOGIN_ID_PATTERN = re.compile(r"^[a-z0-9_]{3,32}$")
PASSWORD_MIN = 8
PASSWORD_MAX = 128

_hasher = PasswordHasher()


@dataclass(frozen=True)
class Member:
    member_id: str
    login_id: str
    created_at: datetime


def validate_credentials(login_id: str, password: str) -> None:
    fields: list[str] = []
    if not LOGIN_ID_PATTERN.fullmatch(login_id):
        fields.append("login_id")
    if not (PASSWORD_MIN <= len(password) <= PASSWORD_MAX):
        fields.append("password")
    if fields:
        raise GosariError("INVALID_INPUT", {"fields": fields})


class MemberStore:
    """PostgreSQL app_member 저장소. DB가 없고 비밀번호 설정도 없으면 인메모리로 동작한다."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._memory: dict[str, tuple[Member, str]] = {}
        self._lock = threading.RLock()

    def _db(self) -> bool:
        if db_available():
            return True
        if self._settings.resolved_db_password:
            raise GosariError("DATABASE_UNAVAILABLE")
        return False

    def create(self, login_id: str, password: str) -> Member:
        validate_credentials(login_id, password)
        member = Member(member_id=new_id("mem"), login_id=login_id, created_at=utcnow())
        password_hash = _hasher.hash(password)
        if not self._db():
            with self._lock:
                if login_id in self._memory:
                    raise GosariError("LOGIN_ID_TAKEN")
                self._memory[login_id] = (member, password_hash)
            return member
        try:
            with connection() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM app_member WHERE login_id = %s", (login_id,)
                ).fetchone()
                if exists:
                    raise GosariError("LOGIN_ID_TAKEN")
                conn.execute(
                    """INSERT INTO app_member (member_id, login_id, password_hash, created_at)
                    VALUES (%s, %s, %s, %s)""",
                    (member.member_id, login_id, password_hash, member.created_at),
                )
                conn.commit()
        except GosariError:
            raise
        except Exception as exc:
            logger.warning("member create failed", extra={"error_type": type(exc).__name__})
            raise GosariError("DATABASE_UNAVAILABLE") from exc
        return member

    def authenticate(self, login_id: str, password: str) -> Member:
        if not LOGIN_ID_PATTERN.fullmatch(login_id) or not password:
            raise GosariError("LOGIN_FAILED")
        if not self._db():
            with self._lock:
                found = self._memory.get(login_id)
            if found is None:
                raise GosariError("LOGIN_FAILED")
            member, password_hash = found
            self._verify(password_hash, password)
            return member
        try:
            with connection() as conn:
                row = conn.execute(
                    """SELECT member_id, login_id, password_hash, created_at
                    FROM app_member WHERE login_id = %s""",
                    (login_id,),
                ).fetchone()
                if not row:
                    raise GosariError("LOGIN_FAILED")
                self._verify(str(row[2]), password)
                conn.execute(
                    "UPDATE app_member SET last_login_at = %s WHERE member_id = %s",
                    (utcnow(), str(row[0])),
                )
                conn.commit()
                created = (
                    row[3] if isinstance(row[3], datetime) else datetime.fromisoformat(str(row[3]))
                )
                return Member(member_id=str(row[0]), login_id=str(row[1]), created_at=created)
        except GosariError:
            raise
        except Exception as exc:
            logger.warning("member login failed", extra={"error_type": type(exc).__name__})
            raise GosariError("DATABASE_UNAVAILABLE") from exc

    @staticmethod
    def _verify(password_hash: str, password: str) -> None:
        try:
            _hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError) as exc:
            raise GosariError("LOGIN_FAILED") from exc


_store: MemberStore | None = None


def get_member_store() -> MemberStore:
    global _store
    if _store is None:
        _store = MemberStore()
    return _store
