"""Named user accounts (Phase 2) persisted in the ``users`` table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlmodel import Session, col, select

from leagent.db.models.identity_stub import UserStub as UserAccount
from leagent.services.auth.service import LOCAL_USER_ID
from leagent.utils.crypto import hash_password, verify_password


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class UserRecord:
    user_id: UUID
    username: str
    display_name: str
    role: str
    disabled: bool
    is_superuser: bool

    def to_api(self) -> dict[str, Any]:
        return {
            "id": str(self.user_id),
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "disabled": self.disabled,
            "is_superuser": self.is_superuser,
            "permissions": ["*"] if self.is_superuser else [],
            "roles": [self.role],
        }


def _row_to_record(row: UserAccount) -> UserRecord:
    role = (row.role or "user").strip() or "user"
    is_admin = role == "admin" or row.id == LOCAL_USER_ID
    return UserRecord(
        user_id=row.id,
        username=(row.username or ("admin" if is_admin else str(row.id)[:8])),
        display_name=(row.display_name or row.username or "User"),
        role="admin" if is_admin else role,
        disabled=bool(row.disabled),
        is_superuser=is_admin,
    )


def _sync_session() -> Session | None:
    """Open a short-lived sync Session against the app database."""
    try:
        from leagent.config.settings import get_settings
        from sqlalchemy import create_engine

        settings = get_settings()
        url = settings.database.sync_url
        engine = create_engine(url)
        return Session(engine)
    except Exception:  # noqa: BLE001
        return None


def ensure_users_schema() -> None:
    """Best-effort create/alter for expanded user columns (SQLite-friendly)."""
    session = _sync_session()
    if session is None:
        return
    try:
        bind = session.get_bind()
        UserAccount.metadata.create_all(bind, tables=[UserAccount.__table__])
        # Additive columns for pre-existing stub rows (SQLite).
        from sqlalchemy import inspect, text

        insp = inspect(bind)
        if "users" not in insp.get_table_names():
            return
        existing = {c["name"] for c in insp.get_columns("users")}
        alters: list[str] = []
        if "username" not in existing:
            alters.append("ALTER TABLE users ADD COLUMN username VARCHAR(128)")
        if "password_hash" not in existing:
            alters.append("ALTER TABLE users ADD COLUMN password_hash VARCHAR(512)")
        if "display_name" not in existing:
            alters.append("ALTER TABLE users ADD COLUMN display_name VARCHAR(256)")
        if "role" not in existing:
            alters.append("ALTER TABLE users ADD COLUMN role VARCHAR(32) DEFAULT 'user'")
        if "disabled" not in existing:
            alters.append("ALTER TABLE users ADD COLUMN disabled BOOLEAN DEFAULT 0")
        if "created_at" not in existing:
            alters.append("ALTER TABLE users ADD COLUMN created_at TIMESTAMP")
        if "updated_at" not in existing:
            alters.append("ALTER TABLE users ADD COLUMN updated_at TIMESTAMP")
        for stmt in alters:
            try:
                session.execute(text(stmt))
                session.commit()
            except Exception:  # noqa: BLE001
                session.rollback()
    finally:
        session.close()


def get_user_by_username(username: str) -> UserRecord | None:
    uname = (username or "").strip().lower()
    if not uname:
        return None
    session = _sync_session()
    if session is None:
        return None
    try:
        stmt = select(UserAccount).where(col(UserAccount.username) == uname)
        row = session.exec(stmt).first()
        if row is None:
            # Case-insensitive fallback for mixed-case storage.
            rows = session.exec(select(UserAccount)).all()
            for candidate in rows:
                if (candidate.username or "").lower() == uname:
                    row = candidate
                    break
        if row is None or row.disabled:
            return None
        return _row_to_record(row)
    finally:
        session.close()


def get_user_by_id(user_id: UUID) -> UserRecord | None:
    session = _sync_session()
    if session is None:
        return None
    try:
        row = session.get(UserAccount, user_id)
        if row is None or row.disabled:
            return None
        return _row_to_record(row)
    finally:
        session.close()


def authenticate_user(username: str, password: str) -> UserRecord | None:
    uname = (username or "").strip().lower()
    session = _sync_session()
    if session is None:
        return None
    try:
        rows = session.exec(select(UserAccount)).all()
        row = None
        for candidate in rows:
            if (candidate.username or "").lower() == uname:
                row = candidate
                break
        if row is None or row.disabled or not row.password_hash:
            return None
        if not verify_password(password, row.password_hash):
            return None
        return _row_to_record(row)
    finally:
        session.close()


def list_users() -> list[UserRecord]:
    session = _sync_session()
    if session is None:
        return []
    try:
        rows = session.exec(select(UserAccount)).all()
        return [_row_to_record(r) for r in rows]
    finally:
        session.close()


def create_user(
    *,
    username: str,
    password: str,
    display_name: str | None = None,
    role: str = "user",
    user_id: UUID | None = None,
) -> UserRecord:
    uname = (username or "").strip().lower()
    if not uname:
        raise ValueError("username is required")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")
    role_n = (role or "user").strip().lower()
    if role_n not in {"admin", "user"}:
        raise ValueError("role must be admin or user")

    ensure_users_schema()
    session = _sync_session()
    if session is None:
        raise RuntimeError("Database unavailable")
    try:
        existing = session.exec(select(UserAccount)).all()
        for row in existing:
            if (row.username or "").lower() == uname:
                raise ValueError("Username already exists")
        now = _utcnow()
        uid = user_id or uuid4()
        row = UserAccount(
            id=uid,
            username=uname,
            password_hash=hash_password(password),
            display_name=display_name or uname,
            role=role_n,
            disabled=False,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _row_to_record(row)
    finally:
        session.close()


def set_user_password(user_id: UUID, password: str) -> None:
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")
    session = _sync_session()
    if session is None:
        raise RuntimeError("Database unavailable")
    try:
        row = session.get(UserAccount, user_id)
        if row is None:
            raise LookupError("User not found")
        row.password_hash = hash_password(password)
        row.updated_at = _utcnow()
        session.add(row)
        session.commit()
    finally:
        session.close()


def set_user_disabled(user_id: UUID, disabled: bool) -> UserRecord:
    if user_id == LOCAL_USER_ID and disabled:
        raise ValueError("Cannot disable the primary local admin user")
    session = _sync_session()
    if session is None:
        raise RuntimeError("Database unavailable")
    try:
        row = session.get(UserAccount, user_id)
        if row is None:
            raise LookupError("User not found")
        row.disabled = disabled
        row.updated_at = _utcnow()
        session.add(row)
        session.commit()
        session.refresh(row)
        return _row_to_record(row)
    finally:
        session.close()


def seed_admin_from_access_password(password: str) -> UserRecord:
    """Ensure LOCAL_USER_ID exists as admin with the given password."""
    ensure_users_schema()
    session = _sync_session()
    if session is None:
        raise RuntimeError("Database unavailable")
    try:
        row = session.get(UserAccount, LOCAL_USER_ID)
        now = _utcnow()
        if row is None:
            row = UserAccount(
                id=LOCAL_USER_ID,
                username="admin",
                password_hash=hash_password(password),
                display_name="Admin",
                role="admin",
                disabled=False,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            row.username = row.username or "admin"
            row.password_hash = hash_password(password)
            row.display_name = row.display_name or "Admin"
            row.role = "admin"
            row.disabled = False
            row.updated_at = now
            session.add(row)
        session.commit()
        session.refresh(row)
        return _row_to_record(row)
    finally:
        session.close()
