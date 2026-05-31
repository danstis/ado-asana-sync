"""Legacy TinyDB migration helpers for the database package."""

import json
import logging
import os
import sqlite3
from contextlib import AbstractContextManager
from typing import Any, Dict, Protocol

_LOGGER = logging.getLogger(__name__)


class _ConnectionProvider(Protocol):
    """Protocol for database classes that expose a connection context manager."""

    def get_connection(self) -> AbstractContextManager[sqlite3.Connection]:
        """Return a managed SQLite connection."""

    def _migrate_table_data(self, conn, tinydb_data: Dict[str, Any], table_name: str) -> None:
        """Migrate a single TinyDB table into SQLite."""


class TinyDBMigrationMixin:
    """TinyDB import helpers for Database."""

    def migrate_from_tinydb(self: _ConnectionProvider, appdata_path: str) -> bool:
        """Migrate data from TinyDB JSON file to SQLite."""
        if not os.path.exists(appdata_path):
            _LOGGER.info("No appdata.json file found, skipping migration")
            return True

        try:
            _LOGGER.info("Starting migration from %s", appdata_path)

            with open(appdata_path, "r", encoding="utf-8") as file_handle:
                tinydb_data = json.load(file_handle)

            with self.get_connection() as conn:
                self._migrate_table_data(conn, tinydb_data, "matches")
                self._migrate_table_data(conn, tinydb_data, "pr_matches")
                self._migrate_table_data(conn, tinydb_data, "config")

            _LOGGER.info("Migration completed successfully")
            return True
        except Exception:  # pylint: disable=broad-exception-caught
            _LOGGER.exception("Migration failed")
            return False

    def _migrate_table_data(self, conn, tinydb_data: Dict[str, Any], table_name: str):
        """Helper method to migrate data for a specific table."""
        if table_name not in tinydb_data:
            return

        table_data = tinydb_data[table_name]
        for doc_id, record in table_data.items():
            if doc_id == "_default":
                continue

            clean_record = {key: value for key, value in record.items() if key != "doc_id"}
            json_data = json.dumps(clean_record, default=str)

            conn.execute(
                f"INSERT INTO {table_name} (data) VALUES (?)",  # nosec B608 - table_name is controlled
                (json_data,),
            )

        count = len(table_data) - 1 if "_default" in table_data else len(table_data)
        _LOGGER.info("Migrated %d %s records", count, table_name)
