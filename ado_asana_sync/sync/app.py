"""
This module contains the App class which represents an application that connects to Azure DevOps (ADO) and Asana, and sets up
a TinyDB database.

Classes:
    App: Represents an application that connects to Azure DevOps (ADO) and Asana, and sets up a TinyDB database.
"""

import json
import logging
import os
import threading
from typing import Optional

import asana  # type: ignore
from azure.devops.connection import Connection  # type: ignore
from azure.monitor.opentelemetry import configure_azure_monitor
from msrest.authentication import BasicAuthentication

from ado_asana_sync.database import Database, DatabaseTable

# _LOGGER is the logging instance for this file.
_LOGGER = logging.getLogger(__name__)
# ASANA_PAGE_SIZE contains the default value for the page size to send to the Asana API.
ASANA_PAGE_SIZE = 100
# ASANA_TAG_NAME defined the name of the tag to add to synced items.
ASANA_TAG_NAME = os.environ.get("SYNCED_TAG_NAME", "synced")
# SLEEP_TIME defines the sleep time between sync tasks in seconds.
SLEEP_TIME = max(30, int(os.environ.get("SLEEP_TIME", 300)))


class App:
    """
    Represents an application that connects to Azure DevOps (ADO) and Asana, and sets up a TinyDB database.

    Args:
        ado_pat (str, optional): ADO Personal Access Token. Defaults to value retrieved from environment variable "ADO_PAT".
        ado_url (str, optional): ADO URL. Defaults to value retrieved from environment variable "ADO_URL".
        asana_token (str, optional): Asana access token. Defaults to value retrieved from environment variable "ASANA_TOKEN".
        asana_workspace_name (str, optional): Asana workspace name. Defaults to value retrieved from environment variable
         "ASANA_WORKSPACE_NAME".

    Attributes:
        ado_pat (str): ADO Personal Access Token.
        ado_url (str): ADO URL.
        asana_token (str): Asana access token.
        asana_workspace_name (str): Asana workspace name.
        ado_core_client: ADO core client.
        ado_work_client: ADO work client.
        ado_wit_client: ADO work item tracking client.
        ado_git_client: ADO git client.
        asana_client: Asana client.
        asana_page_size: The default page size for API calls, can be between 1-100.
        asana_tag_name: Defines the name of the Asana tag to add to synced items.
        asana_tag_gid: stores the tag id for the named asana tag in asana_tag_name.
        db: SQLite database.
        db_lock: Lock for the SQLite database (maintained for compatibility).
        matches: Database table named "matches".
        pr_matches: Database table named "pr_matches".
        config: Database table named "config".
    """

    def __init__(
        self,
        ado_pat: str = "",  # nosec B107
        ado_url: str = "",  # nosec B107
        asana_token: str = "",  # nosec B107
        asana_workspace_name: str = "",  # nosec B107
        applicationinsights_connection_string: Optional[str] = None,
    ) -> None:
        self.ado_pat = ado_pat or os.environ.get("ADO_PAT", "")
        self.ado_url = ado_url or os.environ.get("ADO_URL", "")
        self.asana_token = asana_token or os.environ.get("ASANA_TOKEN", "")
        self.asana_workspace_name = asana_workspace_name or os.environ.get("ASANA_WORKSPACE_NAME", "")
        self.applicationinsights_connection_string = applicationinsights_connection_string or os.environ.get(
            "APPLICATIONINSIGHTS_CONNECTION_STRING", None
        )
        if not self.applicationinsights_connection_string:
            os.environ["OTEL_LOGS_EXPORTER"] = "None"
            os.environ["OTEL_METRICS_EXPORTER"] = "None"
            os.environ["OTEL_TRACES_EXPORTER"] = "None"
        self.ado_core_client = None
        self.ado_wit_client = None
        self.ado_work_client = None
        self.ado_git_client = None
        self.asana_client = None
        self.asana_page_size = ASANA_PAGE_SIZE
        self.asana_tag_gid: Optional[str] = None
        self.asana_tag_name = ASANA_TAG_NAME
        self.db: Optional[Database] = None
        self.db_lock = threading.Lock()  # Maintained for compatibility, SQLite handles its own locking
        self.matches: Optional[DatabaseTable] = None
        self.pr_matches: Optional[DatabaseTable] = None
        self.config: Optional[DatabaseTable] = None
        self.sleep_time = SLEEP_TIME
        # Trace sampling configuration for Application Insights
        self.trace_sampling_percentage = float(os.environ.get("OTEL_TRACES_SAMPLER_ARG", "0.05"))  # Default 5%

        if not self.ado_pat:
            _LOGGER.fatal("ADO_PAT must be provided")
            raise ValueError("ADO_PAT must be provided")

        if not self.ado_url:
            _LOGGER.fatal("ADO_URL must be provided")
            raise ValueError("ADO_URL must be provided")

        if not self.asana_token:
            _LOGGER.fatal("ASANA_TOKEN must be provided")
            raise ValueError("ASANA_TOKEN must be provided")

        if not self.asana_workspace_name:
            _LOGGER.fatal("ASANA_WORKSPACE_NAME must be provided")
            raise ValueError("ASANA_WORKSPACE_NAME must be provided")

        _LOGGER.debug("Created new App instance")

    def connect(self) -> None:
        """
        Connects to ADO and Asana, and sets up the TinyDB database.
        """
        # Connect ADO.
        _LOGGER.debug("Connecting to Azure DevOps")
        ado_credentials = BasicAuthentication("", self.ado_pat)
        ado_connection = Connection(base_url=self.ado_url, creds=ado_credentials)
        self.ado_core_client = ado_connection.clients.get_core_client()
        self.ado_work_client = ado_connection.clients.get_work_client()
        self.ado_wit_client = ado_connection.clients.get_work_item_tracking_client()
        self.ado_git_client = ado_connection.clients.get_git_client()
        # Connect Asana.
        _LOGGER.debug("Connecting to Asana")
        asana_config = asana.Configuration()
        asana_config.access_token = self.asana_token
        self.asana_client = asana.ApiClient(asana_config)
        # Configure application insights with trace sampling to reduce telemetry volume
        configure_azure_monitor(
            connection_string=self.applicationinsights_connection_string,
            disable_offline_storage=True,
            sampling_ratio=self.trace_sampling_percentage,  # Reduce dependency trace volume
            instrumentation_options={
                "azure_sdk": {"enabled": True},
                "django": {"enabled": False},
                "fastapi": {"enabled": False},
                "flask": {"enabled": False},
                "psycopg2": {"enabled": False},
                "pymongo": {"enabled": False},
                "pymysql": {"enabled": False},
                "redis": {"enabled": False},
                "requests": {"enabled": True},
                "sqlalchemy": {"enabled": False},
                "urllib": {"enabled": True},
                "urllib3": {"enabled": True},
            },
        )
        _LOGGER.info("Azure Monitor configured with %.1f%% trace sampling", self.trace_sampling_percentage * 100)
        # Setup SQLite database.
        _LOGGER.debug("Opening local database")
        data_dir = os.path.join(os.path.dirname(__package__), "data")
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "appdata.db")
        appdata_json_path = os.path.join(data_dir, "appdata.json")

        # Initialize SQLite database
        self.db = Database(db_path)

        # Migrate from TinyDB if appdata.json exists
        if os.path.exists(appdata_json_path):
            _LOGGER.info("Found existing appdata.json, starting migration to SQLite")
            if self.db.migrate_from_tinydb(appdata_json_path):
                # Rename the old file after successful migration
                backup_path = appdata_json_path + ".migrated"
                os.rename(appdata_json_path, backup_path)
                _LOGGER.info("Migration successful, renamed %s to %s", appdata_json_path, backup_path)
            else:
                _LOGGER.error("Migration failed, keeping original appdata.json file")

        # Setup table interfaces
        self.matches = self.db.table("matches")
        self.pr_matches = self.db.table("pr_matches")
        self.config = self.db.table("config")

        # Sync projects from JSON on startup
        self._sync_projects_from_json()

        # Clean up any corrupted PR records from previous runs
        self._cleanup_corrupted_pr_data()

    def _sync_projects_from_json(self) -> None:
        """
        Sync projects from projects.json to the database.

        This method reads the projects.json file and updates the projects
        table in the database to match the JSON configuration.
        """
        try:
            projects_path = os.path.join(os.path.dirname(__package__), "data", "projects.json")

            if not os.path.exists(projects_path):
                _LOGGER.warning("projects.json not found at %s", projects_path)
                return

            with open(projects_path, "r", encoding="utf-8") as f:
                projects_data = json.load(f)

            if self.db:
                self.db.sync_projects_from_json(projects_data)
                _LOGGER.debug("Successfully synced %d projects from JSON", len(projects_data))

        except Exception as e:  # pylint: disable=broad-exception-caught
            _LOGGER.error("Failed to sync projects from JSON: %s", e)

    def _cleanup_corrupted_pr_data(self) -> None:
        """
        Clean up corrupted PR data during application startup.
        """
        try:
            # Import here to avoid circular import issues
            from .pull_request_item import PullRequestItem  # pylint: disable=import-outside-toplevel

            if self.pr_matches is not None:
                cleaned_count = PullRequestItem.cleanup_all_corrupted_records(self)
                if cleaned_count > 0:
                    _LOGGER.info("Startup cleanup removed %d corrupted PR records", cleaned_count)

        except Exception as e:  # pylint: disable=broad-exception-caught
            _LOGGER.error("Failed to cleanup corrupted PR data: %s", e)

    def close(self) -> None:
        """
        Clean up resources and close database connections.

        This ensures proper cleanup of SQLite WAL and SHM files.
        """
        if self.db:
            _LOGGER.debug("Closing database connections")
            self.db.close()
            self.db = None
