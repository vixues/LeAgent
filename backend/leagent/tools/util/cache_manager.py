"""Cache Manager Tool - In-memory and distributed caching.

Provides operations for cache get/set/delete, TTL management,
cache statistics, and bulk operations.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with value and metadata."""

    value: Any
    created_at: float
    expires_at: float | None = None
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        """Check if entry is expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    @property
    def ttl_remaining(self) -> float | None:
        """Get remaining TTL in seconds."""
        if self.expires_at is None:
            return None
        remaining = self.expires_at - time.time()
        return max(0, remaining)


class LocalCache:
    """Simple in-memory cache implementation."""

    def __init__(self) -> None:
        self._cache: dict[str, CacheEntry] = {}
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
        }

    def get(self, key: str) -> tuple[Any, bool]:
        """Get value from cache. Returns (value, found)."""
        entry = self._cache.get(key)

        if entry is None:
            self._stats["misses"] += 1
            return None, False

        if entry.is_expired:
            del self._cache[key]
            self._stats["misses"] += 1
            return None, False

        entry.access_count += 1
        entry.last_accessed = time.time()
        self._stats["hits"] += 1
        return entry.value, True

    def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Set value in cache."""
        expires_at = time.time() + ttl if ttl else None
        self._cache[key] = CacheEntry(
            value=value,
            created_at=time.time(),
            expires_at=expires_at,
            tags=tags or [],
        )
        self._stats["sets"] += 1

    def delete(self, key: str) -> bool:
        """Delete key from cache. Returns True if key existed."""
        if key in self._cache:
            del self._cache[key]
            self._stats["deletes"] += 1
            return True
        return False

    def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        entry = self._cache.get(key)
        if entry is None:
            return False
        if entry.is_expired:
            del self._cache[key]
            return False
        return True

    def clear(self) -> int:
        """Clear all entries. Returns count cleared."""
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0

        return {
            **self._stats,
            "hit_rate": round(hit_rate, 2),
            "total_requests": total,
            "current_size": len(self._cache),
        }

    def get_entry_info(self, key: str) -> dict[str, Any] | None:
        """Get metadata about a cache entry."""
        entry = self._cache.get(key)
        if entry is None or entry.is_expired:
            return None

        return {
            "created_at": entry.created_at,
            "expires_at": entry.expires_at,
            "ttl_remaining": entry.ttl_remaining,
            "access_count": entry.access_count,
            "last_accessed": entry.last_accessed,
            "tags": entry.tags,
        }

    def keys(self, pattern: str | None = None) -> list[str]:
        """Get all keys, optionally filtered by pattern."""
        self._cleanup_expired()

        if pattern is None:
            return list(self._cache.keys())

        import fnmatch

        return [k for k in self._cache.keys() if fnmatch.fnmatch(k, pattern)]

    def get_by_tag(self, tag: str) -> dict[str, Any]:
        """Get all entries with a specific tag."""
        self._cleanup_expired()

        return {
            key: entry.value
            for key, entry in self._cache.items()
            if tag in entry.tags
        }

    def delete_by_tag(self, tag: str) -> int:
        """Delete all entries with a specific tag."""
        keys_to_delete = [
            key for key, entry in self._cache.items() if tag in entry.tags
        ]
        for key in keys_to_delete:
            del self._cache[key]
        self._stats["deletes"] += len(keys_to_delete)
        return len(keys_to_delete)

    def _cleanup_expired(self) -> int:
        """Remove expired entries."""
        expired = [k for k, v in self._cache.items() if v.is_expired]
        for key in expired:
            del self._cache[key]
        return len(expired)


_local_cache = LocalCache()


class CacheManagerTool(BaseTool):
    """Manage cache operations.

    Features:
    - Get, set, delete cache entries
    - TTL (time-to-live) management
    - Cache statistics and monitoring
    - Bulk operations
    - Tag-based organization
    - Pattern-based key matching
    - Redis integration when available
    """

    name = "cache_manager"
    description = (
        "Manage cache with get/set/delete operations, TTL management, "
        "bulk operations, and cache statistics."
    )
    category = ToolCategory.UTIL
    version = "1.0.0"
    timeout_sec = 30
    aliases = ["cache", "redis_cache"]
    search_hint = "cache get set delete TTL bulk statistics Redis"
    is_concurrency_safe = True
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 100_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "get")
        return f"Cache operation ({op})"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "get",
                        "set",
                        "delete",
                        "exists",
                        "clear",
                        "stats",
                        "info",
                        "keys",
                        "mget",
                        "mset",
                        "mdelete",
                        "get_by_tag",
                        "delete_by_tag",
                        "touch",
                        "increment",
                        "decrement",
                    ],
                    "description": "Cache operation to perform.",
                },
                "key": {
                    "type": "string",
                    "description": "Cache key.",
                },
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Multiple cache keys for bulk operations.",
                },
                "value": {
                    "description": "Value to cache.",
                },
                "values": {
                    "type": "object",
                    "description": "Key-value pairs for mset operation.",
                },
                "ttl": {
                    "type": "number",
                    "description": "Time-to-live in seconds.",
                    "minimum": 0,
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for organizing cache entries.",
                },
                "tag": {
                    "type": "string",
                    "description": "Tag for tag-based operations.",
                },
                "pattern": {
                    "type": "string",
                    "description": "Pattern for key matching (glob-style).",
                },
                "amount": {
                    "type": "integer",
                    "description": "Amount for increment/decrement operations.",
                    "default": 1,
                },
                "use_redis": {
                    "type": "boolean",
                    "description": "Use Redis if available in context.",
                    "default": True,
                },
                "namespace": {
                    "type": "string",
                    "description": "Key namespace/prefix.",
                },
            },
            "required": ["operation"],
            "additionalProperties": False,
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute cache operation.

        Args:
            params: Tool parameters including operation and cache data.
            context: Execution context with optional Redis client.

        Returns:
            Dictionary containing operation result.

        Raises:
            ValueError: If parameters are invalid.
        """
        operation = params["operation"]
        use_redis = params.get("use_redis", True) and context.cache is not None
        namespace = params.get("namespace", "")

        logger.info("Executing cache operation", operation=operation, use_redis=use_redis)

        if use_redis and context.cache:
            result = await self._execute_redis(operation, params, context, namespace)
        else:
            result = self._execute_local(operation, params, namespace)

        logger.info("Cache operation complete", operation=operation)
        return result

    def _make_key(self, key: str, namespace: str) -> str:
        """Create namespaced key."""
        if namespace:
            return f"{namespace}:{key}"
        return key

    def _execute_local(self, operation: str, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Execute operation on local cache."""
        operations = {
            "get": self._local_get,
            "set": self._local_set,
            "delete": self._local_delete,
            "exists": self._local_exists,
            "clear": self._local_clear,
            "stats": self._local_stats,
            "info": self._local_info,
            "keys": self._local_keys,
            "mget": self._local_mget,
            "mset": self._local_mset,
            "mdelete": self._local_mdelete,
            "get_by_tag": self._local_get_by_tag,
            "delete_by_tag": self._local_delete_by_tag,
            "touch": self._local_touch,
            "increment": self._local_increment,
            "decrement": self._local_decrement,
        }

        if operation not in operations:
            raise ValueError(f"Unknown operation: {operation}")

        return operations[operation](params, namespace)

    def _local_get(self, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Get value from local cache."""
        key = params.get("key")
        if not key:
            raise ValueError("Key is required for get operation")

        full_key = self._make_key(key, namespace)
        value, found = _local_cache.get(full_key)

        return {
            "key": key,
            "value": value,
            "found": found,
            "source": "local",
        }

    def _local_set(self, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Set value in local cache."""
        key = params.get("key")
        value = params.get("value")
        ttl = params.get("ttl")
        tags = params.get("tags")

        if not key:
            raise ValueError("Key is required for set operation")

        full_key = self._make_key(key, namespace)
        _local_cache.set(full_key, value, ttl, tags)

        return {
            "key": key,
            "success": True,
            "ttl": ttl,
            "source": "local",
        }

    def _local_delete(self, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Delete from local cache."""
        key = params.get("key")
        if not key:
            raise ValueError("Key is required for delete operation")

        full_key = self._make_key(key, namespace)
        deleted = _local_cache.delete(full_key)

        return {
            "key": key,
            "deleted": deleted,
            "source": "local",
        }

    def _local_exists(self, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Check if key exists in local cache."""
        key = params.get("key")
        if not key:
            raise ValueError("Key is required for exists operation")

        full_key = self._make_key(key, namespace)
        exists = _local_cache.exists(full_key)

        return {
            "key": key,
            "exists": exists,
            "source": "local",
        }

    def _local_clear(self, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Clear local cache."""
        count = _local_cache.clear()
        return {
            "cleared": count,
            "source": "local",
        }

    def _local_stats(self, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Get local cache statistics."""
        stats = _local_cache.get_stats()
        stats["source"] = "local"
        return stats

    def _local_info(self, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Get info about specific cache entry."""
        key = params.get("key")
        if not key:
            raise ValueError("Key is required for info operation")

        full_key = self._make_key(key, namespace)
        info = _local_cache.get_entry_info(full_key)

        if info is None:
            return {"key": key, "found": False, "source": "local"}

        return {
            "key": key,
            "found": True,
            **info,
            "source": "local",
        }

    def _local_keys(self, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """List keys in local cache."""
        pattern = params.get("pattern")
        if namespace:
            pattern = f"{namespace}:{pattern or '*'}"

        keys = _local_cache.keys(pattern)

        if namespace:
            keys = [k[len(namespace) + 1 :] for k in keys]

        return {
            "keys": keys,
            "count": len(keys),
            "source": "local",
        }

    def _local_mget(self, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Get multiple values from local cache."""
        keys = params.get("keys", [])
        if not keys:
            raise ValueError("Keys are required for mget operation")

        results = {}
        found_count = 0

        for key in keys:
            full_key = self._make_key(key, namespace)
            value, found = _local_cache.get(full_key)
            results[key] = value
            if found:
                found_count += 1

        return {
            "results": results,
            "found_count": found_count,
            "total_count": len(keys),
            "source": "local",
        }

    def _local_mset(self, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Set multiple values in local cache."""
        values = params.get("values", {})
        ttl = params.get("ttl")
        tags = params.get("tags")

        if not values:
            raise ValueError("Values are required for mset operation")

        for key, value in values.items():
            full_key = self._make_key(key, namespace)
            _local_cache.set(full_key, value, ttl, tags)

        return {
            "set_count": len(values),
            "keys": list(values.keys()),
            "source": "local",
        }

    def _local_mdelete(self, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Delete multiple keys from local cache."""
        keys = params.get("keys", [])
        if not keys:
            raise ValueError("Keys are required for mdelete operation")

        deleted_count = 0
        for key in keys:
            full_key = self._make_key(key, namespace)
            if _local_cache.delete(full_key):
                deleted_count += 1

        return {
            "deleted_count": deleted_count,
            "total_count": len(keys),
            "source": "local",
        }

    def _local_get_by_tag(self, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Get all entries with specific tag."""
        tag = params.get("tag")
        if not tag:
            raise ValueError("Tag is required for get_by_tag operation")

        entries = _local_cache.get_by_tag(tag)

        return {
            "tag": tag,
            "entries": entries,
            "count": len(entries),
            "source": "local",
        }

    def _local_delete_by_tag(self, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Delete all entries with specific tag."""
        tag = params.get("tag")
        if not tag:
            raise ValueError("Tag is required for delete_by_tag operation")

        deleted = _local_cache.delete_by_tag(tag)

        return {
            "tag": tag,
            "deleted_count": deleted,
            "source": "local",
        }

    def _local_touch(self, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Update TTL of existing key."""
        key = params.get("key")
        ttl = params.get("ttl")

        if not key:
            raise ValueError("Key is required for touch operation")

        full_key = self._make_key(key, namespace)
        value, found = _local_cache.get(full_key)

        if not found:
            return {"key": key, "success": False, "message": "Key not found"}

        entry = _local_cache._cache.get(full_key)
        if entry and ttl is not None:
            entry.expires_at = time.time() + ttl

        return {
            "key": key,
            "success": True,
            "new_ttl": ttl,
            "source": "local",
        }

    def _local_increment(self, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Increment numeric value."""
        key = params.get("key")
        amount = params.get("amount", 1)

        if not key:
            raise ValueError("Key is required for increment operation")

        full_key = self._make_key(key, namespace)
        value, found = _local_cache.get(full_key)

        if not found:
            new_value = amount
        elif isinstance(value, (int, float)):
            new_value = value + amount
        else:
            raise ValueError(f"Cannot increment non-numeric value: {type(value)}")

        _local_cache.set(full_key, new_value)

        return {
            "key": key,
            "value": new_value,
            "source": "local",
        }

    def _local_decrement(self, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Decrement numeric value."""
        params["amount"] = -params.get("amount", 1)
        return self._local_increment(params, namespace)

    async def _execute_redis(
        self,
        operation: str,
        params: dict[str, Any],
        context: ToolContext,
        namespace: str,
    ) -> dict[str, Any]:
        """Execute operation on Redis cache."""
        redis = context.cache
        if redis is None:
            return self._execute_local(operation, params, namespace)

        try:
            if operation == "get":
                return await self._redis_get(redis, params, namespace)
            elif operation == "set":
                return await self._redis_set(redis, params, namespace)
            elif operation == "delete":
                return await self._redis_delete(redis, params, namespace)
            elif operation == "exists":
                return await self._redis_exists(redis, params, namespace)
            elif operation == "keys":
                return await self._redis_keys(redis, params, namespace)
            elif operation == "mget":
                return await self._redis_mget(redis, params, namespace)
            elif operation == "mset":
                return await self._redis_mset(redis, params, namespace)
            elif operation == "increment":
                return await self._redis_increment(redis, params, namespace)
            elif operation == "decrement":
                return await self._redis_decrement(redis, params, namespace)
            else:
                return self._execute_local(operation, params, namespace)
        except Exception as e:
            logger.warning("Redis operation failed, falling back to local", error=str(e))
            return self._execute_local(operation, params, namespace)

    async def _redis_get(self, redis: Any, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Get value from Redis."""
        key = params.get("key")
        if not key:
            raise ValueError("Key is required")

        full_key = self._make_key(key, namespace)
        value = await redis.get(full_key)

        if value is not None:
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            "key": key,
            "value": value,
            "found": value is not None,
            "source": "redis",
        }

    async def _redis_set(self, redis: Any, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Set value in Redis."""
        key = params.get("key")
        value = params.get("value")
        ttl = params.get("ttl")

        if not key:
            raise ValueError("Key is required")

        full_key = self._make_key(key, namespace)

        if not isinstance(value, (str, bytes)):
            value = json.dumps(value)

        if ttl:
            await redis.setex(full_key, int(ttl), value)
        else:
            await redis.set(full_key, value)

        return {
            "key": key,
            "success": True,
            "ttl": ttl,
            "source": "redis",
        }

    async def _redis_delete(self, redis: Any, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Delete from Redis."""
        key = params.get("key")
        if not key:
            raise ValueError("Key is required")

        full_key = self._make_key(key, namespace)
        deleted = await redis.delete(full_key)

        return {
            "key": key,
            "deleted": deleted > 0,
            "source": "redis",
        }

    async def _redis_exists(self, redis: Any, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Check if key exists in Redis."""
        key = params.get("key")
        if not key:
            raise ValueError("Key is required")

        full_key = self._make_key(key, namespace)
        exists = await redis.exists(full_key)

        return {
            "key": key,
            "exists": exists > 0,
            "source": "redis",
        }

    async def _redis_keys(self, redis: Any, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """List keys in Redis."""
        pattern = params.get("pattern", "*")
        if namespace:
            pattern = f"{namespace}:{pattern}"

        keys = await redis.keys(pattern)
        keys = [k.decode() if isinstance(k, bytes) else k for k in keys]

        if namespace:
            keys = [k[len(namespace) + 1 :] for k in keys]

        return {
            "keys": keys,
            "count": len(keys),
            "source": "redis",
        }

    async def _redis_mget(self, redis: Any, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Get multiple values from Redis."""
        keys = params.get("keys", [])
        if not keys:
            raise ValueError("Keys are required")

        full_keys = [self._make_key(k, namespace) for k in keys]
        values = await redis.mget(full_keys)

        results = {}
        found_count = 0
        for key, value in zip(keys, values):
            if value is not None:
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass
                found_count += 1
            results[key] = value

        return {
            "results": results,
            "found_count": found_count,
            "total_count": len(keys),
            "source": "redis",
        }

    async def _redis_mset(self, redis: Any, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Set multiple values in Redis."""
        values = params.get("values", {})
        if not values:
            raise ValueError("Values are required")

        mapping = {}
        for key, value in values.items():
            full_key = self._make_key(key, namespace)
            if not isinstance(value, (str, bytes)):
                value = json.dumps(value)
            mapping[full_key] = value

        await redis.mset(mapping)

        return {
            "set_count": len(values),
            "keys": list(values.keys()),
            "source": "redis",
        }

    async def _redis_increment(self, redis: Any, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Increment value in Redis."""
        key = params.get("key")
        amount = params.get("amount", 1)

        if not key:
            raise ValueError("Key is required")

        full_key = self._make_key(key, namespace)

        if isinstance(amount, float):
            new_value = await redis.incrbyfloat(full_key, amount)
        else:
            new_value = await redis.incrby(full_key, amount)

        return {
            "key": key,
            "value": new_value,
            "source": "redis",
        }

    async def _redis_decrement(self, redis: Any, params: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Decrement value in Redis."""
        key = params.get("key")
        amount = params.get("amount", 1)

        if not key:
            raise ValueError("Key is required")

        full_key = self._make_key(key, namespace)
        new_value = await redis.decrby(full_key, amount)

        return {
            "key": key,
            "value": new_value,
            "source": "redis",
        }
