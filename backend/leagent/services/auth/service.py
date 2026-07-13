"""Session authentication service (access password + JWT).

Local / desktop deployments may run in *passthrough* mode when auth is not
enforced: any non-empty bearer is accepted as ``LOCAL_USER_ID``. When
enforcement is on, tokens must be HMAC-signed with a strong secret and carry
a valid ``exp`` claim.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from leagent.services.auth.secrets import is_weak_secret, resolve_signing_secret
from leagent.services.auth.store import get_security_store
from leagent.services.auth.tokens import TokenError, decode_token, mint_token
from leagent.utils.crypto import hash_password as _hash_password
from leagent.utils.crypto import verify_password as _verify_password

LOCAL_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

_DEFAULT_ACCESS_TTL = 12 * 60 * 60  # 12 hours
_DEFAULT_REFRESH_TTL = 7 * 24 * 60 * 60


@dataclass
class TokenPayload:
    sub: str = str(LOCAL_USER_ID)
    type: str = "access"
    role: str = "admin"
    username: str = "local"
    jti: str = ""
    exp: int = 0


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = _DEFAULT_ACCESS_TTL


@dataclass
class AuthUserInfo:
    user_id: UUID
    username: str
    display_name: str
    role: str
    is_superuser: bool
    permissions: list[str]
    roles: list[str]


class AuthService:
    """Password + JWT auth service for the security control plane."""

    def __init__(self, settings: object | None = None) -> None:
        self._settings = settings

    def _settings_obj(self) -> object | None:
        if self._settings is not None:
            return self._settings
        try:
            from leagent.config.settings import get_settings

            return get_settings()
        except Exception:  # noqa: BLE001
            return None

    def signing_secret(self) -> str:
        return resolve_signing_secret(self._settings_obj())

    def auth_enforced(self) -> bool:
        from leagent.services.auth.policy import effective_enforce_auth

        return effective_enforce_auth(self._settings_obj())

    def passthrough(self) -> bool:
        """True when tokens are not cryptographically verified."""
        return not self.auth_enforced()

    def hash_password(self, password: str) -> str:
        return _hash_password(password)

    def verify_password(self, plain: str, hashed: str) -> bool:
        if not hashed:
            # Passthrough legacy stub behaviour when no hash is configured.
            return self.passthrough()
        try:
            return _verify_password(plain, hashed)
        except Exception:  # noqa: BLE001
            return False

    def create_access_token(
        self,
        user_id: UUID,
        *,
        role: str = "admin",
        username: str = "local",
        ttl_seconds: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        ttl = int(ttl_seconds if ttl_seconds is not None else _DEFAULT_ACCESS_TTL)
        now = int(time.time())
        jti = uuid.uuid4().hex
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "type": "access",
            "role": role,
            "username": username,
            "jti": jti,
            "iat": now,
            "exp": now + ttl,
        }
        if extra:
            payload.update(extra)
        return mint_token(payload, self.signing_secret())

    def create_refresh_token(
        self,
        user_id: UUID,
        *,
        role: str = "admin",
        username: str = "local",
        ttl_seconds: int | None = None,
    ) -> str:
        ttl = int(ttl_seconds if ttl_seconds is not None else _DEFAULT_REFRESH_TTL)
        now = int(time.time())
        payload = {
            "sub": str(user_id),
            "type": "refresh",
            "role": role,
            "username": username,
            "jti": uuid.uuid4().hex,
            "iat": now,
            "exp": now + ttl,
        }
        return mint_token(payload, self.signing_secret())

    def create_token_pair(
        self,
        user_id: UUID,
        *,
        role: str = "admin",
        username: str = "local",
        **_kw: object,
    ) -> TokenPair:
        access = self.create_access_token(user_id, role=role, username=username)
        refresh = self.create_refresh_token(user_id, role=role, username=username)
        return TokenPair(access_token=access, refresh_token=refresh)

    def decode_access_token(self, token: str) -> TokenPayload | None:
        if not token:
            return None
        if self.passthrough():
            # Accept literally any non-empty token as the local admin principal.
            return TokenPayload(sub=str(LOCAL_USER_ID), type="access", role="admin")
        try:
            raw = decode_token(
                token,
                self.signing_secret(),
                options={"require_exp": True},
            )
        except TokenError:
            return None
        if raw.get("type") not in (None, "access"):
            return None
        jti = str(raw.get("jti") or "")
        if jti and get_security_store().is_jti_revoked(jti):
            return None
        try:
            UUID(str(raw.get("sub")))
        except Exception:  # noqa: BLE001
            return None
        return TokenPayload(
            sub=str(raw["sub"]),
            type=str(raw.get("type") or "access"),
            role=str(raw.get("role") or "user"),
            username=str(raw.get("username") or ""),
            jti=jti,
            exp=int(raw.get("exp") or 0),
        )

    def verify_access_token(self, token: str) -> UUID | None:
        payload = self.decode_access_token(token)
        if payload is None:
            return None
        try:
            return UUID(payload.sub)
        except Exception:  # noqa: BLE001
            return None

    def revoke_token(self, token: str) -> None:
        payload = self.decode_access_token(token)
        if payload and payload.jti:
            get_security_store().revoke_jti(payload.jti)

    def login_with_access_password(self, password: str) -> TokenPair:
        store = get_security_store()
        if not store.is_setup_complete():
            raise PermissionError("Access password is not configured. Complete setup first.")
        if not store.verify_access_password(password):
            raise PermissionError("Invalid access password")
        return self.create_token_pair(LOCAL_USER_ID, role="admin", username="admin")

    def login_user(self, username: str, password: str) -> TokenPair:
        """Authenticate a named user (Phase 2). Falls back to access password."""
        uname = (username or "").strip()
        if not uname:
            return self.login_with_access_password(password)

        from leagent.services.auth.users import authenticate_user

        info = authenticate_user(uname, password)
        if info is None:
            # Allow the instance access password with username "admin".
            if uname.lower() in {"admin", "local"}:
                return self.login_with_access_password(password)
            raise PermissionError("Invalid username or password")
        return self.create_token_pair(
            info.user_id,
            role=info.role,
            username=info.username,
        )

    def user_info_from_token(self, token: str) -> AuthUserInfo | None:
        payload = self.decode_access_token(token)
        if payload is None:
            return None
        uid = UUID(payload.sub)
        role = payload.role or "user"
        is_admin = role == "admin" or uid == LOCAL_USER_ID
        perms = ["*"] if is_admin else []
        return AuthUserInfo(
            user_id=uid,
            username=payload.username or ("admin" if is_admin else "user"),
            display_name=payload.username or ("Admin" if is_admin else "User"),
            role="admin" if is_admin else role,
            is_superuser=is_admin,
            permissions=perms,
            roles=["admin"] if is_admin else [role],
        )

    def assert_signing_secret_ready(self) -> None:
        """Fail closed when auth is enforced with a weak/missing secret."""
        if not self.auth_enforced():
            return
        secret = self.signing_secret()
        if is_weak_secret(secret):
            raise RuntimeError(
                "LEAGENT_SECRET_KEY is missing or too weak while authentication "
                "is enforced. Set a strong secret (openssl rand -hex 32)."
            )


_auth_service: AuthService | None = None


def init_auth_service(settings: object = None) -> AuthService:
    global _auth_service
    _auth_service = AuthService(settings)
    return _auth_service


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
