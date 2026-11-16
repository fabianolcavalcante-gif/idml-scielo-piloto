from __future__ import annotations

import hashlib
import hmac
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol, cast

from redis import Redis
from redis.exceptions import RedisError

from idml_foundation.settings import Settings


class RateLimitUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int


class AuthRateLimiter(Protocol):
    def check(self, scope: str, identities: tuple[str, ...], limit: int) -> RateLimitResult: ...

    def hit(
        self,
        scope: str,
        identities: tuple[str, ...],
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult: ...

    def reset(self, scope: str, identities: tuple[str, ...]) -> None: ...


def _bounded_key(pepper: str, scope: str, identity: str) -> str:
    digest = hmac.new(pepper.encode(), identity.encode(), hashlib.sha256).hexdigest()
    return f"idml:auth-rate:{scope}:{digest}"


class RedisAuthRateLimiter:
    _HIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""

    def __init__(self, redis_url: str, pepper: str) -> None:
        self._client: Redis = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        self._pepper = pepper

    def _keys(self, scope: str, identities: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_bounded_key(self._pepper, scope, identity) for identity in identities)

    def check(self, scope: str, identities: tuple[str, ...], limit: int) -> RateLimitResult:
        try:
            pipeline = self._client.pipeline(transaction=False)
            keys = self._keys(scope, identities)
            for key in keys:
                pipeline.get(key)
                pipeline.ttl(key)
            values = pipeline.execute()
        except RedisError as exc:
            raise RateLimitUnavailable("authentication rate limiter unavailable") from exc
        blocked_for = 0
        for offset in range(0, len(values), 2):
            count = int(values[offset] or 0)
            ttl = max(int(values[offset + 1] or 0), 1)
            if count >= limit:
                blocked_for = max(blocked_for, ttl)
        return RateLimitResult(allowed=blocked_for == 0, retry_after_seconds=blocked_for)

    def hit(
        self,
        scope: str,
        identities: tuple[str, ...],
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        blocked_for = 0
        try:
            for key in self._keys(scope, identities):
                result = cast(
                    list[int | str],
                    self._client.eval(self._HIT_SCRIPT, 1, key, str(window_seconds)),
                )
                current, ttl = result
                if int(current) >= limit:
                    blocked_for = max(blocked_for, max(int(ttl), 1))
        except RedisError as exc:
            raise RateLimitUnavailable("authentication rate limiter unavailable") from exc
        return RateLimitResult(allowed=blocked_for == 0, retry_after_seconds=blocked_for)

    def reset(self, scope: str, identities: tuple[str, ...]) -> None:
        try:
            keys = self._keys(scope, identities)
            if keys:
                self._client.delete(*keys)
        except RedisError as exc:
            raise RateLimitUnavailable("authentication rate limiter unavailable") from exc


class MemoryAuthRateLimiter:
    """Deterministic test limiter; production and development use Redis."""

    def __init__(self, pepper: str) -> None:
        self._pepper = pepper
        self._entries: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def _keys(self, scope: str, identities: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_bounded_key(self._pepper, scope, identity) for identity in identities)

    def check(self, scope: str, identities: tuple[str, ...], limit: int) -> RateLimitResult:
        now = time.monotonic()
        blocked_for = 0
        with self._lock:
            for key in self._keys(scope, identities):
                count, expires = self._entries.get(key, (0, now))
                if expires <= now:
                    self._entries.pop(key, None)
                elif count >= limit:
                    blocked_for = max(blocked_for, max(int(expires - now), 1))
        return RateLimitResult(allowed=blocked_for == 0, retry_after_seconds=blocked_for)

    def hit(
        self,
        scope: str,
        identities: tuple[str, ...],
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        now = time.monotonic()
        blocked_for = 0
        with self._lock:
            for key in self._keys(scope, identities):
                count, expires = self._entries.get(key, (0, now + window_seconds))
                if expires <= now:
                    count, expires = 0, now + window_seconds
                count += 1
                self._entries[key] = (count, expires)
                if count >= limit:
                    blocked_for = max(blocked_for, max(int(expires - now), 1))
        return RateLimitResult(allowed=blocked_for == 0, retry_after_seconds=blocked_for)

    def reset(self, scope: str, identities: tuple[str, ...]) -> None:
        with self._lock:
            for key in self._keys(scope, identities):
                self._entries.pop(key, None)


@lru_cache
def _build_rate_limiter(
    environment: str,
    redis_url: str,
    pepper: str,
    test_namespace: str,
) -> AuthRateLimiter:
    del test_namespace
    if environment == "test":
        return MemoryAuthRateLimiter(pepper)
    return RedisAuthRateLimiter(redis_url, pepper)


def get_auth_rate_limiter(settings: Settings) -> AuthRateLimiter:
    return _build_rate_limiter(
        settings.environment,
        settings.redis_url,
        settings.session_pepper.get_secret_value(),
        str(settings.artifact_root),
    )
