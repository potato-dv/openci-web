from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Response
from redis import Redis
from redis.exceptions import RedisError
from starlette.requests import Request

from app.config import settings
from app.routes import user as user_routes
from app.schemas.user import UserLogin
from app.services.rate_limit import LOGIN_FAILURE_POLICY, RateLimitPolicy, account_identifier_key, consume


@pytest.fixture
def redis_client(monkeypatch):
    url = os.getenv("RATE_LIMIT_TEST_REDIS_URL", "redis://localhost:6379/15")
    client = Redis.from_url(url, decode_responses=True, socket_connect_timeout=0.5)
    try:
        client.ping()
    except RedisError as error:
        client.close()
        pytest.skip(f"isolated rate-limit Redis is unavailable: {type(error).__name__}")
    namespace = f"collector:ratelimit:pytest-auth:{uuid4().hex}"
    monkeypatch.setattr(settings, "RATE_LIMIT_NAMESPACE", namespace)
    yield client
    keys = list(client.scan_iter(match=f"{namespace}:*"))
    if keys:
        client.delete(*keys)
    client.close()


def make_request(app: FastAPI, email: str, peer_ip: str) -> Request:
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/users/login",
        "raw_path": b"/users/login",
        "query_string": b"",
        "headers": [
            (b"origin", b"http://localhost:5173"),
            (b"x-csrf-token", b"1"),
            (b"content-type", b"application/json"),
        ],
        "client": (peer_ip, 50000),
        "server": ("localhost", 8000),
        "app": app,
    })


def test_failed_login_throttle_is_account_scoped_but_does_not_block_valid_password(
    redis_client, monkeypatch,
):
    app = FastAPI()
    app.state.rate_limit_redis = redis_client
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    email = f"login-{uuid4().hex}@example.test"
    payload = UserLogin(email=email, password="wrong-password")

    def invalid_login(_db, _data):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    monkeypatch.setattr(user_routes, "login", invalid_login)
    responses = []
    for index in range(5):
        try:
            user_routes.login_user(payload, make_request(app, email, f"192.0.2.{index + 1}"), Response(), None)
        except HTTPException as error:
            responses.append(error)
    assert [error.status_code for error in responses] == [401] * 5
    assert {error.detail for error in responses} == {"Invalid email or password"}

    with pytest.raises(HTTPException) as limited:
        user_routes.login_user(payload, make_request(app, email, "192.0.2.20"), Response(), None)
    assert limited.value.status_code == 429
    assert limited.value.detail["code"] == "RATE_LIMIT_EXCEEDED"

    def valid_login(_db, _data):
        return SimpleNamespace(access_token="test-access-token", refresh_cookie="test-cookie", refresh_max_age=60)

    monkeypatch.setattr(user_routes, "login", valid_login)
    response = Response()
    result = user_routes.login_user(
        UserLogin(email=email, password="correct-password"),
        make_request(app, email, "192.0.2.21"),
        response,
        None,
    )
    assert result["access_token"] == "test-access-token"
    assert response.headers.get("set-cookie")

    reset_state = consume(redis_client, LOGIN_FAILURE_POLICY, account_identifier_key(email))
    assert reset_state.allowed is True


def test_login_ip_limit_is_separate_and_does_not_cross_ips(redis_client, monkeypatch):
    app = FastAPI()
    app.state.rate_limit_redis = redis_client
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(user_routes, "LOGIN_IP_POLICY", RateLimitPolicy("login:ip-test", 2, 60, True))
    email = f"ip-{uuid4().hex}@example.test"
    monkeypatch.setattr(
        user_routes,
        "login",
        lambda _db, _data: SimpleNamespace(
            access_token="test-access-token",
            refresh_cookie="test-cookie",
            refresh_max_age=60,
        ),
    )

    for _ in range(2):
        assert user_routes.login_user(
            UserLogin(email=email, password="correct-password"),
            make_request(app, email, "192.0.2.30"),
            Response(),
            None,
        )["token_type"] == "bearer"
    with pytest.raises(HTTPException) as limited:
        user_routes.login_user(
            UserLogin(email=email, password="correct-password"),
            make_request(app, email, "192.0.2.30"),
            Response(),
            None,
        )
    assert limited.value.status_code == 429

    assert user_routes.login_user(
        UserLogin(email=email, password="correct-password"),
        make_request(app, email, "192.0.2.31"),
        Response(),
        None,
    )["token_type"] == "bearer"
