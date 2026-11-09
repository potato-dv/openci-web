from __future__ import annotations

import asyncio
import json
import logging
import random
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any
from uuid import UUID

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import (
    AUTH_SESSION_IDLE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
    REALTIME_AUTH_TIMEOUT_SECONDS,
    REALTIME_IDLE_TIMEOUT_SECONDS,
    REALTIME_MAX_CONNECTIONS_PER_USER,
    REALTIME_MAX_CONNECTIONS_PER_WORKER,
    REALTIME_OUTBOX_POLL_SECONDS,
    REALTIME_OUTBOX_RETENTION_DAYS,
    REALTIME_REDIS_CHANNEL,
)
from app.database.session import SessionLocal
from app.models.auth_session import AuthSession
from app.models.investigation import Investigation
from app.models.realtime_outbox import RealtimeOutboxEvent
from app.models.user import User
from app.realtime.event_mapping import event_scope_names
from app.services.agent_permissions import is_agent_feature_allowed
from app.services.auth_sessions import _aware, utc_now
from app.services.investigation import can_access_investigation
from app.utils.auth import is_allowed_websocket_origin


logger = logging.getLogger("app.realtime")
router = APIRouter(tags=["Real-time"])
MAX_CLIENT_MESSAGE_BYTES = 8_192
MAX_SUBSCRIPTIONS = 64
MAX_OUTBOUND_QUEUE = 128
EVENT_ID_CACHE_SIZE = 512
ALLOWED_FIXED_SCOPES = {
    "me", "dashboard", "investigations", "reports.queue", "route.planning",
    "route.own", "activity.logs", "users", "schedules",
    "role:admin", "role:supervisor", "role:agent",
}


class WebSocketAuthError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(eq=False)
class WebSocketConnection:
    websocket: WebSocket
    user_id: int
    session_id: UUID
    role: str
    token: str
    token_expires_at: datetime
    subscriptions: set[str]
    outbound: asyncio.Queue[dict[str, Any]] = field(
        default_factory=lambda: asyncio.Queue(maxsize=MAX_OUTBOUND_QUEUE),
    )
    last_message_at: float = field(default_factory=monotonic)
    recent_event_ids: deque[str] = field(default_factory=lambda: deque(maxlen=EVENT_ID_CACHE_SIZE))
    closed: bool = False


def authenticate_websocket(db: Session, token: str) -> tuple[User, AuthSession, datetime]:
    if not token or len(token) > 4_096:
        raise WebSocketAuthError("session_revoked")
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "sid", "iat", "exp", "typ", "jti"]},
        )
        if payload.get("typ") != "access":
            raise InvalidTokenError("Wrong token type")
        user_id = int(payload["sub"])
        session_id = UUID(str(payload["sid"]))
        expires_at = datetime.fromtimestamp(float(payload["exp"]), tz=timezone.utc)
    except ExpiredSignatureError as error:
        raise WebSocketAuthError("access_token_expired") from error
    except (InvalidTokenError, KeyError, ValueError, TypeError, OverflowError) as error:
        raise WebSocketAuthError("session_revoked") from error

    auth_session = db.query(AuthSession).filter(AuthSession.id == session_id).first()
    if auth_session is None or auth_session.user_id != user_id or auth_session.revoked_at is not None:
        raise WebSocketAuthError("session_revoked")
    now = utc_now()
    if now >= _aware(auth_session.absolute_expires_at):
        auth_session.revoked_at = now
        auth_session.revoke_reason = "absolute_expired"
        db.commit()
        raise WebSocketAuthError("session_expired")
    if now - _aware(auth_session.last_interactive_at) >= timedelta(minutes=AUTH_SESSION_IDLE_MINUTES):
        auth_session.revoked_at = now
        auth_session.revoke_reason = "idle_expired"
        db.commit()
        raise WebSocketAuthError("session_idle")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise WebSocketAuthError("session_revoked")
    return user, auth_session, expires_at


def scope_is_authorized(db: Session, user: User, scope: str) -> bool:
    if scope.startswith("role:"):
        return scope.partition(":")[2] == user.role
    if scope in {"me", "dashboard"}:
        return True
    if scope == "investigations":
        return user.role in {"admin", "supervisor", "agent"}
    if scope == "reports.queue":
        return user.role in {"admin", "supervisor"}
    if scope == "route.planning":
        return user.role in {"admin", "supervisor"}
    if scope == "route.own":
        return user.role == "agent"
    if scope == "activity.logs":
        return user.role == "admin"
    if scope == "users":
        return user.role == "admin"
    if scope == "schedules":
        return user.role in {"admin", "supervisor", "agent"}
    if scope.startswith("investigation:"):
        try:
            raw_id = scope.partition(":")[2]
            if not raw_id.isdecimal() or len(raw_id) > 10:
                return False
            investigation_id = int(raw_id)
            if not 1 <= investigation_id <= 2_147_483_647:
                return False
        except (TypeError, ValueError):
            return False
        case = db.query(Investigation).filter(
            Investigation.id == investigation_id,
            Investigation.deleted_at.is_(None),
        ).first()
        if case is None or not can_access_investigation(case, user):
            return False
        if user.role == "agent" and case.status == "completed":
            return is_agent_feature_allowed(db, user, "investigation.view_own_history")
        return True
    return False


def _event_audience_matches(connection: WebSocketConnection, envelope: dict[str, Any], current_role: str) -> bool:
    target_users = envelope.get("recipient_user_ids") or []
    target_roles = envelope.get("recipient_roles") or []
    return connection.user_id in target_users or current_role in target_roles


def _event_matches_scopes(
    scopes: set[str],
    envelope: dict[str, Any],
    current_role: str | None = None,
    user_id: int | None = None,
) -> bool:
    if current_role and f"role:{current_role}" in scopes:
        if current_role in (envelope.get("recipient_roles") or []):
            return True
    allowed_scopes = set(event_scope_names(str(envelope.get("event_type", ""))))
    if "me" in allowed_scopes:
        allowed_scopes.discard("me")
        if "me" in scopes and user_id in (envelope.get("recipient_user_ids") or []):
            return True
    if scopes.intersection(allowed_scopes):
        return True
    investigation_id = envelope.get("investigation_id")
    return investigation_id is not None and f"investigation:{investigation_id}" in scopes


def _client_event(envelope: dict[str, Any]) -> dict[str, Any]:
    # Recipient and region metadata are server-only and never enter the client frame.
    occurred_at = envelope.get("occurred_at")
    if isinstance(occurred_at, datetime):
        timestamp = occurred_at.isoformat()
    else:
        timestamp = str(occurred_at)
    event_type = str(envelope["event_type"])
    entity_id: int | str = envelope["entity_id"]
    if isinstance(entity_id, str) and entity_id.isdecimal():
        entity_id = int(entity_id)
    frame = {
        "type": "event",
        "event_id": str(envelope["event_id"]),
        "name": event_type,
        "entity_type": envelope["entity_type"],
        "entity_id": entity_id,
        "investigation_id": envelope.get("investigation_id"),
        "timestamp": timestamp,
    }
    if envelope.get("entity_type") in {"agent_schedule", "agent_shift"}:
        recipients = envelope.get("recipient_user_ids") or []
        affected_agent_id = next(
            (user_id for user_id in recipients if isinstance(user_id, int) and user_id > 0),
            None,
        )
        if affected_agent_id is not None:
            frame["affected_agent_id"] = affected_agent_id
    return frame


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocketConnection] = set()
        self._lock = asyncio.Lock()

    async def register(self, connection: WebSocketConnection) -> bool:
        async with self._lock:
            if len(self._connections) >= REALTIME_MAX_CONNECTIONS_PER_WORKER:
                return False
            user_count = sum(item.user_id == connection.user_id for item in self._connections)
            if user_count >= REALTIME_MAX_CONNECTIONS_PER_USER:
                return False
            self._connections.add(connection)
            return True

    async def unregister(self, connection: WebSocketConnection) -> None:
        async with self._lock:
            self._connections.discard(connection)
            connection.closed = True

    async def snapshot(self) -> list[WebSocketConnection]:
        async with self._lock:
            return list(self._connections)

    async def enqueue(self, connection: WebSocketConnection, message: dict[str, Any]) -> None:
        if connection.closed:
            return
        try:
            connection.outbound.put_nowait(message)
        except asyncio.QueueFull:
            try:
                connection.outbound.put_nowait({"_close_code": 1013})
            except asyncio.QueueFull:
                pass

    async def publish(self, envelope: dict[str, Any]) -> None:
        event_id = str(envelope.get("event_id", ""))
        candidates = [
            connection
            for connection in await self.snapshot()
            if event_id not in connection.recent_event_ids
            and _event_audience_matches(connection, envelope, connection.role)
            and _event_matches_scopes(connection.subscriptions, envelope, connection.role, connection.user_id)
        ]
        validations = await asyncio.gather(
            *(asyncio.to_thread(_validate_delivery, connection) for connection in candidates),
            return_exceptions=True,
        )
        for connection, validation in zip(candidates, validations):
            if isinstance(validation, asyncio.CancelledError):
                raise validation
            if isinstance(validation, BaseException):
                logger.warning("Realtime delivery authorization failed (%s)", type(validation).__name__)
                await self.enqueue(connection, {"_close_code": 1011})
                continue
            current_user, valid_scopes, invalid = validation
            if invalid:
                code = 4403 if invalid == "permissions_changed" else 4401
                await self.enqueue(connection, {"_close_code": code})
                continue
            if current_user is None or not _event_audience_matches(connection, envelope, current_user.role):
                continue
            connection.subscriptions.intersection_update(valid_scopes)
            if not _event_matches_scopes(connection.subscriptions, envelope, current_user.role, current_user.id):
                continue
            if current_user.role == "agent" and envelope.get("investigation_id") is not None:
                try:
                    owns_case = await asyncio.to_thread(
                        _agent_still_owns_investigation,
                        connection.user_id,
                        int(envelope["investigation_id"]),
                    )
                except Exception as error:
                    logger.warning("Realtime record authorization failed (%s)", type(error).__name__)
                    await self.enqueue(connection, {"_close_code": 1011})
                    continue
                if not owns_case:
                    continue
            if str(envelope.get("event_type", "")).startswith("user.permissions_changed") and connection.user_id in (envelope.get("recipient_user_ids") or []):
                await self.enqueue(connection, {"_close_code": 4403})
                continue
            if str(envelope.get("event_type", "")).startswith(("user.role_changed", "user.deactivated")) and connection.user_id in (envelope.get("recipient_user_ids") or []):
                await self.enqueue(connection, {"_close_code": 4401})
                continue
            connection.recent_event_ids.append(event_id)
            await self.enqueue(connection, _client_event(envelope))

    async def close_all(self, code: int = 1001) -> None:
        for connection in await self.snapshot():
            await self.enqueue(connection, {"_close_code": code})

    async def request_resync(self) -> None:
        for connection in await self.snapshot():
            await self.enqueue(connection, {"type": "resync"})


def _validate_delivery(connection: WebSocketConnection) -> tuple[User | None, set[str], str | None]:
    db = SessionLocal()
    try:
        try:
            user, auth_session, expires_at = authenticate_websocket(db, connection.token)
        except WebSocketAuthError:
            return None, set(), "session_expired"
        if user.id != connection.user_id or auth_session.id != connection.session_id:
            return None, set(), "session_changed"
        allowed = {
            scope for scope in connection.subscriptions
            if scope_is_authorized(db, user, scope)
        }
        if allowed != connection.subscriptions:
            return user, allowed, "permissions_changed"
        return user, allowed, None
    finally:
        db.close()


def _agent_still_owns_investigation(user_id: int, investigation_id: int) -> bool:
    db = SessionLocal()
    try:
        case = db.query(Investigation.status).filter(
            Investigation.id == investigation_id,
            Investigation.assigned_agent_id == user_id,
            Investigation.deleted_at.is_(None),
        ).first()
        if case is None:
            return False
        if case.status == "completed":
            user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
            return user is not None and user.role == "agent" and is_agent_feature_allowed(
                db, user, "investigation.view_own_history",
            )
        return True
    finally:
        db.close()


manager = ConnectionManager()


def _decode_client_message(raw: str) -> dict[str, Any]:
    if len(raw.encode("utf-8")) > MAX_CLIENT_MESSAGE_BYTES:
        raise ValueError("message_too_large")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("invalid_message")
    return value


def _authorize_requested_scopes(token: str, requested: object) -> tuple[User, AuthSession, datetime, set[str], list[str]]:
    if not isinstance(requested, list) or len(requested) > MAX_SUBSCRIPTIONS:
        raise WebSocketAuthError("invalid_subscriptions")
    db = SessionLocal()
    try:
        user, auth_session, expires_at = authenticate_websocket(db, token)
        authorized: set[str] = set()
        denied: list[str] = []
        for raw_scope in requested:
            if not isinstance(raw_scope, str) or len(raw_scope) > 100:
                denied.append("invalid")
                continue
            scope = raw_scope.strip()
            if scope not in ALLOWED_FIXED_SCOPES and not scope.startswith("investigation:"):
                denied.append(scope[:80])
            elif scope_is_authorized(db, user, scope):
                authorized.add(scope)
            else:
                denied.append(scope[:80])
        return user, auth_session, expires_at, authorized, denied
    finally:
        db.close()


def _make_envelope(row: RealtimeOutboxEvent) -> dict[str, Any]:
    return {
        "event_id": str(row.event_id),
        "event_type": row.event_type,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "investigation_id": row.investigation_id,
        "recipient_user_ids": row.recipient_user_ids or [],
        "recipient_roles": row.recipient_roles or [],
        "occurred_at": row.occurred_at.isoformat(),
    }


async def run_outbox_relay(redis: Redis, stop: asyncio.Event) -> None:
    next_prune_at = monotonic() + 3_600
    while not stop.is_set():
        db = SessionLocal()
        try:
            now = utc_now()
            if monotonic() >= next_prune_at:
                old_rows = db.execute(
                    select(RealtimeOutboxEvent)
                    .where(
                        RealtimeOutboxEvent.published_at.is_not(None),
                        RealtimeOutboxEvent.published_at < now - timedelta(days=REALTIME_OUTBOX_RETENTION_DAYS),
                    )
                    .order_by(RealtimeOutboxEvent.id)
                    .limit(500)
                    .with_for_update(skip_locked=True)
                ).scalars().all()
                for old_row in old_rows:
                    db.delete(old_row)
                db.commit()
                next_prune_at = monotonic() + 3_600
            row = db.execute(
                select(RealtimeOutboxEvent)
                .where(
                    RealtimeOutboxEvent.published_at.is_(None),
                    RealtimeOutboxEvent.available_at <= now,
                )
                .order_by(RealtimeOutboxEvent.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).scalars().first()
            if row is None:
                db.rollback()
                try:
                    await asyncio.wait_for(stop.wait(), timeout=REALTIME_OUTBOX_POLL_SECONDS)
                except asyncio.TimeoutError:
                    pass
                continue
            try:
                await redis.publish(REALTIME_REDIS_CHANNEL, json.dumps(_make_envelope(row), separators=(",", ":")))
            except Exception as error:
                # Keep retry metadata generic so Redis URLs or payloads never enter logs.
                row.attempt_count += 1
                row.available_at = utc_now() + timedelta(seconds=min(60, 2 ** min(row.attempt_count, 6)) + random.random())
                row.last_error = type(error).__name__[:80]
                db.commit()
                logger.warning("Realtime outbox publish failed (%s)", type(error).__name__)
            else:
                row.published_at = utc_now()
                row.attempt_count += 1
                row.last_error = None
                db.commit()
        except Exception as error:
            db.rollback()
            logger.warning("Realtime outbox relay failed (%s)", type(error).__name__)
            try:
                await asyncio.wait_for(stop.wait(), timeout=max(1.0, REALTIME_OUTBOX_POLL_SECONDS))
            except asyncio.TimeoutError:
                pass
        finally:
            db.close()


async def run_redis_listener(redis: Redis, stop: asyncio.Event) -> None:
    delay = 0.5
    while not stop.is_set():
        pubsub = redis.pubsub(ignore_subscribe_messages=True)
        try:
            await pubsub.subscribe(REALTIME_REDIS_CHANNEL)
            delay = 0.5
            await manager.request_resync()
            while not stop.is_set():
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is None:
                    continue
                if message.get("type") != "message":
                    continue
                try:
                    envelope = json.loads(message.get("data", "{}"))
                    if isinstance(envelope, dict) and envelope.get("event_id"):
                        await manager.publish(envelope)
                except (json.JSONDecodeError, TypeError, ValueError):
                    logger.warning("Discarded malformed realtime Redis message")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning("Realtime Redis listener disconnected (%s)", type(error).__name__)
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay + random.random() * delay)
            except asyncio.TimeoutError:
                pass
            delay = min(delay * 2, 15)
        finally:
            try:
                await pubsub.aclose()
            except Exception:
                pass


async def _writer(connection: WebSocketConnection) -> None:
    while not connection.closed:
        message = await connection.outbound.get()
        if "_close_code" in message:
            try:
                await connection.websocket.close(code=int(message["_close_code"]))
            except Exception:
                pass
            return
        await connection.websocket.send_json(message)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    if not is_allowed_websocket_origin(websocket.headers.get("origin")):
        await websocket.close(code=4403, reason="origin_not_allowed")
        return
    await websocket.accept()
    connection: WebSocketConnection | None = None
    writer_task: asyncio.Task | None = None
    try:
        try:
            first_raw = await asyncio.wait_for(
                websocket.receive_text(), timeout=REALTIME_AUTH_TIMEOUT_SECONDS,
            )
            first = _decode_client_message(first_raw)
            if first.get("type") != "auth" or not isinstance(first.get("token"), str):
                raise WebSocketAuthError("authentication_required")
            user, auth_session, expires_at, scopes, denied = await asyncio.to_thread(
                _authorize_requested_scopes, first["token"], first.get("subscriptions", []),
            )
        except asyncio.TimeoutError:
            await websocket.close(code=4401, reason="authentication_timeout")
            return
        except (WebSocketAuthError, ValueError, json.JSONDecodeError) as error:
            code = getattr(error, "code", "invalid_authentication")
            await websocket.close(code=4401, reason=str(code)[:80])
            return
        connection = WebSocketConnection(
            websocket=websocket,
            user_id=user.id,
            session_id=auth_session.id,
            role=user.role,
            token=first["token"],
            token_expires_at=expires_at,
            subscriptions=scopes,
        )
        if not await manager.register(connection):
            await websocket.close(code=4429, reason="connection_limit")
            return
        writer_task = asyncio.create_task(_writer(connection))
        await manager.enqueue(connection, {"type": "authenticated", "subscriptions": sorted(scopes)})
        for scope in denied:
            await manager.enqueue(connection, {"type": "subscription.denied", "scope": scope})

        while not connection.closed:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=REALTIME_IDLE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                await manager.enqueue(connection, {"_close_code": 4408})
                break
            try:
                message = _decode_client_message(raw)
            except (ValueError, json.JSONDecodeError):
                await manager.enqueue(connection, {"type": "error", "code": "invalid_message"})
                continue
            connection.last_message_at = monotonic()
            message_type = message.get("type")
            if message_type in {"ping", "pong"}:
                current_user, current_scopes, invalid = await asyncio.to_thread(
                    _validate_delivery, connection,
                )
                if invalid:
                    await manager.enqueue(connection, {
                        "_close_code": 4403 if invalid == "permissions_changed" else 4401,
                    })
                    break
                if current_user is None:
                    await manager.enqueue(connection, {"_close_code": 4401})
                    break
                connection.role = current_user.role
                connection.subscriptions = current_scopes
                if message_type == "ping":
                    await manager.enqueue(connection, {"type": "pong", "timestamp": message.get("timestamp")})
                continue
            if message_type in {"reauth", "auth"}:
                if not isinstance(message.get("token"), str):
                    await manager.enqueue(connection, {"_close_code": 4401})
                    break
                try:
                    auth_result = await asyncio.to_thread(
                        _authorize_requested_scopes,
                        message["token"],
                        sorted(connection.subscriptions),
                    )
                    new_user, new_session, new_expiry = auth_result[:3]
                    new_scopes = auth_result[3]
                except WebSocketAuthError:
                    await manager.enqueue(connection, {"_close_code": 4401})
                    break
                if new_user.id != connection.user_id or new_session.id != connection.session_id:
                    await manager.enqueue(connection, {"_close_code": 4401})
                    break
                if new_scopes != connection.subscriptions:
                    await manager.enqueue(connection, {"_close_code": 4403})
                    break
                connection.token = message["token"]
                connection.token_expires_at = new_expiry
                connection.role = new_user.role
                connection.subscriptions.intersection_update(new_scopes)
                await manager.enqueue(connection, {"type": "authenticated", "subscriptions": sorted(connection.subscriptions)})
                continue
            if message_type in {"subscribe", "unsubscribe"}:
                requested = message.get("scopes")
                if not isinstance(requested, list) or len(requested) > MAX_SUBSCRIPTIONS:
                    await manager.enqueue(connection, {"type": "error", "code": "invalid_subscriptions"})
                    continue
                if message_type == "subscribe":
                    try:
                        _user, _session, _expires, allowed, denied = await asyncio.to_thread(
                            _authorize_requested_scopes,
                            connection.token,
                            requested,
                        )
                    except WebSocketAuthError:
                        await manager.enqueue(connection, {"_close_code": 4401})
                        break
                    if len(connection.subscriptions | allowed) > MAX_SUBSCRIPTIONS:
                        await manager.enqueue(connection, {"type": "error", "code": "subscription_limit"})
                        continue
                    connection.subscriptions.update(allowed)
                    for scope in denied:
                        await manager.enqueue(connection, {"type": "subscription.denied", "scope": scope})
                else:
                    connection.subscriptions.difference_update(scope for scope in requested if isinstance(scope, str))
                await manager.enqueue(connection, {"type": "subscriptions", "scopes": sorted(connection.subscriptions)})
                continue
            await manager.enqueue(connection, {"type": "error", "code": "unsupported_message"})
    except WebSocketDisconnect:
        pass
    except Exception as error:
        logger.info("Realtime websocket closed (%s)", type(error).__name__)
    finally:
        if connection is not None:
            await manager.unregister(connection)
        if writer_task is not None:
            writer_task.cancel()
            try:
                await writer_task
            except (asyncio.CancelledError, Exception):
                pass
