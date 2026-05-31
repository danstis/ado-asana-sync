"""SQLite connection and table wrappers for the database package."""

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from .migrations import DatabaseMigrationsMixin
from .tinydb_migration import TinyDBMigrationMixin

_LOGGER = logging.getLogger(__name__)


class DatabaseTable:
    """Represents a table in the SQLite database."""

    def __init__(self, db: "Database", table_name: str):
        self.db = db
        # table_name is validated and comes from a controlled set of names
        self.table_name = table_name

    def insert(self, data: Dict[str, Any]) -> int:
        """Insert a new record and return the row ID."""
        with self.db.get_connection() as conn:
            json_data = json.dumps(data, default=str)
            cursor = conn.execute(
                f"INSERT INTO {self.table_name} (data) VALUES (?)",  # nosec B608 - table_name is controlled
                (json_data,),
            )
            return cursor.lastrowid

    def update(self, data: Dict[str, Any], query_func) -> List[int]:
        """Update records matching the query function."""
        with self.db.get_connection() as conn:
            matching_ids = []
            cursor = conn.execute(f"SELECT id, data FROM {self.table_name}")  # nosec B608 - table_name is controlled

            for row_id, json_data in cursor:
                record = json.loads(json_data)
                record["doc_id"] = row_id
                if query_func(record):
                    matching_ids.append(row_id)

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
            cursor = conn.execute(f"SELECT id, data FROM {self.table_name}")  # nosec B608 - table_name is controlled

            for row_id, json_data in cursor:
                record = json.loads(json_data)
                record["doc_id"] = row_id
                if query_func(record):
                    json_data = json.dumps(data, default=str)
                    conn.execute(
                        f"UPDATE {self.table_name} SET data = ?, updated_at = CURRENT_TIMESTAMP "  # nosec B608
                        f"WHERE id = ?",
                        (json_data, row_id),
                    )
                    return row_id

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

            if kwargs:
                cursor = conn.execute(f"SELECT id, data FROM {self.table_name}")  # nosec B608 - table_name is controlled
                for row_id, json_data in cursor:
                    record = json.loads(json_data)
                    record["doc_id"] = row_id
                    matches = all(record.get(key) == value for key, value in kwargs.items())
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
                cursor = conn.execute(f"SELECT id, data FROM {self.table_name}")  # nosec B608 - table_name is controlled

                for row_id, json_data in cursor:
                    record = json.loads(json_data)
                    record["doc_id"] = row_id
                    if query_func(record):
                        removed_ids.append(row_id)

                if removed_ids:
                    placeholders = ",".join(["?" for _ in removed_ids])
                    conn.execute(
                        f"DELETE FROM {self.table_name} WHERE id IN ({placeholders})",  # nosec B608
                        removed_ids,
                    )

            return removed_ids


class Database(DatabaseMigrationsMixin, TinyDBMigrationMixin):
    """SQLite database wrapper with TinyDB-like interface."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._connections: set[sqlite3.Connection] = set()
        self._lock = threading.Lock()
        self._init_database()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _init_database(self):
        """Initialize the database with required tables."""
        with self.get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=10000")
            conn.execute("PRAGMA temp_store=MEMORY")

            self._ensure_schema_version_table(conn)
            self._apply_migrations(conn)

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

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_matches_data
                ON matches(json_extract(data, '$.ado_id'))
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pr_matches_data
                ON pr_matches(json_extract(data, '$.pr_id'))
            """)

    @contextmanager
    def get_connection(self):
        """Get a thread-local database connection."""
        if not hasattr(self._local, "connection"):
            self._local.connection = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
            self._local.connection.row_factory = sqlite3.Row

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
        seen = set()
        duplicate_keys = set()
        duplicates = []
        project_entries_by_name: Dict[str, List[str]] = {}
        for project in projects_data:
            key = (project["adoProjectName"], project["adoTeamName"])
            if key in seen and key not in duplicate_keys:
                duplicates.append(f"{project['adoProjectName']} (Team: {project['adoTeamName']})")
                duplicate_keys.add(key)
            seen.add(key)
            project_entries_by_name.setdefault(project["adoProjectName"], []).append(
                f"{project['adoProjectName']} (Team: {project['adoTeamName']})"
            )

        if duplicates:
            error_msg = f"Duplicate project configuration found in projects.json for: {', '.join(duplicates)}"
            _LOGGER.error(
                "Duplicate project configuration found in projects.json for: %s",
                ", ".join(d.replace("\n", "\\n").replace("\r", "\\r") for d in duplicates),
            )
            raise ValueError(error_msg)

        with self.get_connection() as conn:
            conn.execute("DELETE FROM projects")

            for project in projects_data:
                try:
                    conn.execute(
                        """
                        INSERT INTO projects (ado_project_name, ado_team_name, asana_project_name)
                        VALUES (?, ?, ?)
                    """,
                        (project["adoProjectName"], project["adoTeamName"], project["asanaProjectName"]),
                    )
                except sqlite3.IntegrityError as exc:
                    if not self._is_legacy_project_name_unique_constraint(conn, exc):
                        raise

                    conflicting_projects = project_entries_by_name.get(project["adoProjectName"], [])
                    project_list = ", ".join(conflicting_projects) or project["adoProjectName"]
                    raise ValueError(
                        "Duplicate ADO project name found while syncing projects.json for "
                        f"{project_list}. The database still appears to use the legacy "
                        "single-project unique constraint on ado_project_name."
                    ) from exc

            _LOGGER.info("Synced %d projects to database", len(projects_data))

    def _is_legacy_project_name_unique_constraint(self, conn: sqlite3.Connection, exc: sqlite3.IntegrityError) -> bool:
        """Return True when the database still uses the old unique constraint on ado_project_name."""
        if getattr(exc, "sqlite_errorcode", None) != sqlite3.SQLITE_CONSTRAINT_UNIQUE:
            return False

        cursor = conn.execute("PRAGMA index_list(projects)")
        for index in cursor.fetchall():
            if not index["unique"]:
                continue

            index_name = index["name"]
            index_columns = conn.execute(f"PRAGMA index_info('{index_name}')").fetchall()
            column_names = [column["name"] for column in index_columns]
            if column_names == ["ado_project_name"]:
                return True

        return False

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
                projects.append(
                    {
                        "adoProjectName": row[0],
                        "adoTeamName": row[1],
                        "asanaProjectName": row[2],
                    }
                )

            return projects

    def close(self):
        """Close all database connections and clean up WAL files."""
        with self._lock:
            connections_to_close = list(self._connections)
            self._connections.clear()

        for conn in connections_to_close:
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.close()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _LOGGER.warning("Error closing database connection: %s", exc)

        if hasattr(self._local, "connection"):
            try:
                delattr(self._local, "connection")
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _LOGGER.warning("Error cleaning up thread-local connection: %s", exc)

        _LOGGER.debug("All database connections closed")
