import unittest
from datetime import datetime, timezone

from fastapi import HTTPException, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
import app.models
from app.controllers.investigation import get_investigation_report, get_investigation_report_versions, get_one
from app.models.activity import ActivityLog
from app.models.investigation import Investigation
from app.models.report import InvestigationReport
from app.models.user import User
from app.models.user_permission_override import UserPermissionOverride
from app.routes.investigation import get_investigation_activity_history, get_investigations
from app.routes.user import set_agent_permissions
from app.schemas.agent_permissions import AgentPermissionOverrideMap
from app.services.agent_permissions import effective_agent_permissions, is_agent_feature_allowed, require_agent_feature
from app.services.agent_revisits import can_request_agent_revisit


class AgentPermissionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def add_user(self, db: Session, suffix: str, role: str = "agent") -> User:
        user = User(name=f"{role.title()} {suffix}", email=f"{suffix}@example.test", password="hash", role=role)
        db.add(user)
        db.flush()
        return user

    def add_case(self, db: Session, agent: User, status: str = "assigned") -> Investigation:
        case = Investigation(
            reference_number=f"INV-{agent.id}-{status}",
            legacy_subject_name="Example Subject",
            status=status,
            priority="normal",
            assigned_agent_id=agent.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(case)
        db.flush()
        return case

    def full_map(self):
        return {
            "investigation.request_revisit": "inherit",
            "route.view_own_history": "inherit",
            "investigation.view_own_history": "deny",
        }

    def test_defaults_and_overrides_are_individual_to_each_agent(self):
        with Session(self.engine) as db:
            lyka = self.add_user(db, "lyka")
            other = self.add_user(db, "other")
            db.add(UserPermissionOverride(user_id=lyka.id, feature_code="route.view_own_history", effect="deny"))
            db.commit()

            lyka_permissions = effective_agent_permissions(db, lyka)
            other_permissions = effective_agent_permissions(db, other)
            self.assertFalse(lyka_permissions["route.view_own_history"])
            self.assertTrue(other_permissions["route.view_own_history"])
            self.assertFalse(other_permissions["investigation.view_own_history"])
            self.assertFalse(is_agent_feature_allowed(db, other, "investigation.view_own_history"))

    def test_denied_feature_is_403_and_unknown_or_incomplete_maps_are_rejected(self):
        with Session(self.engine) as db:
            agent = self.add_user(db, "denied")
            db.add(UserPermissionOverride(user_id=agent.id, feature_code="investigation.request_revisit", effect="deny"))
            db.commit()
            with self.assertRaises(HTTPException) as denied:
                require_agent_feature(db, agent, "investigation.request_revisit")
            self.assertEqual(denied.exception.status_code, 403)

            invalid = self.full_map()
            invalid["investigation.unknown"] = "allow"
            with self.assertRaises(ValueError):
                AgentPermissionOverrideMap(overrides=invalid)
            incomplete = self.full_map()
            incomplete.pop("route.view_own_history")
            with self.assertRaises(ValueError):
                AgentPermissionOverrideMap(overrides=incomplete)
            inherited_history = self.full_map()
            inherited_history["investigation.view_own_history"] = "inherit"
            with self.assertRaises(ValueError):
                AgentPermissionOverrideMap(overrides=inherited_history)

    def test_completed_cases_are_removed_before_agent_counts_and_detail_reads(self):
        with Session(self.engine) as db:
            agent = self.add_user(db, "completed-reader")
            self.add_case(db, agent, "assigned")
            completed = self.add_case(db, agent, "completed")
            db.add(UserPermissionOverride(user_id=agent.id, feature_code="investigation.view_own_history", effect="deny"))
            db.commit()

            page = get_investigations(
                db=db,
                current_user=agent,
                q="",
                status=None,
                priority=None,
                assigned_agent_id=None,
                location_confirmed=None,
                sort="created_at",
                direction="desc",
                page=1,
                page_size=25,
            )
            self.assertEqual(page["total"], 1)
            self.assertEqual(page["facets"]["status"]["completed"], 0)
            with self.assertRaises(HTTPException) as denied:
                get_one(db, completed.id, agent)
            self.assertEqual(denied.exception.status_code, 403)

    def test_report_history_denial_does_not_change_current_ownership(self):
        with Session(self.engine) as db:
            agent = self.add_user(db, "report-reader")
            other = self.add_user(db, "other-owner")
            case = self.add_case(db, agent)
            other_case = self.add_case(db, other)
            db.add(UserPermissionOverride(user_id=agent.id, feature_code="investigation.view_own_history", effect="deny"))
            report = InvestigationReport(
                investigation_id=case.id,
                author_id=agent.id,
                version=1,
                content="Current report",
                status="draft",
            )
            db.add(report)
            db.commit()

            with self.assertRaises(HTTPException) as denied_history:
                get_investigation_report_versions(db, case.id, agent)
            self.assertEqual(denied_history.exception.status_code, 403)
            self.assertEqual(get_investigation_report(db, case.id, agent).content, "Current report")
            with self.assertRaises(HTTPException) as denied_ownership:
                get_one(db, other_case.id, agent)
            self.assertEqual(denied_ownership.exception.status_code, 403)

    def test_revisit_eligibility_does_not_depend_on_report_history_permission(self):
        with Session(self.engine) as db:
            agent = self.add_user(db, "revisit-reader")
            case = self.add_case(db, agent, "returned_for_correction")
            case.region_code = "1300000000"
            case.latitude = 14.6
            case.longitude = 121.0
            case.location_source = "manual"
            case.location_confirmed_at = datetime.now(timezone.utc)
            case.h3_r7 = "r7"
            case.h3_r8 = "r8"
            case.h3_r9 = "r9"
            db.add(InvestigationReport(
                investigation_id=case.id,
                author_id=agent.id,
                version=1,
                content="Returned report",
                status="returned_for_correction",
            ))
            db.add(UserPermissionOverride(
                user_id=agent.id,
                feature_code="investigation.view_own_history",
                effect="deny",
            ))
            db.commit()

            self.assertFalse(is_agent_feature_allowed(db, agent, "investigation.view_own_history"))
            self.assertTrue(can_request_agent_revisit(db, case, agent))
            self.assertEqual(get_one(db, case.id, agent).status, "returned_for_correction")

    def test_activity_timeline_is_owner_scoped_and_returns_only_allowlisted_fields(self):
        with Session(self.engine) as db:
            agent = self.add_user(db, "activity-reader")
            other = self.add_user(db, "unrelated")
            case = self.add_case(db, agent)
            other_case = self.add_case(db, other)
            db.add(UserPermissionOverride(user_id=agent.id, feature_code="investigation.view_own_history", effect="allow"))
            db.add_all([
                ActivityLog(actor_id=other.id, action="report.submitted", object_type="investigation", object_id=case.id,
                            details={"content": "private report body", "address": "private address"}),
                ActivityLog(actor_id=other.id, action="investigation.location_confirmed", object_type="investigation", object_id=case.id,
                            details={"latitude": 1.0, "longitude": 2.0}),
            ])
            db.commit()

            response = get_investigation_activity_history(case.id, Response(), db, agent)
            self.assertEqual(len(response["items"]), 1)
            self.assertEqual(response["items"][0]["label"], "Report submitted")
            self.assertNotIn("details", response["items"][0])
            self.assertNotIn("content", response["items"][0])
            with self.assertRaises(HTTPException) as denied:
                get_investigation_activity_history(other_case.id, Response(), db, agent)
            self.assertEqual(denied.exception.status_code, 403)

            db.add(UserPermissionOverride(user_id=other.id, feature_code="investigation.view_own_history", effect="deny"))
            db.commit()
            with self.assertRaises(HTTPException) as history_denied:
                get_investigation_activity_history(other_case.id, Response(), db, other)
            self.assertEqual(history_denied.exception.status_code, 403)

    def test_admin_save_is_audited_with_old_and_new_effective_values(self):
        with Session(self.engine) as db:
            admin = self.add_user(db, "admin", "admin")
            agent = self.add_user(db, "configured")
            overrides = self.full_map()
            overrides["investigation.view_own_history"] = "allow"
            state = set_agent_permissions(agent.id, AgentPermissionOverrideMap(overrides=overrides), Response(), db, admin)
            audit = db.query(ActivityLog).filter_by(action="agent.permissions_changed", object_id=agent.id).one()
            self.assertTrue(state["features"][2]["effective_allowed"])
            self.assertFalse(audit.details["old_effective"]["investigation.view_own_history"])
            self.assertTrue(audit.details["new_effective"]["investigation.view_own_history"])
            self.assertEqual(audit.actor_id, admin.id)

    def test_permission_revocation_takes_effect_for_existing_agent_session(self):
        with Session(self.engine) as db:
            agent = self.add_user(db, "session-revocation")
            case = self.add_case(db, agent)
            db.add(InvestigationReport(
                investigation_id=case.id,
                author_id=agent.id,
                version=1,
                content="Current report body",
                status="draft",
            ))
            db.add(UserPermissionOverride(
                user_id=agent.id,
                feature_code="investigation.view_own_history",
                effect="allow",
            ))
            db.commit()

            # Reuse the same authenticated User object while the feature
            # resolver queries the override table on each protected request.
            self.assertTrue(effective_agent_permissions(db, agent)["investigation.view_own_history"])
            self.assertEqual(len(get_investigation_report_versions(db, case.id, agent)), 1)
            self.assertEqual(get_investigation_report(db, case.id, agent).content, "Current report body")

            db.query(UserPermissionOverride).filter_by(
                user_id=agent.id,
                feature_code="investigation.view_own_history",
            ).update({"effect": "deny"})
            db.commit()

            self.assertFalse(effective_agent_permissions(db, agent)["investigation.view_own_history"])
            with self.assertRaises(HTTPException) as revoked:
                get_investigation_report_versions(db, case.id, agent)
            self.assertEqual(revoked.exception.status_code, 403)
            self.assertEqual(get_investigation_report(db, case.id, agent).content, "Current report body")


if __name__ == "__main__":
    unittest.main()
