"""Variable service for global variables, environment integration, and secrets."""

from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlmodel import Column, SQLModel, Text, col, select

from leagent.services.base import Service, ServiceType, service_factory
from leagent.services.database.models.base import BaseModel as DBBaseModel

if TYPE_CHECKING:
    from leagent.config.settings import Settings
    from leagent.services.cache.service import CacheService
    from leagent.services.database.service import DatabaseService

logger = logging.getLogger(__name__)

CACHE_NAMESPACE = "variables"
CACHE_TTL = 600


class VariableType(str, Enum):
    """Variable type classification."""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    JSON = "json"
    SECRET = "secret"


class VariableScope(str, Enum):
    """Variable scope for access control."""

    GLOBAL = "global"
    USER = "user"
    FLOW = "flow"
    SESSION = "session"


class Variable(DBBaseModel, table=True):
    """Variable database model."""

    __tablename__ = "variables"

    name: str = Field(max_length=100, index=True)
    value: str = Field(sa_column=Column(Text))
    var_type: VariableType = Field(default=VariableType.STRING)
    scope: VariableScope = Field(default=VariableScope.GLOBAL)
    scope_id: UUID | None = Field(default=None, index=True)
    is_encrypted: bool = Field(default=False)
    description: str | None = Field(default=None, max_length=500)
    created_by: UUID | None = Field(default=None, foreign_key="users.id")


class VariableCreate(BaseModel):
    """Schema for creating a variable."""

    name: str = Field(max_length=100)
    value: Any
    var_type: VariableType = VariableType.STRING
    scope: VariableScope = VariableScope.GLOBAL
    scope_id: UUID | None = None
    description: str | None = None


class VariableRead(BaseModel):
    """Schema for reading a variable (value masked for secrets)."""

    id: UUID
    name: str
    value: Any
    var_type: VariableType
    scope: VariableScope
    scope_id: UUID | None
    is_encrypted: bool
    description: str | None
    created_at: datetime
    updated_at: datetime


class VariableUpdate(BaseModel):
    """Schema for updating a variable."""

    value: Any | None = None
    description: str | None = None


class EncryptionService:
    """Simple base64 obfuscation for variable secrets."""

    def __init__(self, key: str) -> None:
        import hashlib
        self._key = hashlib.sha256(key.encode()).digest()

    def encrypt(self, value: str) -> str:
        raw = value.encode()
        xored = bytes(b ^ self._key[i % len(self._key)] for i, b in enumerate(raw))
        return base64.urlsafe_b64encode(xored).decode()

    def decrypt(self, encrypted_value: str) -> str:
        try:
            xored = base64.urlsafe_b64decode(encrypted_value.encode())
            raw = bytes(b ^ self._key[i % len(self._key)] for i, b in enumerate(xored))
            return raw.decode()
        except Exception as e:
            logger.error("Decryption failed: %s", e)
            raise ValueError("Failed to decrypt value") from e


@service_factory(ServiceType.VARIABLE)
class VariableService(Service):
    """Service for managing global variables with encryption support.

    Features:
    - CRUD operations for variables
    - Environment variable integration
    - Encryption for secret values
    - Scoped variables (global, user, flow, session)
    - Cache-backed lookups
    """

    def __init__(
        self,
        settings: Settings,
        db_service: DatabaseService | None = None,
        cache_service: CacheService | None = None,
    ) -> None:
        super().__init__(settings)
        self._db = db_service
        self._cache = cache_service
        self._encryption = EncryptionService("leagent-local-encryption-key!!")
        self._env_prefix = "LEAGENT_VAR_"

    @property
    def name(self) -> str:
        return "VariableService"

    def set_dependencies(
        self,
        db_service: DatabaseService,
        cache_service: CacheService | None = None,
    ) -> None:
        """Set service dependencies after initialization."""
        self._db = db_service
        self._cache = cache_service

    async def _do_health_check(self) -> dict[str, Any]:
        return {
            "db_connected": self._db is not None,
            "cache_connected": self._cache is not None,
            "encryption_ready": self._encryption is not None,
        }

    def _serialize_value(self, value: Any, var_type: VariableType) -> str:
        """Serialize a value based on its type."""
        if var_type == VariableType.JSON:
            return json.dumps(value)
        elif var_type == VariableType.NUMBER:
            return str(value)
        elif var_type == VariableType.BOOLEAN:
            return "true" if value else "false"
        return str(value)

    def _deserialize_value(self, value: str, var_type: VariableType) -> Any:
        """Deserialize a value based on its type."""
        if var_type == VariableType.JSON:
            return json.loads(value)
        elif var_type == VariableType.NUMBER:
            try:
                return int(value)
            except ValueError:
                return float(value)
        elif var_type == VariableType.BOOLEAN:
            return value.lower() in ("true", "1", "yes")
        return value

    def _get_cache_key(
        self,
        name: str,
        scope: VariableScope,
        scope_id: UUID | None,
    ) -> str:
        """Generate a cache key for a variable."""
        if scope_id:
            return f"{scope.value}:{scope_id}:{name}"
        return f"{scope.value}:{name}"

    async def create(
        self,
        data: VariableCreate,
        *,
        user_id: UUID | None = None,
    ) -> Variable:
        """Create a new variable.

        Args:
            data: Variable creation data
            user_id: Creating user ID

        Returns:
            The created variable

        Raises:
            ValueError: If variable name already exists in scope
        """
        if self._db is None:
            raise RuntimeError("Database service not initialized")

        existing = await self.get_by_name(
            data.name,
            scope=data.scope,
            scope_id=data.scope_id,
        )
        if existing:
            raise ValueError(f"Variable '{data.name}' already exists in {data.scope.value} scope")

        serialized = self._serialize_value(data.value, data.var_type)

        is_encrypted = data.var_type == VariableType.SECRET
        if is_encrypted:
            serialized = self._encryption.encrypt(serialized)

        variable = Variable(
            id=uuid4(),
            name=data.name,
            value=serialized,
            var_type=data.var_type,
            scope=data.scope,
            scope_id=data.scope_id,
            is_encrypted=is_encrypted,
            description=data.description,
            created_by=user_id,
        )

        async with self._db.session() as db:
            db.add(variable)
            await db.flush()
            await db.refresh(variable)

        cache_key = self._get_cache_key(data.name, data.scope, data.scope_id)
        if self._cache:
            await self._cache.delete(cache_key, namespace=CACHE_NAMESPACE)

        logger.debug("Created variable %s in %s scope", data.name, data.scope.value)
        return variable

    async def get(self, variable_id: UUID) -> Variable | None:
        """Get a variable by ID.

        Args:
            variable_id: The variable ID

        Returns:
            The variable or None
        """
        if self._db is None:
            return None

        async with self._db.session() as db:
            stmt = select(Variable).where(Variable.id == variable_id)
            result = await db.execute(stmt)
            return result.scalar_one_or_none()

    async def get_by_name(
        self,
        name: str,
        *,
        scope: VariableScope = VariableScope.GLOBAL,
        scope_id: UUID | None = None,
        decrypt: bool = True,
    ) -> Variable | None:
        """Get a variable by name and scope.

        Args:
            name: Variable name
            scope: Variable scope
            scope_id: Scope identifier (user_id, flow_id, etc.)
            decrypt: Whether to decrypt secret values

        Returns:
            The variable or None
        """
        cache_key = self._get_cache_key(name, scope, scope_id)

        if self._cache:
            cached = await self._cache.get(cache_key, namespace=CACHE_NAMESPACE)
            if cached:
                variable = Variable.model_validate(cached)
                if decrypt and variable.is_encrypted:
                    variable.value = self._encryption.decrypt(variable.value)
                return variable

        if self._db is None:
            return None

        async with self._db.session() as db:
            stmt = select(Variable).where(
                Variable.name == name,
                Variable.scope == scope,
            )
            if scope_id:
                stmt = stmt.where(Variable.scope_id == scope_id)
            else:
                stmt = stmt.where(Variable.scope_id.is_(None))

            result = await db.execute(stmt)
            variable = result.scalar_one_or_none()

        if variable and self._cache:
            await self._cache.set(
                cache_key,
                variable.model_dump(mode="json"),
                namespace=CACHE_NAMESPACE,
                ttl=CACHE_TTL,
            )

        if variable and decrypt and variable.is_encrypted:
            variable.value = self._encryption.decrypt(variable.value)

        return variable

    async def get_value(
        self,
        name: str,
        *,
        scope: VariableScope = VariableScope.GLOBAL,
        scope_id: UUID | None = None,
        default: Any = None,
    ) -> Any:
        """Get a variable's deserialized value.

        Also checks environment variables with LEAGENT_VAR_ prefix.

        Args:
            name: Variable name
            scope: Variable scope
            scope_id: Scope identifier
            default: Default value if not found

        Returns:
            The variable value or default
        """
        env_key = f"{self._env_prefix}{name.upper()}"
        env_value = os.environ.get(env_key)
        if env_value is not None:
            return env_value

        variable = await self.get_by_name(name, scope=scope, scope_id=scope_id)
        if variable is None:
            return default

        return self._deserialize_value(variable.value, variable.var_type)

    async def update(
        self,
        variable_id: UUID,
        data: VariableUpdate,
    ) -> Variable | None:
        """Update a variable.

        Args:
            variable_id: The variable ID
            data: Update data

        Returns:
            The updated variable or None
        """
        if self._db is None:
            return None

        async with self._db.session() as db:
            stmt = select(Variable).where(Variable.id == variable_id)
            result = await db.execute(stmt)
            variable = result.scalar_one_or_none()

            if not variable:
                return None

            if data.value is not None:
                serialized = self._serialize_value(data.value, variable.var_type)
                if variable.is_encrypted:
                    serialized = self._encryption.encrypt(serialized)
                variable.value = serialized

            if data.description is not None:
                variable.description = data.description

            variable.updated_at = datetime.utcnow()
            await db.flush()
            await db.refresh(variable)

        cache_key = self._get_cache_key(variable.name, variable.scope, variable.scope_id)
        if self._cache:
            await self._cache.delete(cache_key, namespace=CACHE_NAMESPACE)

        return variable

    async def delete(self, variable_id: UUID) -> bool:
        """Delete a variable.

        Args:
            variable_id: The variable ID

        Returns:
            True if deleted
        """
        if self._db is None:
            return False

        async with self._db.session() as db:
            stmt = select(Variable).where(Variable.id == variable_id)
            result = await db.execute(stmt)
            variable = result.scalar_one_or_none()

            if not variable:
                return False

            cache_key = self._get_cache_key(variable.name, variable.scope, variable.scope_id)
            await db.delete(variable)

        if self._cache:
            await self._cache.delete(cache_key, namespace=CACHE_NAMESPACE)

        return True

    async def list(
        self,
        *,
        scope: VariableScope | None = None,
        scope_id: UUID | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[VariableRead]:
        """List variables with optional filtering.

        Args:
            scope: Filter by scope
            scope_id: Filter by scope ID
            offset: Pagination offset
            limit: Maximum results

        Returns:
            List of variables (secrets are masked)
        """
        if self._db is None:
            return []

        async with self._db.session() as db:
            stmt = select(Variable).offset(offset).limit(limit)

            if scope:
                stmt = stmt.where(Variable.scope == scope)
            if scope_id:
                stmt = stmt.where(Variable.scope_id == scope_id)

            stmt = stmt.order_by(col(Variable.name))
            result = await db.execute(stmt)
            variables = result.scalars().all()

        reads = []
        for var in variables:
            value = var.value
            if var.is_encrypted:
                value = "********"
            else:
                value = self._deserialize_value(var.value, var.var_type)

            reads.append(
                VariableRead(
                    id=var.id,
                    name=var.name,
                    value=value,
                    var_type=var.var_type,
                    scope=var.scope,
                    scope_id=var.scope_id,
                    is_encrypted=var.is_encrypted,
                    description=var.description,
                    created_at=var.created_at,
                    updated_at=var.updated_at,
                )
            )

        return reads

    async def set_env_override(self, name: str, value: str) -> None:
        """Set an environment variable override.

        Args:
            name: Variable name
            value: Variable value
        """
        env_key = f"{self._env_prefix}{name.upper()}"
        os.environ[env_key] = value
        logger.debug("Set environment override %s", env_key)

    async def clear_env_override(self, name: str) -> None:
        """Clear an environment variable override.

        Args:
            name: Variable name
        """
        env_key = f"{self._env_prefix}{name.upper()}"
        os.environ.pop(env_key, None)

    async def resolve_template(
        self,
        template: str,
        *,
        scope: VariableScope = VariableScope.GLOBAL,
        scope_id: UUID | None = None,
    ) -> str:
        """Resolve variable references in a template string.

        Supports {{variable_name}} syntax.

        Args:
            template: Template string with variable references
            scope: Variable scope for lookups
            scope_id: Scope identifier

        Returns:
            Resolved string
        """
        import re

        pattern = r"\{\{(\w+)\}\}"

        async def replace(match: re.Match) -> str:
            var_name = match.group(1)
            value = await self.get_value(var_name, scope=scope, scope_id=scope_id)
            return str(value) if value is not None else match.group(0)

        matches = re.findall(pattern, template)
        result = template

        for var_name in matches:
            value = await self.get_value(var_name, scope=scope, scope_id=scope_id)
            if value is not None:
                result = result.replace(f"{{{{{var_name}}}}}", str(value))

        return result

    async def bulk_set(
        self,
        variables: dict[str, Any],
        *,
        scope: VariableScope = VariableScope.GLOBAL,
        scope_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> int:
        """Set multiple variables at once.

        Args:
            variables: Dictionary of name -> value
            scope: Variable scope
            scope_id: Scope identifier
            user_id: Creating user ID

        Returns:
            Number of variables created/updated
        """
        count = 0
        for name, value in variables.items():
            existing = await self.get_by_name(name, scope=scope, scope_id=scope_id, decrypt=False)

            var_type = VariableType.STRING
            if isinstance(value, bool):
                var_type = VariableType.BOOLEAN
            elif isinstance(value, (int, float)):
                var_type = VariableType.NUMBER
            elif isinstance(value, (dict, list)):
                var_type = VariableType.JSON

            if existing:
                await self.update(existing.id, VariableUpdate(value=value))
            else:
                await self.create(
                    VariableCreate(
                        name=name,
                        value=value,
                        var_type=var_type,
                        scope=scope,
                        scope_id=scope_id,
                    ),
                    user_id=user_id,
                )
            count += 1

        return count


_variable_service: VariableService | None = None


def get_variable_service() -> VariableService:
    """Get the global variable service instance."""
    if _variable_service is None:
        raise RuntimeError("VariableService not initialized")
    return _variable_service


async def init_variable_service(
    settings: Settings,
    db_service: DatabaseService,
    cache_service: CacheService | None = None,
) -> VariableService:
    """Initialize and start the global variable service."""
    global _variable_service
    _variable_service = VariableService(settings, db_service, cache_service)
    await _variable_service.start()
    return _variable_service
