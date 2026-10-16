import unittest
from types import SimpleNamespace

from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers

from app.database import Base
from app.models.investigation import Investigation
from app.models.activity import ActivityLog
from app.models.review import InvestigationReview
from app.models.report import InvestigationReport
from app.schemas.activity import ActivityLogResponse
from app.schemas.assignment import AssignmentResponse
from app.schemas.investigation import InvestigationCreate, InvestigationResponse, InvestigationUpdate
from app.services.investigation import (
    can_access_investigation,
    assign_investigation,
    create_investigation,
    get_report,
    get_report_versions,
    is_valid_status_transition,
    review_investigation_report,
    save_report_draft,
    submit_report,
    update_investigation,
)
from app.schemas.report import ReportResponse, ReportUpsert
from app.services.locations import catalog, get_barangays, get_cities, get_provinces
from app.utils.auth import require_roles
from fastapi import HTTPException


class InvestigationNameTests(unittest.TestCase):
    def address_fields(self):
        from app.services.locations import catalog, get_barangays

        city_code = "1381400000"
        city = next(item for item in catalog()["cities"] if item["code"] == city_code)
        return {
            "house_number": "10",
            "street": "Test Street",
            "region_code": city["region_code"],
            "province_code": None,
            "city_municipality_code": city_code,
            "barangay_code": get_barangays(city_code)[0]["code"],
        }

    def test_create_schema_trims_names_and_validates_required_and_combined_length(self):
        values = {
            **self.address_fields(),
            "first_name": "  Ada ",
            "middle_name": "  Augusta  ",
            "last_name": " Lovelace  ",
        }
        payload = InvestigationCreate(**values)
        self.assertEqual(payload.first_name, "Ada")
        self.assertEqual(payload.middle_name, "Augusta")
        self.assertEqual(payload.last_name, "Lovelace")
        optional_middle = InvestigationCreate(**{**values, "middle_name": "   "})
        self.assertIsNone(optional_middle.middle_name)

        with self.assertRaises(ValidationError):
            InvestigationCreate(**{**values, "first_name": "   "})
        with self.assertRaises(ValidationError):
            InvestigationCreate(**{key: value for key, value in values.items() if key != "last_name"})
        with self.assertRaises(ValidationError):
            InvestigationCreate(**{**values, "first_name": "A" * 128, "middle_name": None, "last_name": "B" * 127})
        with self.assertRaises(ValidationError):
            InvestigationCreate(**{**values, "subject_name": "Ada Augusta Lovelace"})

        formatted = InvestigationCreate(**{
            **values,
            "first_name": "  aDA ",
            "middle_name": " mARIE  ",
            "last_name": " lOVELACE  ",
        })
        self.assertEqual(formatted.first_name, "Ada")
        self.assertEqual(formatted.middle_name, "Marie")
        self.assertEqual(formatted.last_name, "Lovelace")

    def test_create_and_update_normalize_freeform_address_fields(self):
        create_payload = InvestigationCreate(**{
            **self.address_fields(),
            "first_name": "Ada",
            "last_name": "Lovelace",
            "house_number": "  bLDG   12a ",
            "unit_floor_building_name": "  tOWER   WEST ",
            "street": "  mAIN   STREET ",
            "subdivision_village_purok": "  sAN   ISIDRO ",
        })
        self.assertEqual(create_payload.house_number, "Bldg 12a")
        self.assertEqual(create_payload.unit_floor_building_name, "Tower West")
        self.assertEqual(create_payload.street, "Main Street")
        self.assertEqual(create_payload.subdivision_village_purok, "San Isidro")

        update_payload = InvestigationUpdate(
            house_number="  uNIT   4 ",
            street="  hIGH   STREET ",
        )
        self.assertEqual(update_payload.house_number, "Unit 4")
        self.assertEqual(update_payload.street, "High Street")

        updated_name = InvestigationUpdate(
            first_name=" jANE ",
            middle_name=" DOE ",
            last_name=" SMITH ",
        )
        self.assertEqual((updated_name.first_name, updated_name.middle_name, updated_name.last_name), ("Jane", "Doe", "Smith"))

    def test_create_response_and_legacy_correction_use_structured_names(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            legacy = Investigation(
                reference_number="INV-LEGACY-NAME",
                legacy_subject_name="Two Words",
            )
            session.add(legacy)
            session.flush()

            legacy_response = InvestigationResponse.model_validate(legacy)
            self.assertEqual(legacy_response.subject_name, "Two Words")
            self.assertIsNone(legacy_response.first_name)
            self.assertIsNone(legacy_response.last_name)

            corrected = update_investigation(
                session,
                legacy,
                InvestigationUpdate(first_name="  Ada ", middle_name=" ", last_name=" Lovelace "),
            )
            response = InvestigationResponse.model_validate(corrected)
            self.assertEqual(response.first_name, "Ada")
            self.assertIsNone(response.middle_name)
            self.assertEqual(response.last_name, "Lovelace")
            self.assertEqual(response.subject_name, "Ada Lovelace")
            self.assertIsNone(corrected.legacy_subject_name)

    def test_update_requires_all_name_parts_and_rejects_legacy_subject_name(self):
        with self.assertRaises(ValidationError):
            InvestigationUpdate(first_name="Ada", last_name="Lovelace")
        with self.assertRaises(ValidationError):
            InvestigationUpdate(subject_name="Ada Lovelace")
        with self.assertRaises(ValidationError):
            InvestigationUpdate(first_name=" ", middle_name=None, last_name="Lovelace")
        with self.assertRaises(ValidationError):
            InvestigationUpdate(first_name="A" * 128, middle_name=None, last_name="B" * 127)

    def test_database_rejects_incomplete_non_legacy_name_parts(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(
                Investigation(
                    reference_number="INV-INCOMPLETE-NAME",
                    first_name=" ",
                    middle_name=None,
                    last_name="Lovelace",
                )
            )
            with self.assertRaises(IntegrityError):
                session.commit()


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
            "first_name": "Test",
            "last_name": "Subject",
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
    def test_investigation_delete_permissions_distinguish_soft_restore_and_permanent_delete(self):
        from app.controllers.investigation import permanently_delete, restore

        supervisor = SimpleNamespace(role="supervisor", id=2)
        agent = SimpleNamespace(role="agent", id=3)
        self.assertIs(require_roles("admin", "supervisor")(supervisor), supervisor)
        with self.assertRaises(HTTPException):
            require_roles("admin")(supervisor)
        with self.assertRaises(HTTPException) as permanent_error:
            permanently_delete(None, 7, supervisor)
        self.assertEqual(permanent_error.exception.status_code, 403)
        with self.assertRaises(HTTPException) as restore_error:
            restore(None, 7, agent)
        self.assertEqual(restore_error.exception.status_code, 403)

    def test_review_decision_column_fits_longest_decision(self):
        decision_column = InvestigationReview.__table__.columns["decision"]
        self.assertGreaterEqual(decision_column.type.length, len("returned_for_correction"))

    def test_report_versions_are_unique_per_investigation_not_per_investigation_only(self):
        from sqlalchemy import UniqueConstraint

        unique_columns = {
            tuple(constraint.columns.keys())
            for constraint in InvestigationReport.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        self.assertIn(("investigation_id", "version"), unique_columns)
        self.assertNotIn(("investigation_id",), unique_columns)

    def test_celery_task_uses_workflow_status_and_rejects_invalid_transition(self):
        from datetime import datetime, timezone
        from unittest.mock import patch

        from sqlalchemy.orm import sessionmaker

        from app.workers.tasks import process_investigation

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        with session_factory() as session:
            assigned = Investigation(
                reference_number="INV-CELERY-ASSIGNED",
                first_name="QA",
                last_name="Agent",
                status="assigned",
            )
            pending = Investigation(
                reference_number="INV-CELERY-PENDING",
                first_name="QA",
                last_name="Pending",
                status="pending",
            )
            trashed = Investigation(
                reference_number="INV-CELERY-TRASHED",
                first_name="QA",
                last_name="Trashed",
                status="assigned",
                deleted_at=datetime.now(timezone.utc),
            )
            session.add_all([assigned, pending, trashed])
            session.flush()
            assigned_id = assigned.id
            pending_id = pending.id
            trashed_id = trashed.id
            session.commit()

        with patch("app.workers.tasks.SessionLocal", session_factory):
            result = process_investigation.run(assigned_id)
            rejected = process_investigation.run(pending_id)
            skipped = process_investigation.run(trashed_id)

        self.assertEqual(result["status"], "in_progress")
        self.assertEqual(rejected["status"], "failed")
        self.assertEqual(skipped["status"], "skipped")
        with session_factory() as session:
            self.assertEqual(session.get(Investigation, assigned_id).status, "in_progress")
            self.assertEqual(session.get(Investigation, pending_id).status, "pending")
            self.assertEqual(session.get(Investigation, trashed_id).status, "assigned")
        engine.dispose()

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
                first_name="Test",
                last_name="Subject",
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
                first_name="Test",
                last_name="Subject",
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
                first_name="Test",
                last_name="Subject",
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
            first_name="Test",
            middle_name="Case",
            last_name="Subject",
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
            response = InvestigationResponse.model_validate(first)
            self.assertEqual(response.subject_name, "Test Case Subject")
            self.assertEqual(response.first_name, "Test")
            self.assertEqual(response.middle_name, "Case")
            self.assertEqual(response.last_name, "Subject")

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

    def test_assignment_service_rejects_non_assignable_statuses(self):
        for status in ("in_progress", "under_review", "returned_for_correction", "completed"):
            with self.subTest(status=status):
                with self.assertRaisesRegex(ValueError, "Only pending or assigned"):
                    assign_investigation(
                        None,
                        SimpleNamespace(status=status),
                        None,
                        None,
                        None,
                    )

    def test_admin_dependency_rejects_other_roles(self):
        admin = SimpleNamespace(role="admin", id=1)
        supervisor = SimpleNamespace(role="supervisor", id=2)
        self.assertIs(require_roles("admin")(admin), admin)
        with self.assertRaises(HTTPException):
            require_roles("admin")(supervisor)

    def test_soft_delete_preserves_relationships_and_permanent_delete_preserves_audit(self):
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
            investigation = Investigation(reference_number="INV-CASCADE", first_name="Test", last_name="Subject", assigned_agent_id=agent.id)
            assignment = InvestigationAssignment(agent_id=agent.id, assigned_by_id=actor.id, is_active=True)
            investigation.assignments.append(assignment)
            session.add(investigation)
            session.flush()
            report = InvestigationReport(
                investigation_id=investigation.id,
                author_id=agent.id,
                content="Field findings",
            )
            session.add(report)
            session.flush()
            review = InvestigationReview(
                investigation_id=investigation.id,
                report_id=report.id,
                reviewer_id=actor.id,
                decision="approved",
            )
            session.add(review)
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
            from app.services.investigation import (
                delete_investigation,
                get_investigations,
                get_investigation,
                get_trashed_investigations,
                permanently_delete_investigation,
                restore_investigation,
            )

            investigation = session.get(Investigation, investigation_id)
            delete_investigation(session, investigation, actor)
            self.assertEqual(get_investigations(session, actor), [])
            self.assertIsNotNone(session.get(Investigation, investigation_id))
            self.assertEqual(session.query(InvestigationAssignment).count(), 1)
            self.assertEqual(session.query(InvestigationReport).count(), 1)
            self.assertEqual(session.query(InvestigationReview).count(), 1)
            soft_delete_event = session.query(ActivityLog).filter_by(
                action="investigation.deleted",
                object_id=investigation_id,
            ).one()
            self.assertEqual(soft_delete_event.actor_id, actor.id)
            self.assertEqual(soft_delete_event.details["reference_number"], "INV-CASCADE")
            self.assertIsNone(get_investigation(session, investigation_id))
            self.assertEqual(get_trashed_investigations(session)[0].id, investigation_id)

            investigation = get_trashed_investigations(session)[0]
            restore_investigation(session, investigation, actor)
            self.assertEqual(get_investigations(session, actor)[0].id, investigation_id)

            investigation = session.get(Investigation, investigation_id)
            delete_investigation(session, investigation, actor)
            investigation = get_trashed_investigations(session)[0]
            permanently_delete_investigation(session, investigation, actor)
            self.assertIsNone(session.get(Investigation, investigation_id))
            self.assertEqual(session.query(InvestigationAssignment).count(), 0)
            self.assertEqual(session.query(InvestigationReport).count(), 0)
            self.assertEqual(session.query(InvestigationReview).count(), 0)
            deletion_event = session.query(ActivityLog).filter_by(
                action="investigation.permanently_deleted",
                object_id=investigation_id,
            ).one()
            self.assertEqual(deletion_event.actor_id, actor.id)
            self.assertEqual(deletion_event.details["reference_number"], "INV-CASCADE")
            self.assertIsNotNone(deletion_event.created_at)


if __name__ == "__main__":
    unittest.main()
