import importlib.util
import unittest
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations


class RoutingMigrationDDLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "0007_routing_and_planning.py"
        spec = importlib.util.spec_from_file_location("routing_and_planning_migration", migration_path)
        cls.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.migration)

    def compile_operation(self, operation: str) -> str:
        output = StringIO()
        context = MigrationContext.configure(
            dialect_name="postgresql",
            opts={"as_sql": True, "output_buffer": output},
        )
        with Operations.context(context):
            getattr(self.migration, operation)()
        return output.getvalue()

    def test_upgrade_compiles_postgresql_location_constraints_and_planning_tables(self):
        sql = self.compile_operation("upgrade")
        self.assertIn("CREATE TABLE planning_runs", sql)
        self.assertIn("CREATE TABLE agent_shifts", sql)
        self.assertIn("CREATE TABLE planning_items", sql)
        self.assertIn("FOREIGN KEY(location_confirmed_by_id) REFERENCES users (id) ON DELETE SET NULL", sql)
        self.assertIn("latitude BETWEEN -90 AND 90", sql)
        self.assertIn("CREATE INDEX ix_investigations_h3_r9", sql)

    def test_downgrade_compiles_in_reverse_dependency_order(self):
        sql = self.compile_operation("downgrade")
        self.assertLess(sql.index("DROP TABLE planning_items"), sql.index("DROP TABLE agent_shifts"))
        self.assertLess(sql.index("DROP TABLE agent_shifts"), sql.index("DROP TABLE planning_runs"))
        self.assertIn("DROP COLUMN latitude", sql)

    def test_automatic_assignment_migration_adds_provenance_and_scope_lock_fields(self):
        path = Path(__file__).parents[1] / "alembic" / "versions" / "0010_automatic_assignment_source.py"
        spec = importlib.util.spec_from_file_location("automatic_assignment_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        output = StringIO()
        context = MigrationContext.configure(
            dialect_name="postgresql",
            opts={"as_sql": True, "output_buffer": output},
        )
        with Operations.context(context):
            migration.upgrade()
        sql = output.getvalue()
        self.assertIn("assignment_source VARCHAR(20) DEFAULT 'manual' NOT NULL", sql)
        self.assertIn("assignment_source IN ('manual', 'automatic')", sql)
        self.assertIn("auto_replan_requested BOOLEAN DEFAULT false NOT NULL", sql)
        self.assertIn("auto_assignment_ids JSON DEFAULT '[]' NOT NULL", sql)


if __name__ == "__main__":
    unittest.main()
