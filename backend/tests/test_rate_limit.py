from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from redis import Redis
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from types import SimpleNamespace

from app.dependencies import rate_limit as rate_limit_dependencies
from app.services.rate_limit import (
    LOGIN_FAILURE_POLICY,
    RateLimitPolicy,
    account_identifier_key,
    clear_counter,
    consume,
)
from app.utils.auth import get_current_user


@pytest.fixture
def rate_limit_redis(monkeypatch):
    url = os.getenv("RATE_LIMIT_TEST_REDIS_URL", "redis://localhost:6379/15")
    client = Redis.from_url(url, decode_responses=True, socket_connect_timeout=0.5)
    try:
        client.ping()
    except RedisError as error:
        client.close()
        pytest.skip(f"isolated rate-limit Redis is unavailable: {type(error).__name__}")

    namespace = f"collector:ratelimit:pytest:{uuid4().hex}"
    monkeypatch.setattr("app.services.rate_limit.settings.RATE_LIMIT_NAMESPACE", namespace)
    yield client

    # Delete only this test's namespaced keys. Never flush a shared Redis DB.
    keys = list(client.scan_iter(match=f"{namespace}:*"))
    if keys:
        client.delete(*keys)
    client.close()


def test_sliding_window_boundaries_and_expiry(rate_limit_redis):
    policy = RateLimitPolicy("boundary", limit=3, window_seconds=1)
    identity = f"user:{uuid4().hex}"

    first = [consume(rate_limit_redis, policy, identity) for _ in range(3)]
    denied = consume(rate_limit_redis, policy, identity)

    assert all(result.allowed for result in first)
    assert [result.remaining for result in first] == [2, 1, 0]
    assert denied.allowed is False
    assert denied.retry_after_seconds >= 1

    time.sleep(1.1)
    recovered = consume(rate_limit_redis, policy, identity)
    assert recovered.allowed is True


def test_users_and_account_keys_are_isolated_and_opaque(rate_limit_redis):
    policy = RateLimitPolicy("identity", limit=1, window_seconds=60)
    first = f"user:{uuid4().hex}"
    second = f"user:{uuid4().hex}"
    assert consume(rate_limit_redis, policy, first).allowed
    assert consume(rate_limit_redis, policy, first).allowed is False
    assert consume(rate_limit_redis, policy, second).allowed

    address = "Private.User@example.test"
    key_identity = account_identifier_key(address)
    assert "Private.User@example.test" not in key_identity
    assert "private.user@example.test" not in key_identity
    assert account_identifier_key(address) == account_identifier_key(address.lower())


def test_client_ip_ignores_untrusted_forwarded_headers():
    from app.services.rate_limit import client_ip

    request = Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [(b"x-forwarded-for", b"203.0.113.99")],
        "client": ("192.0.2.5", 50000),
        "server": ("localhost", 8000),
    })
    assert client_ip(request) == "192.0.2.5"


def test_concurrent_requests_share_one_atomic_counter(rate_limit_redis):
    policy = RateLimitPolicy("parallel", limit=10, window_seconds=60)
    identity = f"user:{uuid4().hex}"
    second_client = Redis.from_url(
        os.getenv("RATE_LIMIT_TEST_REDIS_URL", "redis://localhost:6379/15"),
        decode_responses=True,
    )
    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(
            lambda index: consume(
                rate_limit_redis if index % 2 == 0 else second_client,
                policy,
                identity,
            ),
            range(50),
        ))
    second_client.close()
    assert sum(result.allowed for result in results) == 10
    assert sum(not result.allowed for result in results) == 40


def test_successful_login_can_clear_only_its_failure_bucket(rate_limit_redis):
    email = f"test-{uuid4().hex}@example.test"
    identifier = account_identifier_key(email)
    results = [consume(rate_limit_redis, LOGIN_FAILURE_POLICY, identifier) for _ in range(5)]
    assert all(result.allowed for result in results)
    assert consume(rate_limit_redis, LOGIN_FAILURE_POLICY, identifier).allowed is False

    clear_counter(rate_limit_redis, LOGIN_FAILURE_POLICY, identifier)
    assert consume(rate_limit_redis, LOGIN_FAILURE_POLICY, identifier).allowed is True


def test_general_counter_is_shared_between_endpoint_paths(rate_limit_redis, monkeypatch):
    monkeypatch.setattr(
        rate_limit_dependencies,
        "GENERAL_POLICY",
        RateLimitPolicy("general-api-test", limit=3, window_seconds=60),
    )
    app = FastAPI()
    app.state.rate_limit_redis = rate_limit_redis
    app.state.user_id = 7001
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=app.state.user_id)
    app.add_api_route("/dashboard", lambda: {"ok": True}, dependencies=[Depends(rate_limit_dependencies.general_api_rate_limit)])
    app.add_api_route("/investigations", lambda: {"ok": True}, dependencies=[Depends(rate_limit_dependencies.general_api_rate_limit)])

    with TestClient(app) as client:
        assert client.get("/dashboard").status_code == 200
        assert client.get("/investigations").status_code == 200
        assert client.get("/dashboard").status_code == 200
        limited = client.get("/investigations")
        assert limited.status_code == 429
        assert limited.headers["retry-after"]
        assert limited.json()["detail"]["code"] == "RATE_LIMIT_EXCEEDED"

        app.state.user_id = 7002
        assert client.get("/dashboard").status_code == 200


def test_planning_enqueue_uses_a_separate_counter(rate_limit_redis, monkeypatch):
    monkeypatch.setattr(
        rate_limit_dependencies,
        "GENERAL_POLICY",
        RateLimitPolicy("general-separate-test", limit=1, window_seconds=60),
    )
    monkeypatch.setattr(
        rate_limit_dependencies,
        "PLANNING_POLICY",
        RateLimitPolicy("planning-separate-test", limit=1, window_seconds=60, fail_closed=True),
    )
    app = FastAPI()
    app.state.rate_limit_redis = rate_limit_redis
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=8001)
    app.add_api_route("/dashboard", lambda: {"ok": True}, dependencies=[Depends(rate_limit_dependencies.general_api_rate_limit)])
    app.add_api_route(
        "/planning/retry",
        lambda: {"ok": True},
        methods=["POST"],
        dependencies=[Depends(rate_limit_dependencies.planning_enqueue_rate_limit)],
    )

    with TestClient(app) as client:
        assert client.get("/dashboard").status_code == 200
        assert client.post("/planning/retry").status_code == 200
        assert client.post("/planning/retry").status_code == 429


def test_redis_outage_fails_closed_for_planning_and_open_for_general_reads(monkeypatch):
    class UnavailableRedis:
        def eval(self, *_args):
            raise RedisConnectionError("redis unavailable")

    monkeypatch.setattr("app.services.rate_limit.settings.RATE_LIMIT_ENABLED", True)
    app = FastAPI()
    app.state.rate_limit_redis = UnavailableRedis()
    app.state.user_id = 9001
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=app.state.user_id)
    app.add_api_route("/read", lambda: {"ok": True}, dependencies=[Depends(rate_limit_dependencies.general_api_rate_limit)])
    app.add_api_route(
        "/write",
        lambda: {"ok": True},
        methods=["POST"],
        dependencies=[Depends(rate_limit_dependencies.general_api_rate_limit)],
    )
    app.add_api_route(
        "/planning/retry",
        lambda: {"ok": True},
        methods=["POST"],
        dependencies=[Depends(rate_limit_dependencies.planning_enqueue_rate_limit)],
    )

    with TestClient(app) as client:
        assert client.get("/read").status_code == 200
        assert client.post("/write").status_code == 503
        response = client.post("/planning/retry")
        assert response.status_code == 503
        assert response.headers["retry-after"] == "5"
        assert response.json()["detail"]["code"] == "RATE_LIMIT_UNAVAILABLE"
