import importlib.util
import unittest
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


REVISION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0004_structured_investigation_names.py"
)
SPEC = importlib.util.spec_from_file_location("structured_names_revision", REVISION_PATH)
assert SPEC is not None and SPEC.loader is not None
REVISION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVISION)


class StructuredNameMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE investigations ("
                    "id INTEGER PRIMARY KEY, subject_name VARCHAR(255) NOT NULL)"
                )
            )
            connection.execute(
                text("INSERT INTO investigations (id, subject_name) VALUES (:id, :name)"),
                [
                    {"id": 1, "name": "Single"},
                    {"id": 2, "name": "Two Words"},
                    {"id": 3, "name": "A Multi Word Name"},
                    {"id": 4, "name": "  Preserve  Exact Spacing  "},
                ],
            )

    def tearDown(self):
        self.engine.dispose()

    def run_revision(self, operation):
        with self.engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                operation()

    def test_upgrade_preserves_ambiguous_names_without_inference_and_downgrade_restores(self):
        self.run_revision(REVISION.upgrade)

        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    "SELECT id, legacy_subject_name, first_name, middle_name, last_name "
                    "FROM investigations ORDER BY id"
                )
            ).all()
            self.assertEqual(
                [row.legacy_subject_name for row in rows],
                ["Single", "Two Words", "A Multi Word Name", "  Preserve  Exact Spacing  "],
            )
            for row in rows:
                self.assertIsNone(row.first_name)
                self.assertIsNone(row.middle_name)
                self.assertIsNone(row.last_name)

            connection.execute(
                text(
                    "UPDATE investigations SET first_name='Ada', middle_name='Augusta', "
                    "last_name='Lovelace', legacy_subject_name=NULL WHERE id=2"
                )
            )

        self.run_revision(REVISION.downgrade)

        with self.engine.begin() as connection:
            rows = connection.execute(
                text("SELECT id, subject_name FROM investigations ORDER BY id")
            ).all()
            self.assertEqual(
                [row.subject_name for row in rows],
                ["Single", "Ada Augusta Lovelace", "A Multi Word Name", "  Preserve  Exact Spacing  "],
            )


if __name__ == "__main__":
    unittest.main()
