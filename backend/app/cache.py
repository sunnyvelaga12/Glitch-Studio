"""
cache.py — Production-grade Caching and Distributed Rate Limiting for VirtualHR

Features:
  - Redis / LRU cache for query responses
  - Sliding window rate limiter (per-IP and per-user)
  - Fail-Closed Redis Outage Security Policy for abuse-sensitive auth routes
"""

import hashlib
import logging
import time
import os
from collections import defaultdict, OrderedDict
from threading import Lock
from typing import Any, Optional

from fastapi import HTTPException, status
import redis
from app.config import settings

logger = logging.getLogger(__name__)

# Redis Client Connection Setup
redis_url = os.environ.get("REDIS_URL") or getattr(settings, "REDIS_URL", "")
redis_client = None
if redis_url:
    try:
        redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        redis_client.ping()
        logger.info("Connected to Redis for caching and distributed rate limiting.")
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {e}. Falling back to in-memory mode.")
        redis_client = None


def get_redis_client() -> Optional[redis.Redis]:
    return redis_client


def set_redis_client_override(client: Optional[redis.Redis]) -> None:
    """Helper for testing Redis outages and fail-closed behaviors."""
    global redis_client
    redis_client = client


class TimeboxedCache:
    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self.lock = Lock()

    def get(self, key: str) -> Optional[Any]:
        if redis_client:
            try:
                return redis_client.get(f"cache:{key}")
            except Exception as e:
                logger.error(f"Redis get error: {e}")
                return None
        
        with self.lock:
            if key not in self.cache:
                return None
            value, timestamp = self.cache[key]
            if time.time() - timestamp > self.ttl_seconds:
                del self.cache[key]
                return None
            self.cache.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        if redis_client:
            try:
                redis_client.setex(f"cache:{key}", self.ttl_seconds, str(value))
                return
            except Exception as e:
                logger.error(f"Redis set error: {e}")
                
        with self.lock:
            if key in self.cache:
                del self.cache[key]
            self.cache[key] = (value, time.time())
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)

    def clear(self) -> None:
        if redis_client:
            try:
                for key in redis_client.scan_iter("cache:*"):
                    redis_client.delete(key)
            except Exception:
                pass
        with self.lock:
            self.cache.clear()

    @property
    def size(self) -> int:
        if redis_client:
            return 0
        with self.lock:
            return len(self.cache)


class SlidingWindowRateLimiter:
    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        is_abuse_sensitive: bool = False,
    ):
        self.rpm_limit = requests_per_minute
        self.rph_limit = requests_per_hour
        self.is_abuse_sensitive = is_abuse_sensitive
        self.windows: dict[str, list[float]] = defaultdict(list)
        self.lock = Lock()

    def _should_fail_closed(self) -> bool:
        """Determine if security rate limiters must fail closed when Redis is offline."""
        explicit_req = os.getenv("REQUIRE_REDIS_FAIL_CLOSED")
        if explicit_req is not None:
            return explicit_req.strip().lower() in ("true", "1", "yes")
        settings_req = getattr(settings, "REQUIRE_REDIS_FAIL_CLOSED", None)
        if settings_req is not None:
            return bool(settings_req)
        has_redis = bool(getattr(settings, "REDIS_URL", "") or os.getenv("REDIS_URL", ""))
        if not has_redis:
            return False
        env_name = (os.getenv("ENVIRONMENT") or getattr(settings, "ENVIRONMENT", "development")).lower()
        return env_name not in ("development", "dev")

    def is_allowed(self, client_id: str) -> bool:
        """
        Check rate limit.
        Fail-Closed Policy: If Redis is configured but drops connection for abuse-sensitive targets in non-dev environments,
        raises HTTP 503 to reject unthrottled login/signup/reset attempts.
        In development, gracefully degrades to in-memory sliding window rate limiting.
        """
        if redis_client:
            try:
                now = time.time()
                pipe = redis_client.pipeline()
                
                # per minute
                m_key = f"rate:{client_id}:minute"
                pipe.zremrangebyscore(m_key, 0, now - 60)
                pipe.zadd(m_key, {str(now): now})
                pipe.zcard(m_key)
                pipe.expire(m_key, 60)
                
                # per hour
                h_key = f"rate:{client_id}:hour"
                pipe.zremrangebyscore(h_key, 0, now - 3600)
                pipe.zadd(h_key, {str(now): now})
                pipe.zcard(h_key)
                pipe.expire(h_key, 3600)
                
                results = pipe.execute()
                recent_minute = results[2]
                recent_hour = results[6]
                
                if recent_minute > self.rpm_limit or recent_hour > self.rph_limit:
                    return False
                return True

            except Exception as e:
                logger.error(f"Redis rate limit connection error: {e}")
                if self.is_abuse_sensitive and self._should_fail_closed():
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Security rate-limiting service unavailable; failing closed for system protection",
                    )
                # Fallback to local in-memory window for non-security UI/read routes or dev mode

        with self.lock:
            if self.is_abuse_sensitive and self._should_fail_closed() and not redis_client:
                # If Redis is explicitly required for security rate limiters and unavailable
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Security rate-limiting service unavailable; failing closed for system protection",
                )
            now = time.time()
            minute_ago = now - 60
            hour_ago = now - 3600

            # Prune stale timestamps for this client
            valid_ts = [ts for ts in self.windows.get(client_id, []) if ts > hour_ago]
            if not valid_ts and client_id in self.windows:
                del self.windows[client_id]
            elif valid_ts:
                self.windows[client_id] = valid_ts

            recent_minute = [ts for ts in self.windows.get(client_id, []) if ts > minute_ago]
            if len(recent_minute) >= self.rpm_limit:
                return False
            if len(self.windows.get(client_id, [])) >= self.rph_limit:
                return False

            if client_id not in self.windows:
                # Bound maximum active clients in memory to 10,000 to prevent memory leaks
                if len(self.windows) >= 10000:
                    oldest_key = next(iter(self.windows))
                    del self.windows[oldest_key]
                self.windows[client_id] = []

            self.windows[client_id].append(now)
            return True

    def get_remaining_requests(self, client_id: str) -> dict[str, int]:
        if redis_client:
            try:
                recent_minute = redis_client.zcard(f"rate:{client_id}:minute") or 0
                recent_hour = redis_client.zcard(f"rate:{client_id}:hour") or 0
                return {
                    "remaining_per_minute": max(0, self.rpm_limit - recent_minute),
                    "remaining_per_hour": max(0, self.rph_limit - recent_hour),
                }
            except Exception:
                pass
                
        with self.lock:
            now = time.time()
            minute_ago = now - 60
            hour_ago = now - 3600
            client_ts = self.windows.get(client_id, [])
            valid_ts = [ts for ts in client_ts if ts > hour_ago]
            if not valid_ts and client_id in self.windows:
                del self.windows[client_id]
            recent_minute = len([ts for ts in valid_ts if ts > minute_ago])
            recent_hour = len(valid_ts)
            return {
                "remaining_per_minute": max(0, self.rpm_limit - recent_minute),
                "remaining_per_hour": max(0, self.rph_limit - recent_hour),
            }


# Global instances
response_cache = TimeboxedCache(
    max_size=100,
    ttl_seconds=settings.CACHE_TTL_SECONDS,
)

rate_limiter = SlidingWindowRateLimiter(
    requests_per_minute=settings.RATE_LIMIT_REQUESTS_PER_MINUTE,
    requests_per_hour=settings.RATE_LIMIT_REQUESTS_PER_HOUR,
)

# Auth Rate Limiter — Abuse sensitive (5 req/min, 50 req/hour, fail-closed policy)
auth_rate_limiter = SlidingWindowRateLimiter(
    requests_per_minute=5,
    requests_per_hour=50,
    is_abuse_sensitive=True,
)

# Admin Rate Limiter (10 req/min, 50 req/hour, fail-closed policy)
admin_rate_limiter = SlidingWindowRateLimiter(
    requests_per_minute=settings.ADMIN_RATE_LIMIT_PER_MINUTE,
    requests_per_hour=50,
    is_abuse_sensitive=True,
)


def cache_key_for_query(
    message: str,
    history_len: int,
    company_id: str = "",
    user_id: str = "",
    role: str = "",
) -> str:
    """Generate a multi-tenant, user-isolated cache key for HR bot responses."""
    key_parts = [
        company_id or "global",
        user_id or "anonymous",
        role or "employee",
        message.strip().lower(),
        str(history_len),
    ]
    combined = "|".join(key_parts)
    return hashlib.sha256(combined.encode()).hexdigest()[:32]
