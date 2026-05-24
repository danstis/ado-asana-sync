"""Schema versioning and SQLite migrations for the database package."""

import logging
import sqlite3

_LOGGER = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 2


class DatabaseMigrationsMixin:
    """Schema versioning and migration helpers for Database."""

    def _ensure_schema_version_table(self, conn):
        """Ensure schema_version table exists."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version INTEGER NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            )
        """)

    def get_schema_version(self, conn):
        """Get current schema version from database."""
        try:
            cursor = conn.execute("SELECT version FROM schema_version ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            return row[0] if row else 1
        except sqlite3.OperationalError as exc:
            if "no such table: schema_version" in str(exc):
                return 1
            raise

    def _record_migration(self, conn, version: int, description: str):
        """Record a completed migration in the schema_version table."""
        conn.execute(
            """
            INSERT INTO schema_version (version, description)
            VALUES (?, ?)
        """,
            (version, description),
        )
        _LOGGER.info("Recorded migration to version %d: %s", version, description)

    def _apply_migrations(self, conn):
        """Apply any pending migrations."""
        current_version = self.get_schema_version(conn)

        if current_version == 1:
            cursor = conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name IN ('matches', 'pr_matches', 'config', 'projects')
            """)
            existing_tables = cursor.fetchall()

            if not existing_tables:
                self._record_migration(conn, CURRENT_SCHEMA_VERSION, "Initial schema creation")
                return

        if current_version < 2:
            self._migrate_to_version_2(conn)
            self._record_migration(conn, 2, "Add composite unique constraint for projects table")

    def get_current_schema_version(self) -> int:
        """Get the current schema version from the database."""
        with self.get_connection() as conn:
            return self.get_schema_version(conn)

    def _migrate_to_version_2(self, conn):
        """Migrate to version 2: composite unique constraint for projects."""
        cursor = conn.execute("""
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name='projects'
        """)
        result = cursor.fetchone()

        if result is None:
            return

        table_sql = result[0]

        if "ado_project_name TEXT NOT NULL UNIQUE" in table_sql:
            _LOGGER.info("Migrating projects table to support multiple teams per project")

            cursor = conn.execute("SELECT ado_project_name, ado_team_name, asana_project_name FROM projects")
            existing_projects = cursor.fetchall()

            conn.execute("DROP TABLE projects")

            conn.execute("""
                CREATE TABLE projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ado_project_name TEXT NOT NULL,
                    ado_team_name TEXT NOT NULL,
                    asana_project_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ado_project_name, ado_team_name)
                )
            """)

            for project in existing_projects:
                conn.execute(
                    """
                    INSERT INTO projects (ado_project_name, ado_team_name, asana_project_name)
                    VALUES (?, ?, ?)
                """,
                    project,
                )

            _LOGGER.info("Successfully migrated %d project records", len(existing_projects))
        else:
            _LOGGER.debug("Projects table already has composite unique constraint, skipping migration")
