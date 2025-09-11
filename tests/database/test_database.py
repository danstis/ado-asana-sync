"""
Tests for SQLite database wrapper and migration functionality.

This module contains regression tests to ensure the SQLite migration from TinyDB
continues to work correctly and that the database wrapper maintains compatibility.
"""

import json
import os
import tempfile
import unittest

from ado_asana_sync.database.database import Database


class TestDatabaseMigration(unittest.TestCase):
    """Test cases for TinyDB to SQLite migration functionality."""

    def setUp(self):
        """Set up test fixtures with temporary directories."""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test.db")
        self.appdata_path = os.path.join(self.test_dir, "appdata.json")

    def tearDown(self):
        """Clean up test fixtures."""
        # Clean up any database files
        for file in os.listdir(self.test_dir):
            try:
                os.remove(os.path.join(self.test_dir, file))
            except OSError:
                pass
        try:
            os.rmdir(self.test_dir)
        except OSError:
            pass

    def test_migrate_from_tinydb_success(self):
        """Test successful migration from TinyDB format to SQLite."""
        # Create mock TinyDB data
        tinydb_data = {
            "matches": {
                "1": {
                    "ado_id": 123,
                    "ado_rev": 5,
                    "title": "Test Task",
                    "item_type": "Bug",
                    "url": "https://example.com",
                    "asana_gid": "asana-123",
                },
                "2": {
                    "ado_id": 456,
                    "ado_rev": 3,
                    "title": "Another Task",
                    "item_type": "User Story",
                    "url": "https://example.com/456",
                },
            },
            "pr_matches": {
                "1": {
                    "ado_pr_id": 789,
                    "ado_repository_id": "repo-789",
                    "title": "Test PR",
                    "status": "active",
                    "reviewer_gid": "reviewer-123",
                }
            },
            "config": {"1": {"key": "test_config", "value": "test_value"}},
        }

        # Write TinyDB data to file
        with open(self.appdata_path, "w", encoding="utf-8") as f:
            json.dump(tinydb_data, f)

        # Create database and migrate
        db = Database(self.db_path)
        result = db.migrate_from_tinydb(self.appdata_path)

        # Verify migration was successful
        self.assertTrue(result)

        # Verify data was migrated correctly
        matches_table = db.table("matches")
        all_matches = matches_table.all()
        self.assertEqual(len(all_matches), 2)

        # Check first record
        match_123 = next((m for m in all_matches if m["ado_id"] == 123), None)
        self.assertIsNotNone(match_123)
        self.assertEqual(match_123["title"], "Test Task")
        self.assertEqual(match_123["item_type"], "Bug")
        self.assertEqual(match_123["asana_gid"], "asana-123")

        # Check PR matches
        pr_matches_table = db.table("pr_matches")
        all_pr_matches = pr_matches_table.all()
        self.assertEqual(len(all_pr_matches), 1)
        self.assertEqual(all_pr_matches[0]["ado_pr_id"], 789)
        self.assertEqual(all_pr_matches[0]["title"], "Test PR")

        # Check config
        config_table = db.table("config")
        all_config = config_table.all()
        self.assertEqual(len(all_config), 1)
        self.assertEqual(all_config[0]["key"], "test_config")

        db.close()

    def test_migrate_from_tinydb_nonexistent_file(self):
        """Test migration when appdata.json doesn't exist."""
        nonexistent_path = os.path.join(self.test_dir, "nonexistent.json")

        db = Database(self.db_path)
        result = db.migrate_from_tinydb(nonexistent_path)

        # Should return True (successful no-op)
        self.assertTrue(result)
        db.close()

    def test_migrate_from_tinydb_invalid_json(self):
        """Test migration with invalid JSON file."""
        # Write invalid JSON
        with open(self.appdata_path, "w", encoding="utf-8") as f:
            f.write("invalid json content")

        db = Database(self.db_path)
        result = db.migrate_from_tinydb(self.appdata_path)

        # Should return False due to JSON decode error
        self.assertFalse(result)
        db.close()

    def test_migrate_filters_doc_id_from_records(self):
        """Regression test: Ensure migration filters out doc_id fields from TinyDB records."""
        # Create TinyDB data with doc_id fields (which should be filtered out)
        tinydb_data = {
            "matches": {
                "1": {
                    "ado_id": 999,
                    "title": "Task with doc_id",
                    "item_type": "Bug",
                    "doc_id": 12345,  # This should be filtered out during migration
                }
            }
        }

        with open(self.appdata_path, "w", encoding="utf-8") as f:
            json.dump(tinydb_data, f)

        db = Database(self.db_path)
        result = db.migrate_from_tinydb(self.appdata_path)

        self.assertTrue(result)

        # Verify the record was migrated but doc_id was filtered out
        matches_table = db.table("matches")
        all_matches = matches_table.all()
        self.assertEqual(len(all_matches), 1)

        migrated_record = all_matches[0]
        self.assertEqual(migrated_record["ado_id"], 999)
        self.assertEqual(migrated_record["title"], "Task with doc_id")

        # The SQLite wrapper should add doc_id for compatibility (different from the original TinyDB doc_id)
        self.assertIn("doc_id", migrated_record)  # This is added by DatabaseTable.all()
        # The new doc_id should be the SQLite row ID, not the original TinyDB doc_id
        self.assertNotEqual(migrated_record["doc_id"], 12345)  # Should not be the original doc_id

        db.close()

    def test_migrate_empty_tables(self):
        """Test migration with empty tables."""
        tinydb_data = {"matches": {}, "pr_matches": {}, "config": {}}

        with open(self.appdata_path, "w", encoding="utf-8") as f:
            json.dump(tinydb_data, f)

        db = Database(self.db_path)
        result = db.migrate_from_tinydb(self.appdata_path)

        self.assertTrue(result)

        # Verify tables exist but are empty
        self.assertEqual(len(db.table("matches").all()), 0)
        self.assertEqual(len(db.table("pr_matches").all()), 0)
        self.assertEqual(len(db.table("config").all()), 0)

        db.close()

    def test_projects_sync_functionality(self):
        """Test the projects sync functionality from JSON."""
        projects_data = [
            {"adoProjectName": "Project1", "adoTeamName": "Team1", "asanaProjectName": "AsanaProject1"},
            {"adoProjectName": "Project2", "adoTeamName": "Team2", "asanaProjectName": "AsanaProject2"},
        ]

        db = Database(self.db_path)
        db.sync_projects_from_json(projects_data)

        # Verify projects were synced
        retrieved_projects = db.get_projects()
        self.assertEqual(len(retrieved_projects), 2)

        self.assertEqual(retrieved_projects[0]["adoProjectName"], "Project1")
        self.assertEqual(retrieved_projects[0]["adoTeamName"], "Team1")
        self.assertEqual(retrieved_projects[0]["asanaProjectName"], "AsanaProject1")

        db.close()

    def test_projects_sync_replaces_existing(self):
        """Test that syncing projects replaces existing data."""
        # Initial projects
        initial_projects = [{"adoProjectName": "OldProject", "adoTeamName": "OldTeam", "asanaProjectName": "OldAsanaProject"}]

        db = Database(self.db_path)
        db.sync_projects_from_json(initial_projects)

        # Verify initial data
        projects = db.get_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["adoProjectName"], "OldProject")

        # Sync new projects (should replace old ones)
        new_projects = [
            {"adoProjectName": "NewProject1", "adoTeamName": "NewTeam1", "asanaProjectName": "NewAsanaProject1"},
            {"adoProjectName": "NewProject2", "adoTeamName": "NewTeam2", "asanaProjectName": "NewAsanaProject2"},
        ]

        db.sync_projects_from_json(new_projects)

        # Verify old data was replaced
        projects = db.get_projects()
        self.assertEqual(len(projects), 2)
        self.assertEqual(projects[0]["adoProjectName"], "NewProject1")
        self.assertEqual(projects[1]["adoProjectName"], "NewProject2")

        # Verify old project is gone
        old_project_names = [p["adoProjectName"] for p in projects]
        self.assertNotIn("OldProject", old_project_names)

        db.close()

    def test_multiple_teams_per_project_constraint(self):
        """Test that multiple teams from the same project can be synced with the new constraint."""
        projects_data = [
            {"adoProjectName": "TestProject", "adoTeamName": "Team1", "asanaProjectName": "TestProject-Team1"},
            {"adoProjectName": "TestProject", "adoTeamName": "Team2", "asanaProjectName": "TestProject-Team2"},
            {"adoProjectName": "AnotherProject", "adoTeamName": "Team1", "asanaProjectName": "AnotherProject-Team1"},
        ]

        db = Database(self.db_path)
        db.sync_projects_from_json(projects_data)

        # Verify all projects were synced (should not fail due to constraint)
        retrieved_projects = db.get_projects()
        self.assertEqual(len(retrieved_projects), 3)

        # Verify we can have the same project with different teams
        test_project_teams = [p for p in retrieved_projects if p["adoProjectName"] == "TestProject"]
        self.assertEqual(len(test_project_teams), 2)

        team_names = {p["adoTeamName"] for p in test_project_teams}
        self.assertEqual(team_names, {"Team1", "Team2"})

        # Verify same team name can exist across different projects
        team1_projects = [p for p in retrieved_projects if p["adoTeamName"] == "Team1"]
        self.assertEqual(len(team1_projects), 2)

        project_names = {p["adoProjectName"] for p in team1_projects}
        self.assertEqual(project_names, {"TestProject", "AnotherProject"})

        db.close()

    def test_duplicate_project_team_combination_fails(self):
        """Test that duplicate project+team combinations still fail appropriately."""
        projects_data = [
            {"adoProjectName": "TestProject", "adoTeamName": "Team1", "asanaProjectName": "TestProject-Team1"},
            {"adoProjectName": "TestProject", "adoTeamName": "Team1", "asanaProjectName": "TestProject-Team1-Duplicate"},
        ]

        db = Database(self.db_path)

        # This should raise an exception due to the unique constraint violation
        with self.assertRaises(Exception):
            db.sync_projects_from_json(projects_data)

        db.close()

    def test_migration_from_old_schema(self):
        """Test migration from old single-column unique constraint to new composite constraint."""
        # This test is now covered by test_schema_versioning_old_database_migration
        # But keeping it for backward compatibility testing

        db = Database(self.db_path)

        # Manually create the old table schema
        with db.get_connection() as conn:
            # Drop schema_version and projects tables to simulate old database
            conn.execute("DROP TABLE IF EXISTS schema_version")
            conn.execute("DROP TABLE IF EXISTS projects")
            conn.execute("""
                CREATE TABLE projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ado_project_name TEXT NOT NULL UNIQUE,
                    ado_team_name TEXT NOT NULL,
                    asana_project_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Insert test data with old schema
            conn.execute("""
                INSERT INTO projects (ado_project_name, ado_team_name, asana_project_name)
                VALUES ('OldProject', 'OldTeam', 'OldAsanaProject')
            """)

        # Close and reopen database to trigger migration
        db.close()

        # Create new database instance - this should trigger migration
        db = Database(self.db_path)

        # Verify the migration was applied (schema version should be 2)
        self.assertEqual(db.get_current_schema_version(), 2)

        # Verify the old data is still there
        projects = db.get_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["adoProjectName"], "OldProject")
        self.assertEqual(projects[0]["adoTeamName"], "OldTeam")

        # Verify we can now add multiple teams for the same project
        new_projects = [
            {"adoProjectName": "OldProject", "adoTeamName": "OldTeam", "asanaProjectName": "OldAsanaProject"},
            {"adoProjectName": "OldProject", "adoTeamName": "NewTeam", "asanaProjectName": "OldProject-NewTeam"},
        ]

        # This should work without constraint violations
        db.sync_projects_from_json(new_projects)

        # Verify both projects exist
        projects = db.get_projects()
        self.assertEqual(len(projects), 2)

        old_project_teams = [p for p in projects if p["adoProjectName"] == "OldProject"]
        self.assertEqual(len(old_project_teams), 2)

        db.close()

    def test_schema_versioning_new_database(self):
        """Test that new databases are created with the current schema version."""
        db = Database(self.db_path)

        # New database should be at current version
        current_version = db.get_current_schema_version()
        self.assertEqual(current_version, 2)  # CURRENT_SCHEMA_VERSION

        # Verify schema_version table has the initial record
        with db.get_connection() as conn:
            cursor = conn.execute("SELECT version, description FROM schema_version ORDER BY id")
            records = cursor.fetchall()

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0][0], 2)  # version
            self.assertEqual(records[0][1], "Initial schema creation")  # description

        db.close()

    def test_schema_versioning_old_database_migration(self):
        """Test that old databases are properly migrated and version is recorded."""
        db = Database(self.db_path)

        # Manually create an old database by removing version table and creating old schema
        with db.get_connection() as conn:
            # Drop schema_version and projects tables
            conn.execute("DROP TABLE IF EXISTS schema_version")
            conn.execute("DROP TABLE IF EXISTS projects")

            # Create old projects table schema
            conn.execute("""
                CREATE TABLE projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ado_project_name TEXT NOT NULL UNIQUE,
                    ado_team_name TEXT NOT NULL,
                    asana_project_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Insert test data
            conn.execute("""
                INSERT INTO projects (ado_project_name, ado_team_name, asana_project_name)
                VALUES ('TestProject', 'TestTeam', 'TestAsanaProject')
            """)

        # Close and reopen to trigger migration
        db.close()
        db = Database(self.db_path)

        # Should now be at version 2
        current_version = db.get_current_schema_version()
        self.assertEqual(current_version, 2)

        # Verify migration was recorded
        with db.get_connection() as conn:
            cursor = conn.execute("SELECT version, description FROM schema_version ORDER BY id")
            records = cursor.fetchall()

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0][0], 2)  # version
            self.assertEqual(records[0][1], "Add composite unique constraint for projects table")  # description

        # Verify data was preserved
        projects = db.get_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["adoProjectName"], "TestProject")

        db.close()

    def test_schema_versioning_already_migrated(self):
        """Test that already migrated databases don't get migrated again."""
        db = Database(self.db_path)

        # First initialization creates version record
        initial_version = db.get_current_schema_version()

        # Get initial migration records
        with db.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM schema_version")
            initial_count = cursor.fetchone()[0]

        # Close and reopen database - should not create additional migration records
        db.close()
        db = Database(self.db_path)

        # Version should be the same
        current_version = db.get_current_schema_version()
        self.assertEqual(current_version, initial_version)

        # Should not have created additional migration records
        with db.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM schema_version")
            final_count = cursor.fetchone()[0]

        self.assertEqual(final_count, initial_count)

        db.close()

    def test_schema_version_table_structure(self):
        """Test that schema_version table has the correct structure."""
        db = Database(self.db_path)

        with db.get_connection() as conn:
            # Test table structure
            cursor = conn.execute("PRAGMA table_info(schema_version)")
            columns = cursor.fetchall()

            # Verify expected columns exist
            column_names = [col[1] for col in columns]  # col[1] is column name
            expected_columns = ["id", "version", "applied_at", "description"]

            for expected_col in expected_columns:
                self.assertIn(expected_col, column_names)

            # Verify primary key
            primary_key_cols = [col[1] for col in columns if col[5] == 1]  # col[5] is pk flag
            self.assertEqual(primary_key_cols, ["id"])

        db.close()


class TestDatabaseWrapper(unittest.TestCase):
    """Test cases for SQLite database wrapper functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test.db")

    def tearDown(self):
        """Clean up test fixtures."""
        # Clean up database files
        for file in os.listdir(self.test_dir):
            try:
                os.remove(os.path.join(self.test_dir, file))
            except OSError:
                pass
        try:
            os.rmdir(self.test_dir)
        except OSError:
            pass

    def test_database_table_compatibility(self):
        """Test that DatabaseTable provides TinyDB-like interface."""
        db = Database(self.db_path)
        table = db.table("matches")  # Use existing table name

        # Test insert
        doc_id = table.insert({"key": "value", "number": 123})
        self.assertIsInstance(doc_id, int)

        # Test search with lambda function
        results = table.search(lambda record: record.get("key") == "value")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["key"], "value")
        self.assertEqual(results[0]["number"], 123)
        # Should include doc_id for compatibility
        self.assertIn("doc_id", results[0])

        # Test contains
        self.assertTrue(table.contains(lambda record: record.get("key") == "value"))
        self.assertFalse(table.contains(lambda record: record.get("key") == "nonexistent"))

        # Test update
        updated_ids = table.update({"key": "updated_value", "number": 456}, lambda record: record.get("key") == "value")
        self.assertEqual(len(updated_ids), 1)

        # Verify update worked
        results = table.search(lambda record: record.get("key") == "updated_value")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["number"], 456)

        db.close()

    def test_database_wal_mode_enabled(self):
        """Test that WAL mode is properly enabled."""
        db = Database(self.db_path)

        with db.get_connection() as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            journal_mode = cursor.fetchone()[0]
            self.assertEqual(journal_mode.upper(), "WAL")

        db.close()

    def test_database_cleanup_on_close(self):
        """Test that database cleanup works properly."""
        db = Database(self.db_path)

        # Insert some data
        table = db.table("matches")  # Use existing table name
        table.insert({"test": "data"})

        # Close database (should clean up WAL files)
        db.close()

        # Verify database file exists but WAL files are cleaned up
        self.assertTrue(os.path.exists(self.db_path))
        # WAL files should be cleaned up (though they might not exist if no concurrent writes)
        # These files may or may not exist depending on SQLite's internal state
        # The important thing is that close() doesn't crash

    def test_upsert_update_existing_record(self):
        """Test that upsert updates an existing record."""
        db = Database(self.db_path)
        table = db.table("matches")  # Use existing table

        # Insert initial record
        test_data = {"name": "John", "age": 25}
        record_id = table.insert(test_data)

        # Update via upsert
        updated_data = {"name": "John", "age": 26}

        def query_func(record):
            return record.get("name") == "John"

        result_id = table.upsert(updated_data, query_func)

        # Should return the same ID (updated, not inserted)
        self.assertEqual(result_id, record_id)

        # Verify the record was updated
        all_records = table.all()
        self.assertEqual(len(all_records), 1)
        self.assertEqual(all_records[0]["age"], 26)

        db.close()

    def test_search_with_query_function(self):
        """Test searching records with a query function."""
        db = Database(self.db_path)
        table = db.table("matches")  # Use existing table

        # Insert test data
        table.insert({"name": "Alice", "age": 30})
        table.insert({"name": "Bob", "age": 25})
        table.insert({"name": "Charlie", "age": 35})

        # Search for people over 30
        def query_func(record):
            return record.get("age", 0) > 30

        results = table.search(query_func)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Charlie")
        self.assertEqual(results[0]["age"], 35)

        db.close()

    def test_contains_method(self):
        """Test the contains method with query function."""
        db = Database(self.db_path)
        table = db.table("matches")  # Use existing table

        # Insert test data
        table.insert({"name": "Diana", "status": "active"})

        # Test contains with existing record
        def query_exists(record):
            return record.get("name") == "Diana"

        def query_not_exists(record):
            return record.get("name") == "Frank"

        self.assertTrue(table.contains(query_exists))
        self.assertFalse(table.contains(query_not_exists))

        db.close()


if __name__ == "__main__":
    unittest.main()
