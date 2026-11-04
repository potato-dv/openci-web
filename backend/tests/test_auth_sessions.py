from datetime import timedelta
from http.cookies import SimpleCookie
import hashlib
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException, Response
from fastapi.responses import JSONResponse
import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.database import Base
from app.models.auth_session import AuthRefreshToken, AuthSession
from app.models.user import User
from app.routes.user import (
    REFRESH_COOKIE_NAME,
    login_user,
    logout_user,
    record_user_activity,
    refresh_user_session,
)
from app.schemas.user import UserLogin
from app.services.auth_sessions import issue_session, utc_now
from app.controllers.user import update_activation, update_role
from app.utils.auth import get_current_auth_context
from app.utils.security import hash_password


SECRET = "test-only-auth-secret-with-enough-entropy"
ORIGIN = "http://localhost:5173"


def make_request(path: str, headers: dict[str, str] | None = None) -> Request:
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [
            (key.lower().encode(), value.encode())
            for key, value in (headers or {}).items()
        ],
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
    })


class AuthSessionAPITests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{self.tempdir.name}/auth.db")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(
            name="Test Agent",
            email="agent@example.test",
            password=hash_password("long-test-password"),
            role="agent",
        )
        self.admin = User(
            name="Test Admin",
            email="admin@example.test",
            password=hash_password("long-test-password"),
            role="admin",
        )
        self.db.add_all([self.user, self.admin])
        self.db.commit()
        self.user_id = self.user.id
        self.user_email = self.user.email
        self.secret_patch = patch("app.utils.auth.JWT_SECRET_KEY", SECRET)
        self.secret_patch.start()
        self.security_patch = patch("app.utils.security.JWT_SECRET_KEY", SECRET)
        self.security_patch.start()

    def tearDown(self):
        self.secret_patch.stop()
        self.security_patch.stop()
        self.db.close()
        self.engine.dispose()
        self.tempdir.cleanup()

    def auth_headers(self):
        return {"Origin": ORIGIN, "X-CSRF-Token": "1"}

    def login(self):
        response = Response()
        payload = login_user(
            UserLogin(email=self.user_email, password="long-test-password"),
            make_request("/users/login", self.auth_headers()),
            response,
            self.db,
        )
        return SimpleNamespace(status_code=response.status_code, headers=response.headers, json=lambda: payload)

    @staticmethod
    def refresh_cookie(response):
        parsed = SimpleCookie()
        parsed.load(response.headers["set-cookie"])
        key = next(iter(parsed.keys()))
        return key, parsed[key].value, parsed[key]

    def refresh(self, cookie_name: str, cookie_value: str):
        response = Response()
        request = make_request(
            "/users/refresh",
            {
                **self.auth_headers(),
                "Cookie": f"{cookie_name}={cookie_value}",
            },
        )
        try:
            payload = refresh_user_session(request, response, self.db)
            if isinstance(payload, JSONResponse):
                return SimpleNamespace(
                    status_code=payload.status_code,
                    headers=payload.headers,
                    json=lambda: json.loads(payload.body),
                )
            return SimpleNamespace(status_code=response.status_code, headers=response.headers, json=lambda: payload)
        except HTTPException as error:
            return SimpleNamespace(
                status_code=error.status_code,
                headers=response.headers,
                json=lambda: {"detail": error.detail},
            )

    def test_login_issues_short_access_token_and_httponly_secure_refresh_cookie(self):
        response = self.login()
        self.assertEqual(response.json()["token_type"], "bearer")
        claims = jwt.decode(
            response.json()["access_token"],
            SECRET,
            algorithms=["HS256"],
        )
        self.assertEqual(claims["typ"], "access")
        self.assertLessEqual(claims["exp"] - claims["iat"], 15 * 60)
        name, value, cookie = self.refresh_cookie(response)
        self.assertEqual(name, "__Secure-openci_refresh")
        self.assertIn("httponly", response.headers["set-cookie"].lower())
        self.assertIn("secure", response.headers["set-cookie"].lower())
        self.assertEqual(cookie["path"], "/users")
        self.assertEqual(cookie["samesite"], "lax")
        self.assertEqual(cookie["max-age"], "28800")
        self.assertEqual(len(value.split(".", 1)[1]), 43)
        session = self.db.query(AuthSession).one()
        self.assertEqual(session.absolute_expires_at - session.created_at, timedelta(hours=8))

        context = get_current_auth_context(response.json()["access_token"], self.db)
        self.assertEqual(context.user.id, self.user_id)

    def test_login_rejects_missing_csrf_header_and_unapproved_origin(self):
        payload = UserLogin(email=self.user_email, password="long-test-password")
        for headers in (
            {"Origin": ORIGIN},
            {"Origin": "https://attacker.example", "X-CSRF-Token": "1"},
        ):
            with self.subTest(headers=headers), self.assertRaises(HTTPException) as raised:
                login_user(payload, make_request("/users/login", headers), Response(), self.db)
            self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(self.db.query(AuthSession).count(), 0)

    def test_refresh_rotates_opaque_token_and_flags_reuse(self):
        login = self.login()
        cookie_name, old_cookie, _ = self.refresh_cookie(login)
        rotated = self.refresh(cookie_name, old_cookie)
        self.assertEqual(rotated.status_code, 200)
        self.assertNotEqual(rotated.json()["access_token"], login.json()["access_token"])
        _, new_cookie, _ = self.refresh_cookie(rotated)
        self.assertNotEqual(new_cookie, old_cookie)

        old_token_hash = hashlib.sha256(old_cookie.encode()).hexdigest()
        old_token = self.db.query(AuthRefreshToken).filter_by(token_hash=old_token_hash).one()
        self.assertIsNotNone(old_token.used_at)
        concurrent_reuse = self.refresh(cookie_name, old_cookie)
        self.assertEqual(concurrent_reuse.status_code, 409)
        self.assertIsNone(self.db.query(AuthSession).one().revoked_at)

        old_token.used_at = utc_now() - timedelta(seconds=20)
        self.db.commit()
        replay = self.refresh(cookie_name, old_cookie)
        self.assertEqual(replay.status_code, 401)
        self.assertIn("max-age=0", replay.headers["set-cookie"].lower())
        session = self.db.query(AuthSession).one()
        self.assertEqual(session.revoke_reason, "refresh_reuse")

    def test_logout_revokes_session_and_clears_cookie(self):
        login = self.login()
        cookie_name, cookie_value, _ = self.refresh_cookie(login)
        response = Response()
        logout_user(
            make_request(
                "/users/logout",
                {
                    **self.auth_headers(),
                    "Cookie": f"{cookie_name}={cookie_value}",
                },
            ),
            response,
            self.db,
        )
        session = self.db.query(AuthSession).one()
        self.assertEqual(session.revoke_reason, "logout")
        self.assertEqual(response.status_code, 204)
        self.assertIn("max-age=0", response.headers["set-cookie"].lower())

    def test_idle_expiration_revokes_session_and_returns_structured_reason(self):
        login = self.login()
        session = self.db.query(AuthSession).one()
        session.last_interactive_at = utc_now() - timedelta(minutes=31)
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            get_current_auth_context(login.json()["access_token"], self.db)
        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.detail["code"], "session_idle")
        self.db.refresh(session)
        self.assertEqual(session.revoke_reason, "idle_expired")

    def test_absolute_expiration_revokes_active_session(self):
        login = self.login()
        session = self.db.query(AuthSession).one()
        session.last_interactive_at = utc_now()
        session.absolute_expires_at = utc_now() - timedelta(seconds=1)
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            get_current_auth_context(login.json()["access_token"], self.db)

        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.detail["code"], "session_expired")
        self.db.refresh(session)
        self.assertEqual(session.revoke_reason, "absolute_expired")

    def test_interactive_activity_extends_only_the_idle_timestamp(self):
        login = self.login()
        context = get_current_auth_context(login.json()["access_token"], self.db)
        before = context.session.last_interactive_at
        absolute_expiry_before = context.session.absolute_expires_at
        response = Response()
        record_user_activity(response, context, self.db)
        self.assertEqual(response.status_code, 204)
        self.db.refresh(context.session)
        self.assertGreaterEqual(context.session.last_interactive_at, before)
        self.assertEqual(context.session.absolute_expires_at, absolute_expiry_before)

    def test_role_change_and_deactivation_revoke_existing_sessions(self):
        self.login()
        session = self.db.query(AuthSession).filter_by(user_id=self.user_id).one()
        update_role(self.db, self.user_id, "supervisor", self.admin)
        self.db.refresh(session)
        self.assertEqual(session.revoke_reason, "account_changed")

        issued = issue_session(self.db, self.db.get(User, self.user_id))
        current_session = self.db.get(AuthSession, UUID(issued.refresh_cookie.split(".", 1)[0]))
        update_activation(self.db, self.user_id, False, self.admin)
        self.db.refresh(current_session)
        self.assertEqual(current_session.revoke_reason, "account_changed")


if __name__ == "__main__":
    unittest.main()
