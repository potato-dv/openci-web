import asyncio
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.investigation import Investigation
from app.models.planning import PlanningRun
from app.models.realtime_outbox import RealtimeOutboxEvent
from app.models.report import InvestigationReport
from app.models.user import User
from app.models.user_permission_override import UserPermissionOverride
from app.realtime.websocket import (
    ConnectionManager,
    WebSocketConnection,
    _client_event,
    _event_matches_scopes,
    run_redis_listener,
    scope_is_authorized,
)


class RealtimeOutboxTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.tables = [
            User.__table__,
            Investigation.__table__,
            InvestigationReport.__table__,
            PlanningRun.__table__,
            RealtimeOutboxEvent.__table__,
            UserPermissionOverride.__table__,
        ]
        Base.metadata.create_all(self.engine, tables=self.tables)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.sessions()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine, tables=list(reversed(self.tables)))
        self.engine.dispose()

    def make_agent_case_report(self):
        agent = User(name="Agent", email="agent@example.test", password="hash", role="agent")
        self.db.add(agent)
        self.db.flush()
        case = Investigation(
            reference_number="INV-REALTIME-1",
            legacy_subject_name="Test subject",
            assigned_agent_id=agent.id,
            status="assigned",
        )
        self.db.add(case)
        self.db.flush()
        report = InvestigationReport(
            investigation_id=case.id,
            author_id=agent.id,
            version=1,
            content="Private report body",
            status="draft",
        )
        self.db.add(report)
        self.db.commit()
        return agent, case, report

    def test_report_submission_is_written_to_outbox_in_same_commit(self):
        agent, _case, report = self.make_agent_case_report()
        self.db.query(RealtimeOutboxEvent).delete(synchronize_session=False)
        self.db.commit()

        report.status = "submitted"
        self.db.commit()

        event = self.db.query(RealtimeOutboxEvent).filter(
            RealtimeOutboxEvent.event_type == "report.submitted",
            RealtimeOutboxEvent.entity_id == str(report.id),
        ).one()
        self.assertEqual(event.investigation_id, report.investigation_id)
        self.assertEqual(event.recipient_user_ids, [agent.id])
        self.assertEqual(event.recipient_roles, ["admin", "supervisor"])
        self.assertFalse(hasattr(event, "content"))

    def test_rollback_removes_both_mutation_and_notification(self):
        _agent, _case, report = self.make_agent_case_report()
        self.db.query(RealtimeOutboxEvent).filter(
            RealtimeOutboxEvent.event_type == "report.submitted",
        ).delete(synchronize_session=False)
        report.status = "submitted"
        self.db.flush()
        self.db.rollback()

        persisted = self.db.get(InvestigationReport, report.id)
        self.assertEqual(persisted.status, "draft")
        self.assertEqual(
            self.db.query(RealtimeOutboxEvent).filter(
                RealtimeOutboxEvent.event_type == "report.submitted",
            ).count(),
            0,
        )

    def test_agent_scope_uses_current_assignment_and_history_permission(self):
        agent, case, _report = self.make_agent_case_report()
        self.assertTrue(scope_is_authorized(self.db, agent, f"investigation:{case.id}"))
        case.status = "completed"
        self.db.commit()
        self.assertFalse(scope_is_authorized(self.db, agent, f"investigation:{case.id}"))

    def test_role_scope_is_checked_against_database_role(self):
        agent, _case, _report = self.make_agent_case_report()
        self.assertTrue(scope_is_authorized(self.db, agent, "role:agent"))
        self.assertFalse(scope_is_authorized(self.db, agent, "role:supervisor"))

    def test_unassigned_agent_gets_route_invalidation_without_case_id(self):
        agent, case, _report = self.make_agent_case_report()
        self.db.query(RealtimeOutboxEvent).delete(synchronize_session=False)
        self.db.commit()

        case.assigned_agent_id = None
        self.db.commit()

        event = next(
            row for row in self.db.query(RealtimeOutboxEvent).filter(
                RealtimeOutboxEvent.event_type == "route.agent_updated",
            )
            if row.recipient_user_ids == [agent.id] and row.investigation_id is None
        )
        self.assertIsNone(event.investigation_id)
        self.assertEqual(event.entity_id, str(agent.id))

    def test_investigation_detail_changes_create_outbox_events(self):
        _agent, case, _report = self.make_agent_case_report()
        self.db.query(RealtimeOutboxEvent).delete(synchronize_session=False)
        self.db.commit()

        case.legacy_subject_name = "Updated subject"
        case.postal_code = "1000"
        self.db.commit()

        types = {
            row.event_type
            for row in self.db.query(RealtimeOutboxEvent).filter(
                RealtimeOutboxEvent.investigation_id == case.id,
            )
        }
        self.assertIn("investigation.updated", types)
        self.assertIn("investigation.location_updated", types)

    def test_reassignment_notifies_new_agent_and_manager_audience(self):
        _old_agent, case, _report = self.make_agent_case_report()
        new_agent = User(name="New Agent", email="new-agent@example.test", password="hash", role="agent")
        self.db.add(new_agent)
        self.db.flush()
        case.assigned_agent_id = new_agent.id
        self.db.query(RealtimeOutboxEvent).delete(synchronize_session=False)
        self.db.commit()

        assigned = self.db.query(RealtimeOutboxEvent).filter(
            RealtimeOutboxEvent.event_type == "investigation.assigned",
            RealtimeOutboxEvent.investigation_id == case.id,
        ).one()
        self.assertEqual(assigned.recipient_user_ids, [new_agent.id])
        self.assertEqual(assigned.recipient_roles, ["admin", "supervisor"])

    def test_route_publication_targets_agents_in_same_transaction(self):
        agent, case, _report = self.make_agent_case_report()
        run = PlanningRun(
            requested_by_id=agent.id,
            work_date=date(2026, 11, 9),
            region_code="13",
            investigation_ids=[case.id],
            agent_ids=[agent.id],
            status="ready",
        )
        self.db.add(run)
        self.db.commit()
        self.db.query(RealtimeOutboxEvent).filter(
            RealtimeOutboxEvent.event_type == "route.updated",
        ).delete(synchronize_session=False)
        self.db.commit()

        run.status = "applied"
        self.db.commit()

        event = self.db.query(RealtimeOutboxEvent).filter(
            RealtimeOutboxEvent.event_type == "route.published",
            RealtimeOutboxEvent.entity_id == str(run.id),
        ).one()
        self.assertEqual(event.recipient_user_ids, [agent.id])
        self.assertEqual(event.recipient_roles, ["admin", "supervisor"])

    def test_large_resource_ids_are_rejected_before_database_query(self):
        agent, _case, _report = self.make_agent_case_report()
        self.assertFalse(scope_is_authorized(self.db, agent, f"investigation:{'9' * 50}"))

    def test_client_frame_contains_only_notification_metadata(self):
        frame = _client_event({
            "event_id": "event-1",
            "event_type": "report.submitted",
            "entity_type": "investigation_report",
            "entity_id": "42",
            "investigation_id": 7,
            "recipient_user_ids": [9],
            "recipient_roles": ["supervisor"],
            "content": "Private report body",
            "occurred_at": "2026-11-09T08:00:00+00:00",
        })
        self.assertEqual(frame["entity_id"], 42)
        self.assertEqual(frame["name"], "report.submitted")
        self.assertNotIn("content", frame)
        self.assertNotIn("recipient_user_ids", frame)
        self.assertNotIn("recipient_roles", frame)

    def test_schedule_frame_identifies_only_the_affected_agent(self):
        frame = _client_event({
            "event_id": "schedule-event",
            "event_type": "schedule.updated",
            "entity_type": "agent_schedule",
            "entity_id": "8",
            "investigation_id": None,
            "recipient_user_ids": [17],
            "recipient_roles": ["supervisor"],
            "occurred_at": "2026-11-09T08:00:00+00:00",
        })
        self.assertEqual(frame["affected_agent_id"], 17)
        self.assertNotIn("recipient_user_ids", frame)


class RealtimeDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def connection(self, user_id: int, role: str, scopes: set[str]) -> WebSocketConnection:
        return WebSocketConnection(
            websocket=SimpleNamespace(),  # The manager queues frames; it does not write in these unit tests.
            user_id=user_id,
            session_id=uuid4(),
            role=role,
            token="test-token",
            token_expires_at=datetime.now(timezone.utc),
            subscriptions=scopes,
        )

    def envelope(self, **overrides):
        return {
            "event_id": "test-event",
            "event_type": "report.submitted",
            "entity_type": "investigation_report",
            "entity_id": "19",
            "investigation_id": 7,
            "recipient_user_ids": [41],
            "recipient_roles": ["supervisor"],
            "occurred_at": "2026-11-09T08:00:00+00:00",
            **overrides,
        }

    async def test_report_event_reaches_authorized_supervisor(self):
        manager = ConnectionManager()
        supervisor = self.connection(52, "supervisor", {"reports.queue"})
        await manager.register(supervisor)
        with patch("app.realtime.websocket._validate_delivery", return_value=(SimpleNamespace(id=52, role="supervisor"), {"reports.queue"}, None)):
            await manager.publish(self.envelope())
        self.assertEqual(supervisor.outbound.get_nowait()["name"], "report.submitted")

    async def test_unauthorized_client_receives_no_protected_event(self):
        manager = ConnectionManager()
        agent = self.connection(99, "agent", {"reports.queue"})
        await manager.register(agent)
        with patch("app.realtime.websocket._validate_delivery", return_value=(SimpleNamespace(id=99, role="agent"), {"reports.queue"}, None)):
            await manager.publish(self.envelope())
        self.assertTrue(agent.outbound.empty())

    async def test_agent_losing_case_access_gets_no_case_event(self):
        manager = ConnectionManager()
        agent = self.connection(41, "agent", {"investigation:7"})
        await manager.register(agent)
        with (
            patch("app.realtime.websocket._validate_delivery", return_value=(SimpleNamespace(id=41, role="agent"), {"investigation:7"}, None)),
            patch("app.realtime.websocket._agent_still_owns_investigation", return_value=False),
        ):
            await manager.publish(self.envelope(event_type="investigation.status_changed", recipient_roles=["admin", "supervisor"]))
        self.assertTrue(agent.outbound.empty())

    async def test_session_and_permission_changes_close_connection_before_delivery(self):
        manager = ConnectionManager()
        expired = self.connection(41, "agent", {"investigations"})
        await manager.register(expired)
        with patch("app.realtime.websocket._validate_delivery", return_value=(None, set(), "session_expired")):
            await manager.publish(self.envelope(event_type="investigation.updated", recipient_user_ids=[41], recipient_roles=[]))
        self.assertEqual(expired.outbound.get_nowait()["_close_code"], 4401)

        changed = self.connection(42, "agent", {"investigations"})
        await manager.register(changed)
        with patch("app.realtime.websocket._validate_delivery", return_value=(SimpleNamespace(id=42, role="agent"), set(), "permissions_changed")):
            await manager.publish(self.envelope(event_type="investigation.updated", recipient_user_ids=[42], recipient_roles=[]))
        self.assertEqual(changed.outbound.get_nowait()["_close_code"], 4403)

    async def test_separate_worker_managers_deliver_same_redis_event_once(self):
        first_worker = ConnectionManager()
        second_worker = ConnectionManager()
        first = self.connection(52, "supervisor", {"reports.queue"})
        second = self.connection(53, "supervisor", {"reports.queue"})
        await first_worker.register(first)
        await second_worker.register(second)
        with patch("app.realtime.websocket._validate_delivery", side_effect=lambda connection: (SimpleNamespace(id=connection.user_id, role="supervisor"), {"reports.queue"}, None)):
            event = self.envelope()
            await first_worker.publish(event)
            await second_worker.publish(event)
        self.assertEqual(first.outbound.get_nowait()["event_id"], "test-event")
        self.assertEqual(second.outbound.get_nowait()["event_id"], "test-event")

    async def test_role_subscription_still_requires_role_recipient(self):
        self.assertTrue(_event_matches_scopes({"role:supervisor"}, self.envelope(), "supervisor"))
        self.assertFalse(_event_matches_scopes({"role:agent"}, self.envelope(), "agent"))

    async def test_identity_scope_receives_only_events_targeted_to_that_user(self):
        event = self.envelope()
        self.assertFalse(_event_matches_scopes({"me"}, event, "supervisor", 52))
        event["recipient_user_ids"] = [52]
        self.assertTrue(_event_matches_scopes({"me"}, event, "supervisor", 52))

    async def test_redis_listener_resubscribes_after_disconnect_and_resyncs(self):
        stop = asyncio.Event()

        class FakePubSub:
            def __init__(self, attempt):
                self.attempt = attempt

            async def subscribe(self, _channel):
                if self.attempt == 1:
                    raise ConnectionError("redis restarted")
                stop.set()

            async def get_message(self, **_kwargs):
                return None

            async def aclose(self):
                return None

        class FakeRedis:
            attempts = 0

            def pubsub(self, **_kwargs):
                self.attempts += 1
                return FakePubSub(self.attempts)

        async def skip_backoff(awaitable, timeout):
            awaitable.close()

        with (
            patch("app.realtime.websocket.manager.request_resync", new_callable=AsyncMock) as resync,
            patch("app.realtime.websocket.asyncio.wait_for", side_effect=skip_backoff),
        ):
            redis = FakeRedis()
            await run_redis_listener(redis, stop)

        self.assertEqual(redis.attempts, 2)
        resync.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
