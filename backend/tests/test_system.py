import unittest
from types import SimpleNamespace

from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, configure_mappers

from app.database import Base
from app.models.investigation import Investigation
from app.models.activity import ActivityLog
from app.schemas.activity import ActivityLogResponse
from app.schemas.assignment import AssignmentResponse
from app.schemas.investigation import InvestigationResponse
from app.schemas.investigation import InvestigationCreate
from app.services.investigation import (
    can_access_investigation,
    create_investigation,
    get_report,
    get_report_versions,
    is_valid_status_transition,
    review_investigation_report,
    save_report_draft,
    submit_report,
)
from app.schemas.report import ReportResponse, ReportUpsert
from app.services.locations import catalog, get_barangays, get_cities, get_provinces
from app.utils.auth import require_roles
from fastapi import HTTPException


class LocationTests(unittest.TestCase):
    def test_local_snapshot_is_complete_and_ncr_has_no_province(self):
        data = catalog()
        self.assertEqual(len(data["regions"]), 18)
        self.assertEqual(len(data["provinces"]), 82)
        self.assertEqual(len(data["barangays"]), 42_010)

        ncr = next(item for item in data["regions"] if item["code"] == "1300000000")
        self.assertEqual(get_provinces(ncr["code"]), [])
        self.assertGreater(len(get_cities(ncr["code"], None)), 0)

    def test_address_schema_rejects_cross_city_barangay(self):
        manila_code = "1380600000"
        manila_barangay = get_barangays(manila_code)[0]["code"]
        qc_code = "1381400000"
        qc_barangay = get_barangays(qc_code)[0]["code"]
        city = next(item for item in catalog()["cities"] if item["code"] == manila_code)

        common = {
            "subject_name": "Test Subject",
            "house_number": "10",
            "street": "Test Street",
            "region_code": city["region_code"],
            "province_code": None,
            "city_municipality_code": manila_code,
            "barangay_code": manila_barangay,
        }
        InvestigationCreate(**common)
        with self.assertRaises(ValidationError):
            InvestigationCreate(**{**common, "barangay_code": qc_barangay})

    def test_location_api_rejects_a_province_from_another_region(self):
        province = next(item for item in catalog()["provinces"] if item["name"] == "Cebu")
        with self.assertRaises(HTTPException):
            get_cities("1300000000", province["code"])


class WorkflowTests(unittest.TestCase):
    def test_report_versions_preserve_returned_submissions_and_reviews(self):
        from datetime import datetime, timezone

        from app.models.review import InvestigationReview
        from app.models.user import User

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            agent = User(name="Field Agent", email="agent@example.test", password="hashed", role="agent")
            supervisor = User(name="Supervisor", email="supervisor@example.test", password="hashed", role="supervisor")
            session.add_all([agent, supervisor])
            session.flush()
            investigation = Investigation(
                reference_number="INV-REPORT-VERSIONS",
                subject_name="Test Subject",
                status="assigned",
                assigned_agent_id=agent.id,
            )
            session.add(investigation)
            session.flush()

            first_input = ReportUpsert(
                content="Initial field findings",
                visit_outcome="visited",
                outcome="verified",
                verified_address="10 Test Street",
                visited_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
            )
            first = save_report_draft(session, investigation, agent, first_input)
            self.assertEqual(first.version, 1)
            self.assertEqual(first.author_name, "Field Agent")
            self.assertEqual(ReportResponse.model_validate(first).author_name, "Field Agent")
            submitted = submit_report(session, investigation)
            self.assertEqual(submitted.status, "submitted")

            review = review_investigation_report(
                session,
                investigation,
                supervisor,
                "returned_for_correction",
                "Please clarify the verified address.",
            )
            self.assertEqual(first.status, "returned_for_correction")
            self.assertEqual(review.report_id, first.id)

            second = save_report_draft(
                session,
                investigation,
                agent,
                ReportUpsert(
                    content="Corrected field findings",
                    visit_outcome="visited",
                    outcome="verified",
                    verified_address="10 Test Street, Barangay North",
                    visited_at=first_input.visited_at,
                ),
            )
            self.assertEqual(second.version, 2)
            self.assertEqual(second.status, "draft")
            self.assertEqual(first.content, "Initial field findings")
            self.assertEqual(first.status, "returned_for_correction")

            submit_report(session, investigation)
            approval = review_investigation_report(session, investigation, supervisor, "approved", None)
            session.flush()
            self.assertEqual(second.status, "approved")
            self.assertEqual(investigation.status, "completed")
            self.assertEqual(approval.report_id, second.id)
            self.assertEqual(session.query(InvestigationReview).count(), 2)
            self.assertEqual([item.version for item in get_report_versions(session, investigation.id)], [2, 1])
            self.assertEqual(get_report(session, investigation.id).id, second.id)

    def test_report_submission_requires_outcomes_and_conditional_visit_data(self):
        from datetime import datetime, timezone

        from app.models.user import User

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            agent = User(name="Field Agent", email="agent@example.test", password="hashed", role="agent")
            session.add(agent)
            session.flush()
            investigation = Investigation(
                reference_number="INV-REPORT-VALIDATION",
                subject_name="Test Subject",
                status="assigned",
                assigned_agent_id=agent.id,
            )
            session.add(investigation)
            session.flush()

            incomplete = save_report_draft(session, investigation, agent, ReportUpsert(content="Findings"))
            with self.assertRaisesRegex(ValueError, "visit outcome"):
                submit_report(session, investigation)

            incomplete.visit_outcome = "visited"
            incomplete.outcome = "verified"
            with self.assertRaisesRegex(ValueError, "date and time"):
                submit_report(session, investigation)

            incomplete.visited_at = datetime.now(timezone.utc)
            with self.assertRaisesRegex(ValueError, "Verified address"):
                submit_report(session, investigation)

            incomplete.verified_address = "10 Test Street"
            self.assertEqual(submit_report(session, investigation).status, "submitted")

    def test_report_schema_rejects_unknown_enumerated_values(self):
        with self.assertRaises(ValidationError):
            ReportUpsert(content="Findings", visit_outcome="not visited")

    def test_legacy_returned_investigation_starts_a_new_report_revision(self):
        from app.models.user import User

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            agent = User(name="Field Agent", email="agent@example.test", password="hashed", role="agent")
            session.add(agent)
            session.flush()
            investigation = Investigation(
                reference_number="INV-LEGACY-RETURN",
                subject_name="Test Subject",
                status="assigned",
                assigned_agent_id=agent.id,
            )
            session.add(investigation)
            session.flush()
            legacy_draft = save_report_draft(
                session,
                investigation,
                agent,
                ReportUpsert(content="Original draft"),
            )

            # Before versioning, returned reports were reset to draft in place.
            investigation.status = "returned_for_correction"
            session.commit()
            corrected = save_report_draft(
                session,
                investigation,
                agent,
                ReportUpsert(content="Corrected draft"),
            )

            self.assertEqual(corrected.version, 2)
            self.assertEqual(legacy_draft.version, 1)
            self.assertEqual(legacy_draft.content, "Original draft")

    def test_investigation_reference_is_generated_and_unique(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        from app.services.locations import catalog, get_barangays

        city_code = "1381400000"
        region_code = next(city["region_code"] for city in catalog()["cities"] if city["code"] == city_code)
        payload = InvestigationCreate(
            subject_name="Test Subject",
            house_number="10",
            street="Test Street",
            region_code=region_code,
            province_code=None,
            city_municipality_code=city_code,
            barangay_code=get_barangays(city_code)[0]["code"],
        )
        with Session(engine) as session:
            first = create_investigation(session, payload)
            second = create_investigation(session, payload)
            self.assertRegex(first.reference_number, r"^INV-[0-9A-F]{32}$")
            self.assertNotEqual(first.reference_number, second.reference_number)

    def test_admin_and_supervisor_scope_and_agent_assignment_scope(self):
        investigation = SimpleNamespace(assigned_agent_id=7)
        self.assertTrue(can_access_investigation(investigation, SimpleNamespace(role="admin", id=3)))
        self.assertTrue(can_access_investigation(investigation, SimpleNamespace(role="supervisor", id=4)))
        self.assertTrue(can_access_investigation(investigation, SimpleNamespace(role="agent", id=7)))
        self.assertFalse(can_access_investigation(investigation, SimpleNamespace(role="agent", id=8)))

    def test_workflow_status_moves_only_through_defined_edges(self):
        self.assertTrue(is_valid_status_transition("pending", "assigned"))
        self.assertFalse(is_valid_status_transition("pending", "under_review"))
        self.assertFalse(is_valid_status_transition("completed", "in_progress"))

    def test_admin_dependency_rejects_other_roles(self):
        admin = SimpleNamespace(role="admin", id=1)
        supervisor = SimpleNamespace(role="supervisor", id=2)
        self.assertIs(require_roles("admin")(admin), admin)
        with self.assertRaises(HTTPException):
            require_roles("admin")(supervisor)

    def test_relationships_and_archive_preserve_assignment_history(self):
        configure_mappers()
        engine = create_engine("sqlite:///:memory:")

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(engine)
        with Session(engine) as session:
            from app.models.assignment import InvestigationAssignment
            from app.models.user import User

            actor = User(name="Admin", email="admin@example.test", password="hashed", role="admin")
            agent = User(name="Agent", email="agent@example.test", password="hashed", role="agent")
            session.add_all([actor, agent])
            session.flush()
            investigation = Investigation(reference_number="INV-CASCADE", subject_name="Subject", assigned_agent_id=agent.id)
            assignment = InvestigationAssignment(agent_id=agent.id, assigned_by_id=actor.id, is_active=True)
            investigation.assignments.append(assignment)
            session.add(investigation)
            activity = ActivityLog(actor_id=actor.id, action="test", object_type="investigation", object_id=1)
            session.add(activity)
            session.commit()
            investigation_id = investigation.id

            self.assertEqual(InvestigationResponse.model_validate(investigation).assigned_agent_name, agent.name)
            assignment_response = AssignmentResponse.model_validate(assignment)
            self.assertEqual(assignment_response.agent_name, agent.name)
            self.assertEqual(assignment_response.assigned_by_name, actor.name)
            self.assertEqual(ActivityLogResponse.model_validate(activity).actor_name, actor.name)

            session.delete(investigation)
            session.rollback()
            from app.services.investigation import delete_investigation, get_investigations

            investigation = session.get(Investigation, investigation_id)
            delete_investigation(session, investigation)
            self.assertEqual(get_investigations(session, actor), [])
            self.assertIsNotNone(session.get(Investigation, investigation_id))
            self.assertEqual(session.query(InvestigationAssignment).count(), 1)


if __name__ == "__main__":
    unittest.main()
