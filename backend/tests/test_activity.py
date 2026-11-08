import unittest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import ActivityLog, Investigation, User
from app.routes.activity import activity_log_filter_options, query_activity_logs


class ActivityLogQueryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.admin = User(
            name="Morgan Santos",
            email="morgan@example.test",
            password="hashed",
            role="admin",
        )
        self.agent = User(
            name="Daniel Cruz",
            email="daniel@example.test",
            password="hashed",
            role="agent",
        )
        self.session.add_all([self.admin, self.agent])
        self.session.flush()
        self.investigation = Investigation(
            reference_number="INV-2026-00900",
            first_name="Test",
            last_name="Subject",
            status="pending",
            priority="normal",
            service_duration_seconds=2700,
        )
        self.session.add(self.investigation)
        self.session.flush()

        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rows = []
        for index in range(260):
            rows.append(
                ActivityLog(
                    actor_id=self.admin.id if index % 3 else None,
                    action="investigation.updated" if index % 2 else "user.created",
                    object_type="investigation" if index % 2 else "user",
                    object_id=index + 1,
                    details=(
                        {"fields": ["priority"]}
                        if index % 2
                        else {"role": "agent"}
                    ),
                    created_at=start + timedelta(minutes=index),
                )
            )
        rows.append(
            ActivityLog(
                actor_id=self.admin.id,
                action="investigation.assigned",
                object_type="investigation",
                object_id=self.investigation.id,
                details={"agent_id": self.agent.id, "notes": "private note"},
                created_at=start + timedelta(days=2),
            )
        )
        self.session.add_all(rows)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def query(self, **overrides):
        values = {
            "response": Response(),
            "q": "",
            "action": None,
            "actor_id": None,
            "actor_type": None,
            "object_type": None,
            "object_id": None,
            "created_from": None,
            "created_to": None,
            "sort": "created_at",
            "direction": "desc",
            "page": 1,
            "page_size": 25,
            "db": self.session,
            "_": self.admin,
        }
        values.update(overrides)
        return query_activity_logs(**values)

    def test_pagination_counts_and_reaches_records_after_250(self):
        result = self.query(page=11, page_size=25)

        self.assertEqual(result.total, 261)
        self.assertEqual(result.page, 11)
        self.assertEqual(result.page_size, 25)
        self.assertEqual(len(result.items), 11)
        self.assertEqual(result.items[0].id, 11)

    def test_search_filters_and_summary_use_stored_values(self):
        result = self.query(q="private note")

        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0].summary, "Investigation assigned to Daniel Cruz")
        self.assertIn("Investigation ID: 1", result.items[0].record_label)
        self.assertIn("INV-2026-00900", result.items[0].record_label)
        user_result = self.query(object_type="user", object_id=self.admin.id)
        self.assertIn("Morgan Santos (User ID: 1)", user_result.items[0].record_label)
        details = {field.key: field for field in result.items[0].detail_fields}
        self.assertEqual(details["agent_id"].value, "Daniel Cruz")
        self.assertTrue(details["notes"].redacted)
        self.assertEqual(details["notes"].value, "Value hidden")

    def test_exact_filters_and_date_range_are_combined_server_side(self):
        result = self.query(
            action="investigation.updated",
            object_type="investigation",
            actor_id=self.admin.id,
            created_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
            created_to=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )

        self.assertGreater(result.total, 0)
        self.assertTrue(all(item.action == "investigation.updated" for item in result.items))
        self.assertTrue(all(item.object_type == "investigation" for item in result.items))

    def test_system_actor_filter_and_filter_options(self):
        result = self.query(actor_type="system", page_size=100)
        self.assertGreater(result.total, 0)
        self.assertTrue(all(item.actor_id is None for item in result.items))

        options = activity_log_filter_options(Response(), self.session, self.admin)
        self.assertIn("investigation.updated", options.actions)
        self.assertIn("investigation", options.object_types)
        self.assertTrue(any(actor.id is None for actor in options.actors))
        self.assertTrue(any(actor.id == self.agent.id for actor in options.actors))

    def test_invalid_date_range_is_rejected(self):
        with self.assertRaises(HTTPException):
            self.query(
                created_from=datetime(2026, 1, 2, tzinfo=timezone.utc),
                created_to=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
