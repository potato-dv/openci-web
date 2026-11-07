import importlib.util
import unittest
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0019_unified_agent_history_permission.py"
)
SPEC = importlib.util.spec_from_file_location("unified_history_revision", MIGRATION_PATH)
assert SPEC is not None and SPEC.loader is not None
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


class UnifiedHistoryMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, role VARCHAR(32) NOT NULL)"))
            connection.execute(text(
                "CREATE TABLE user_permission_overrides ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                "feature_code VARCHAR(100) NOT NULL, effect VARCHAR(10) NOT NULL, "
                "UNIQUE(user_id, feature_code))"
            ))
            connection.execute(text("INSERT INTO users (id, role) VALUES (1, 'agent'), (2, 'agent'), (3, 'agent'), (4, 'supervisor'), (5, 'agent')"))
            connection.execute(text(
                "INSERT INTO user_permission_overrides (user_id, feature_code, effect) VALUES "
                "(1, 'investigation.view_own_report_history', 'allow'), "
                "(1, 'investigation.view_own_completed', 'allow'), "
                "(2, 'investigation.view_own_report_history', 'allow'), "
                "(2, 'investigation.view_own_activity', 'allow'), "
                "(2, 'investigation.view_own_completed', 'allow'), "
                "(3, 'investigation.view_own_report_history', 'deny'), "
                "(3, 'investigation.view_own_activity', 'allow'), "
                "(3, 'investigation.view_own_completed', 'allow'), "
                "(4, 'investigation.view_own_report_history', 'allow')"
            ))

    def tearDown(self):
        self.engine.dispose()

    def run_migration(self, operation):
        with self.engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                operation()

    def test_upgrade_consolidates_without_granting_legacy_restricted_history(self):
        self.run_migration(MIGRATION.upgrade)

        with self.engine.begin() as connection:
            rows = connection.execute(text(
                "SELECT user_id, effect FROM user_permission_overrides "
                "WHERE feature_code = 'investigation.view_own_history' ORDER BY user_id"
            )).all()
            self.assertEqual(rows, [(1, "deny"), (2, "allow"), (3, "deny"), (5, "deny")])
            self.assertEqual(
                connection.execute(text(
                    "SELECT COUNT(*) FROM user_permission_overrides "
                    "WHERE feature_code IN ('investigation.view_own_report_history', "
                    "'investigation.view_own_activity', 'investigation.view_own_completed')"
                )).scalar_one(),
                0,
            )
            self.assertEqual(
                connection.execute(text(
                    "SELECT COUNT(*) FROM user_permission_overrides "
                    "WHERE user_id = 4 AND feature_code = 'investigation.view_own_history'"
                )).scalar_one(),
                0,
            )

    def test_downgrade_restores_a_restrictive_legacy_projection(self):
        self.run_migration(MIGRATION.upgrade)
        with self.engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id, role) VALUES (6, 'agent')"))
        self.run_migration(MIGRATION.downgrade)

        with self.engine.begin() as connection:
            rows = connection.execute(text(
                "SELECT user_id, feature_code, effect FROM user_permission_overrides "
                "ORDER BY user_id, feature_code"
            )).all()
            self.assertEqual(len(rows), 15)
            by_user = {}
            for user_id, feature_code, effect in rows:
                by_user.setdefault(user_id, {})[feature_code] = effect
            for user_id in (1, 3, 5, 6):
                self.assertEqual(set(by_user[user_id].values()), {"deny"})
            self.assertEqual(set(by_user[2].values()), {"allow"})
            self.assertNotIn(4, by_user)
            self.assertTrue(all(code.startswith("investigation.view_own_") for code in by_user[1]))


if __name__ == "__main__":
    unittest.main()
