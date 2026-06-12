"""Cache service — in-memory LRU only."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from leagent.services.base import Service, ServiceState, ServiceType, service_factory

if TYPE_CHECKING:
    from leagent.config.settings import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_TTL = 3600
MAX_MEMORY_ITEMS = 10000


class CacheEntry(Generic[T]):
    __slots__ = ("value", "expires_at")

    def __init__(self, value: T, ttl: int | None = None) -> None:
        self.value = value
        self.expires_at = time.time() + ttl if ttl else None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class InMemoryCache:
    def __init__(self, max_size: int = MAX_MEMORY_ITEMS) -> None:
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._hit_count = 0
        self._miss_count = 0

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._miss_count += 1
                return None
            if entry.is_expired:
                del self._cache[key]
                self._miss_count += 1
                return None
            self._cache.move_to_end(key)
            self._hit_count += 1
            return entry.value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
            self._cache[key] = CacheEntry(value, ttl)
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def exists(self, key: str) -> bool:
        return await self.get(key) is not None

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    async def keys(self, pattern: str = "*") -> list[str]:
        import fnmatch
        async with self._lock:
            now = time.time()
            return [
                k
                for k, v in self._cache.items()
                if fnmatch.fnmatch(k, pattern) and (v.expires_at is None or v.expires_at > now)
            ]

    @property
    def stats(self) -> dict[str, Any]:
        total = self._hit_count + self._miss_count
        hit_rate = self._hit_count / total if total > 0 else 0.0
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hit_count,
            "misses": self._miss_count,
            "hit_rate": round(hit_rate, 4),
        }


@service_factory(ServiceType.CACHE)
class CacheService(Service):
    """In-memory LRU cache service (no Redis)."""

    def __init__(self, settings: "Settings") -> None:
        super().__init__(settings)
        self._memory_cache = InMemoryCache()
        self._prefix = f"{settings.app_name}:"

    @property
    def name(self) -> str:
        return "CacheService"

    @property
    def using_redis(self) -> bool:
        return False

    def _make_key(self, key: str, namespace: str | None = None) -> str:
        if namespace:
            return f"{self._prefix}{namespace}:{key}"
        return f"{self._prefix}{key}"

    async def _do_start(self) -> None:
        logger.info("CacheService: in-memory cache only")

    async def _do_stop(self) -> None:
        await self._memory_cache.clear()

    async def _do_health_check(self) -> dict[str, Any]:
        return {
            "backend": "memory",
            "memory_stats": self._memory_cache.stats,
        }

    async def get(self, key: str, *, namespace: str | None = None, default: T | None = None) -> T | None:
        full_key = self._make_key(key, namespace)
        result = await self._memory_cache.get(full_key)
        return result if result is not None else default

    async def set(self, key: str, value: Any, *, namespace: str | None = None, ttl: int | None = DEFAULT_TTL) -> bool:
        full_key = self._make_key(key, namespace)
        await self._memory_cache.set(full_key, value, ttl)
        return True

    async def delete(self, key: str, *, namespace: str | None = None) -> bool:
        full_key = self._make_key(key, namespace)
        return await self._memory_cache.delete(full_key)

    async def delete_prefix(self, prefix: str, *, namespace: str | None = None) -> int:
        """Delete all keys whose logical key starts with *prefix* in *namespace*."""
        full_prefix = self._make_key(prefix, namespace)
        pattern = f"{full_prefix}*"
        keys = await self._memory_cache.keys(pattern)
        count = 0
        for key in keys:
            if await self._memory_cache.delete(key):
                count += 1
        return count

    async def exists(self, key: str, *, namespace: str | None = None) -> bool:
        full_key = self._make_key(key, namespace)
        return await self._memory_cache.exists(full_key)

    async def get_or_set(self, key: str, factory: Any, *, namespace: str | None = None, ttl: int | None = DEFAULT_TTL) -> Any:
        value = await self.get(key, namespace=namespace)
        if value is not None:
            return value
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        elif callable(factory):
            value = factory()
        else:
            value = factory
        await self.set(key, value, namespace=namespace, ttl=ttl)
        return value

    async def clear_namespace(self, namespace: str) -> int:
        pattern = f"{self._prefix}{namespace}:*"
        keys = await self._memory_cache.keys(pattern)
        count = 0
        for key in keys:
            if await self._memory_cache.delete(key):
                count += 1
        return count

    async def increment(self, key: str, amount: int = 1, *, namespace: str | None = None, ttl: int | None = None) -> int:
        full_key = self._make_key(key, namespace)
        current = await self._memory_cache.get(full_key) or 0
        new_value = current + amount
        await self._memory_cache.set(full_key, new_value, ttl)
        return new_value

    async def get_many(self, keys: list[str], *, namespace: str | None = None) -> dict[str, Any]:
        result = {}
        for key in keys:
            full_key = self._make_key(key, namespace)
            value = await self._memory_cache.get(full_key)
            if value is not None:
                result[key] = value
        return result

    async def set_many(self, mapping: dict[str, Any], *, namespace: str | None = None, ttl: int | None = DEFAULT_TTL) -> bool:
        for key, value in mapping.items():
            full_key = self._make_key(key, namespace)
            await self._memory_cache.set(full_key, value, ttl)
        return True


_cache_service: CacheService | None = None


def get_cache_service() -> CacheService:
    if _cache_service is None:
        raise RuntimeError("CacheService not initialized")
    return _cache_service


async def init_cache_service(settings: "Settings") -> CacheService:
    global _cache_service
    _cache_service = CacheService(settings)
    await _cache_service.start()
    return _cache_service
