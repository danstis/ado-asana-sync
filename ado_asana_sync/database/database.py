"""
SQLite database wrapper for ADO-Asana sync application.

This module provides a thread-safe SQLite database wrapper that maintains
compatibility with the existing TinyDB interface while providing better
concurrency support and data integrity.
"""

import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

_LOGGER = logging.getLogger(__name__)

# Current database schema version
CURRENT_SCHEMA_VERSION = 2


class DatabaseTable:
    """
    Represents a table in the SQLite database with TinyDB-like interface.
    """

    def __init__(self, db: "Database", table_name: str):
        self.db = db
        # table_name is validated and comes from a controlled set of names
        self.table_name = table_name

    def insert(self, data: Dict[str, Any]) -> int:
        """Insert a new record and return the row ID."""
        with self.db.get_connection() as conn:
            # Convert data to JSON for storage
            json_data = json.dumps(data, default=str)
            cursor = conn.execute(
                f"INSERT INTO {self.table_name} (data) VALUES (?)",  # nosec B608 - table_name is controlled
                (json_data,),
            )
            return cursor.lastrowid

    def update(self, data: Dict[str, Any], query_func) -> List[int]:
        """Update records matching the query function."""
        with self.db.get_connection() as conn:
            # Get matching records first
            matching_ids = []
            cursor = conn.execute(f"SELECT id, data FROM {self.table_name}")  # nosec B608 - table_name is controlled

            for row_id, json_data in cursor:
                record = json.loads(json_data)
                record["doc_id"] = row_id  # Add doc_id for TinyDB compatibility
                if query_func(record):
                    matching_ids.append(row_id)

            # Update matching records
            if matching_ids:
                json_data = json.dumps(data, default=str)
                placeholders = ",".join(["?" for _ in matching_ids])
                conn.execute(
                    f"UPDATE {self.table_name} SET data = ?, updated_at = CURRENT_TIMESTAMP "  # nosec B608
                    f"WHERE id IN ({placeholders})",
                    [json_data] + matching_ids,
                )

            return matching_ids

    def upsert(self, data: Dict[str, Any], query_func) -> int:
        """Insert or update a record based on query function."""
        with self.db.get_connection() as conn:
            # Try to find existing record
            cursor = conn.execute(f"SELECT id, data FROM {self.table_name}")  # nosec B608 - table_name is controlled

            for row_id, json_data in cursor:
                record = json.loads(json_data)
                record["doc_id"] = row_id
                if query_func(record):
                    # Update existing record
                    json_data = json.dumps(data, default=str)
                    conn.execute(
                        f"UPDATE {self.table_name} SET data = ?, updated_at = CURRENT_TIMESTAMP "  # nosec B608
                        f"WHERE id = ?",
                        (json_data, row_id),
                    )
                    return row_id

            # Insert new record if no match found
            return self.insert(data)

    def search(self, query_func) -> List[Dict[str, Any]]:
        """Search for records matching the query function."""
        with self.db.get_connection() as conn:
            results = []
            cursor = conn.execute(f"SELECT id, data FROM {self.table_name}")  # nosec B608 - table_name is controlled

            for row_id, json_data in cursor:
                record = json.loads(json_data)
                record["doc_id"] = row_id
                if query_func(record):
                    results.append(record)

            return results

    def contains(self, query_func) -> bool:
        """Check if any record matches the query function."""
        return len(self.search(query_func)) > 0

    def get(self, doc_id: Optional[int] = None, **kwargs) -> Optional[Dict[str, Any]]:
        """Get a record by doc_id or other criteria."""
        with self.db.get_connection() as conn:
            if doc_id is not None:
                cursor = conn.execute(
                    f"SELECT id, data FROM {self.table_name} WHERE id = ?",  # nosec B608
                    (doc_id,),
                )
                row = cursor.fetchone()
                if row:
                    record = json.loads(row[1])
                    record["doc_id"] = row[0]
                    return record

            # Handle other criteria (for config table compatibility)
            if kwargs:
                cursor = conn.execute(f"SELECT id, data FROM {self.table_name}")  # nosec B608 - table_name is controlled
                for row_id, json_data in cursor:
                    record = json.loads(json_data)
                    record["doc_id"] = row_id

                    # Check if record matches all criteria
                    matches = all(record.get(k) == v for k, v in kwargs.items())
                    if matches:
                        return record

            return None

    def all(self) -> List[Dict[str, Any]]:
        """Get all records in the table."""
        with self.db.get_connection() as conn:
            results = []
            cursor = conn.execute(f"SELECT id, data FROM {self.table_name}")  # nosec B608 - table_name is controlled

            for row_id, json_data in cursor:
                record = json.loads(json_data)
                record["doc_id"] = row_id
                results.append(record)

            return results

    def remove(self, doc_ids: Optional[List[int]] = None, query_func=None) -> List[int]:
        """Remove records by doc_ids or query function."""
        with self.db.get_connection() as conn:
            removed_ids = []

            if doc_ids:
                placeholders = ",".join(["?" for _ in doc_ids])
                conn.execute(
                    f"DELETE FROM {self.table_name} WHERE id IN ({placeholders})",  # nosec B608
                    doc_ids,
                )
                removed_ids = doc_ids
            elif query_func:
                # Find matching records first
                cursor = conn.execute(f"SELECT id, data FROM {self.table_name}")  # nosec B608 - table_name is controlled

                for row_id, json_data in cursor:
                    record = json.loads(json_data)
                    record["doc_id"] = row_id
                    if query_func(record):
                        removed_ids.append(row_id)

                # Remove matching records
                if removed_ids:
                    placeholders = ",".join(["?" for _ in removed_ids])
                    conn.execute(
                        f"DELETE FROM {self.table_name} WHERE id IN ({placeholders})",  # nosec B608
                        removed_ids,
                    )

            return removed_ids


class Database:
    """
    SQLite database wrapper with TinyDB-like interface.

    Provides thread-safe access to SQLite database with WAL mode enabled
    for better concurrent performance.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._connections: set[sqlite3.Connection] = set()  # Track all connections for cleanup
        self._lock = threading.Lock()
        self._init_database()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure cleanup."""
        self.close()

    def _init_database(self):
        """Initialize the database with required tables."""
        with self.get_connection() as conn:
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=10000")
            conn.execute("PRAGMA temp_store=MEMORY")

            # Ensure schema version tracking table exists
            self._ensure_schema_version_table(conn)

            # Apply any pending migrations
            self._apply_migrations(conn)

            # Create tables with JSON data storage
            conn.execute("""
                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS pr_matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ado_project_name TEXT NOT NULL,
                    ado_team_name TEXT NOT NULL,
                    asana_project_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ado_project_name, ado_team_name)
                )
            """)

            # Create indexes for better performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_matches_data
                ON matches(json_extract(data, '$.ado_id'))
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pr_matches_data
                ON pr_matches(json_extract(data, '$.pr_id'))
            """)

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
            # Fallback only if version table doesn't exist (old schema)
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

        # For new databases, record the current schema version
        if current_version == 1:
            # Check if this is truly a new database (no tables) or an old database
            cursor = conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name IN ('matches', 'pr_matches', 'config', 'projects')
            """)
            existing_tables = cursor.fetchall()

            if not existing_tables:
                # This is a new database, set it to current version
                self._record_migration(conn, CURRENT_SCHEMA_VERSION, "Initial schema creation")
                return

        if current_version < 2:
            self._migrate_to_version_2(conn)
            self._record_migration(conn, 2, "Add composite unique constraint for projects table")

        # Future migrations would be added here:
        # if current_version < 3:
        #     self._migrate_to_version_3(conn)
        #     self._record_migration(conn, 3, "Description of version 3 migration")

    def get_current_schema_version(self) -> int:
        """Get the current schema version from the database."""
        with self.get_connection() as conn:
            return self.get_schema_version(conn)

    def _migrate_to_version_2(self, conn):
        """Migrate to version 2: composite unique constraint for projects."""
        # Check if projects table exists and what its schema looks like
        cursor = conn.execute("""
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name='projects'
        """)
        result = cursor.fetchone()

        if result is None:
            # Table doesn't exist yet, no migration needed
            return

        table_sql = result[0]

        # Check if the table has the old UNIQUE constraint on just ado_project_name
        if "ado_project_name TEXT NOT NULL UNIQUE" in table_sql:
            _LOGGER.info("Migrating projects table to support multiple teams per project")

            # Get existing data
            cursor = conn.execute("SELECT ado_project_name, ado_team_name, asana_project_name FROM projects")
            existing_projects = cursor.fetchall()

            # Drop the old table
            conn.execute("DROP TABLE projects")

            # Create the new table with the updated schema
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

            # Insert the existing data back
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

    @contextmanager
    def get_connection(self):
        """Get a thread-local database connection."""
        if not hasattr(self._local, "connection"):
            self._local.connection = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
            self._local.connection.row_factory = sqlite3.Row

            # Track connection for cleanup
            with self._lock:
                self._connections.add(self._local.connection)

        try:
            yield self._local.connection
            self._local.connection.commit()
        except Exception:
            self._local.connection.rollback()
            raise

    def table(self, table_name: str) -> DatabaseTable:
        """Get a table interface."""
        return DatabaseTable(self, table_name)

    def sync_projects_from_json(self, projects_data: List[Dict[str, str]]) -> None:
        """Sync projects from JSON data into the projects table."""
        with self.get_connection() as conn:
            # Clear existing projects
            conn.execute("DELETE FROM projects")

            # Insert new projects
            for project in projects_data:
                conn.execute(
                    """
                    INSERT INTO projects (ado_project_name, ado_team_name, asana_project_name)
                    VALUES (?, ?, ?)
                """,
                    (project["adoProjectName"], project["adoTeamName"], project["asanaProjectName"]),
                )

            _LOGGER.info("Synced %d projects to database", len(projects_data))

    def get_projects(self) -> List[Dict[str, str]]:
        """Get all projects from the database."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT ado_project_name, ado_team_name, asana_project_name
                FROM projects
                ORDER BY ado_project_name, ado_team_name
            """)

            projects = []
            for row in cursor:
                projects.append({"adoProjectName": row[0], "adoTeamName": row[1], "asanaProjectName": row[2]})

            return projects

    def migrate_from_tinydb(self, appdata_path: str) -> bool:
        """
        Migrate data from TinyDB JSON file to SQLite.

        Args:
            appdata_path: Path to the appdata.json file

        Returns:
            bool: True if migration was successful, False otherwise
        """
        if not os.path.exists(appdata_path):
            _LOGGER.info("No appdata.json file found, skipping migration")
            return True

        try:
            _LOGGER.info("Starting migration from %s", appdata_path)

            with open(appdata_path, "r", encoding="utf-8") as f:
                tinydb_data = json.load(f)

            with self.get_connection() as conn:
                self._migrate_table_data(conn, tinydb_data, "matches")
                self._migrate_table_data(conn, tinydb_data, "pr_matches")
                self._migrate_table_data(conn, tinydb_data, "config")

            _LOGGER.info("Migration completed successfully")
            return True

        except Exception as e:  # pylint: disable=broad-exception-caught
            _LOGGER.error("Migration failed: %s", e)
            return False

    def _migrate_table_data(self, conn, tinydb_data: Dict[str, Any], table_name: str):
        """Helper method to migrate data for a specific table."""
        if table_name in tinydb_data:
            table_data = tinydb_data[table_name]
            for doc_id, record in table_data.items():
                if doc_id == "_default":
                    continue

                # Clean up the record (remove doc_id if present)
                clean_record = {k: v for k, v in record.items() if k != "doc_id"}
                json_data = json.dumps(clean_record, default=str)

                conn.execute(
                    f"INSERT INTO {table_name} (data) VALUES (?)",  # nosec B608 - table_name is controlled
                    (json_data,),
                )

            count = len(table_data) - 1 if "_default" in table_data else len(table_data)
            _LOGGER.info("Migrated %d %s records", count, table_name)

    def close(self):
        """Close all database connections and clean up WAL files."""
        with self._lock:
            # Close all tracked connections
            connections_to_close = list(self._connections)
            self._connections.clear()

        for conn in connections_to_close:
            try:
                # Checkpoint the WAL file to merge changes back to main database
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.close()
            except Exception as e:  # pylint: disable=broad-exception-caught
                _LOGGER.warning("Error closing database connection: %s", e)

        # Clean up thread-local connection if it exists
        if hasattr(self._local, "connection"):
            try:
                delattr(self._local, "connection")
            except Exception as e:  # pylint: disable=broad-exception-caught
                _LOGGER.warning("Error cleaning up thread-local connection: %s", e)

        _LOGGER.debug("All database connections closed")
