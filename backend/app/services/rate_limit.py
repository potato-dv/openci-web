from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException, Request, Response, status
from redis import Redis
from redis.exceptions import RedisError

from app.config import settings


logger = logging.getLogger("app.rate_limit")

_SLIDING_WINDOW = """
local key = KEYS[1]
local now_parts = redis.call('TIME')
local now = (tonumber(now_parts[1]) * 1000) + math.floor(tonumber(now_parts[2]) / 1000)
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local member = ARGV[3]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry = math.max(1, math.ceil((tonumber(oldest[2]) + window - now) / 1000))
  redis.call('PEXPIRE', key, window)
  return {0, 0, retry, math.ceil((tonumber(oldest[2]) + window - now) / 1000)}
end
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, window)
local remaining = limit - count - 1
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local reset = math.max(1, math.ceil((tonumber(oldest[2]) + window - now) / 1000))
return {1, remaining, 0, reset}
"""

_log_lock = Lock()
_last_redis_error_log: dict[str, float] = {}
_last_denied_log: dict[str, float] = {}
_denied_since_log: dict[str, int] = {}


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_seconds: int
    fail_closed: bool = False


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int
    reset_after_seconds: int


GENERAL_POLICY = RateLimitPolicy(
    "general", settings.RATE_LIMIT_GENERAL_LIMIT, settings.RATE_LIMIT_GENERAL_WINDOW_SECONDS,
)
WRITE_POLICY = RateLimitPolicy(
    "write", settings.RATE_LIMIT_WRITE_LIMIT, settings.RATE_LIMIT_WRITE_WINDOW_SECONDS,
    fail_closed=True,
)
LOGIN_IP_POLICY = RateLimitPolicy(
    "login:ip", settings.RATE_LIMIT_LOGIN_IP_LIMIT,
    settings.RATE_LIMIT_LOGIN_IP_WINDOW_SECONDS, fail_closed=True,
)
LOGIN_FAILURE_POLICY = RateLimitPolicy(
    "login:failure", settings.RATE_LIMIT_LOGIN_FAILURE_LIMIT,
    settings.RATE_LIMIT_LOGIN_FAILURE_WINDOW_SECONDS, fail_closed=True,
)
AUTH_SESSION_POLICY = RateLimitPolicy(
    "auth:session", settings.RATE_LIMIT_AUTH_SESSION_LIMIT,
    settings.RATE_LIMIT_AUTH_SESSION_WINDOW_SECONDS, fail_closed=True,
)
PLANNING_POLICY = RateLimitPolicy(
    "planning:enqueue", settings.RATE_LIMIT_PLANNING_LIMIT,
    settings.RATE_LIMIT_PLANNING_WINDOW_SECONDS, fail_closed=True,
)


def client_ip(request: Request) -> str:
    """Use the socket peer; forwarded headers are untrusted in this deployment."""
    return request.client.host if request.client and request.client.host else "unknown"


def account_identifier_key(email: str) -> str:
    normalized = email.strip().casefold()
    secret = settings.RATE_LIMIT_HASH_SECRET.encode("utf-8")
    opaque = hmac.new(secret, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{settings.RATE_LIMIT_NAMESPACE}:{{{settings.RATE_LIMIT_NAMESPACE}}}:{opaque}"


def _key(policy: RateLimitPolicy, identifier: str) -> str:
    # Hash arbitrary identifiers so Redis keys never expose IPs or account data.
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    return f"{settings.RATE_LIMIT_NAMESPACE}:{{{settings.RATE_LIMIT_NAMESPACE}}}:{policy.name}:{digest}"


def _log_redis_failure(category: str, error: Exception) -> None:
    now = time.monotonic()
    with _log_lock:
        last = _last_redis_error_log.get(category, 0.0)
        if now - last < settings.RATE_LIMIT_LOG_COOLDOWN_SECONDS:
            return
        _last_redis_error_log[category] = now
    logger.error(
        "rate_limit_redis_unavailable category=%s exception_type=%s",
        category,
        type(error).__name__,
    )


def _record_denial(category: str) -> None:
    now = time.monotonic()
    with _log_lock:
        _denied_since_log[category] = _denied_since_log.get(category, 0) + 1
        last = _last_denied_log.get(category, 0.0)
        if now - last < settings.RATE_LIMIT_LOG_COOLDOWN_SECONDS:
            return
        count = _denied_since_log[category]
        _denied_since_log[category] = 0
        _last_denied_log[category] = now
    logger.warning("rate_limit_denied category=%s aggregated_count=%s", category, count)


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "RATE_LIMIT_UNAVAILABLE",
            "message": "Request protection is temporarily unavailable. Please try again shortly.",
            "retry_after_seconds": 5,
        },
        headers={"Retry-After": "5"},
    )


def consume(
    redis: Redis,
    policy: RateLimitPolicy,
    identifier: str,
) -> RateLimitResult:
    result = redis.eval(
        _SLIDING_WINDOW,
        1,
        _key(policy, identifier),
        policy.window_seconds * 1000,
        policy.limit,
        uuid4().hex,
    )
    return RateLimitResult(
        allowed=bool(int(result[0])),
        limit=policy.limit,
        remaining=int(result[1]),
        retry_after_seconds=int(result[2]),
        reset_after_seconds=int(result[3]),
    )


def clear_counter(redis: Redis, policy: RateLimitPolicy, identifier: str) -> None:
    redis.delete(_key(policy, identifier))


def _set_headers(response: Response, result: RateLimitResult) -> None:
    response.headers["X-RateLimit-Limit"] = str(result.limit)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
    response.headers["X-RateLimit-Reset"] = str(int(time.time()) + result.reset_after_seconds)


def enforce(
    request: Request,
    response: Response,
    policy: RateLimitPolicy,
    identifier: str,
) -> RateLimitResult | None:
    if not settings.RATE_LIMIT_ENABLED:
        return None
    redis: Redis | None = getattr(request.app.state, "rate_limit_redis", None)
    if redis is None:
        error = RuntimeError("Rate-limit Redis client is not initialized")
        _log_redis_failure(policy.name, error)
        if policy.fail_closed:
            raise _unavailable()
        return None
    try:
        result = consume(redis, policy, identifier)
    except (RedisError, OSError, TimeoutError) as error:
        _log_redis_failure(policy.name, error)
        if policy.fail_closed:
            raise _unavailable() from error
        return None
    _set_headers(response, result)
    if not result.allowed:
        _record_denial(policy.name)
        retry_after = max(1, result.retry_after_seconds)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Too many requests. Please try again later.",
                "retry_after_seconds": retry_after,
            },
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + result.reset_after_seconds),
            },
        )
    return result


def limit_login_failure(redis: Redis, email: str) -> RateLimitResult:
    identifier = account_identifier_key(email)
    try:
        return consume(redis, LOGIN_FAILURE_POLICY, identifier)
    except (RedisError, OSError, TimeoutError) as error:
        _log_redis_failure(LOGIN_FAILURE_POLICY.name, error)
        raise _unavailable() from error


def clear_login_failures(redis: Redis, email: str) -> None:
    identifier = account_identifier_key(email)
    try:
        clear_counter(redis, LOGIN_FAILURE_POLICY, identifier)
    except (RedisError, OSError, TimeoutError) as error:
        _log_redis_failure(LOGIN_FAILURE_POLICY.name, error)
        # The login request already passed the fail-closed IP check and the
        # credentials were verified; do not strand a newly issued session if
        # Redis fails only during best-effort success cleanup.


def apply_rate_headers(response: Response, result: RateLimitResult) -> None:
    _set_headers(response, result)
