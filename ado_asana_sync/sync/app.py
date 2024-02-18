"""
This module contains the App class which represents an application that connects to Azure DevOps (ADO) and Asana, and sets up
a TinyDB database.

Classes:
    App: Represents an application that connects to Azure DevOps (ADO) and Asana, and sets up a TinyDB database.
"""

import logging
import os
from typing import Optional

import asana  # type: ignore
from azure.devops.connection import Connection  # type: ignore
from azure.monitor.opentelemetry import configure_azure_monitor
from msrest.authentication import BasicAuthentication
from tinydb import TinyDB

# _LOGGER is the logging instance for this file.
_LOGGER = logging.getLogger(__name__)
# ASANA_PAGE_SIZE contains the default value for the page size to send to the Asana API.
ASANA_PAGE_SIZE = 100
# ASANA_TAG_NAME defined the name of the tag to add to synced items.
ASANA_TAG_NAME = os.environ.get("SYNCED_TAG_NAME", "synced")
# SLEEP_TIME defines the sleep time between sync tasks in seconds.
SLEEP_TIME = min(1, int(os.environ.get("SLEEP_TIME", 300)))


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
        asana_client: Asana client.
        asana_page_size: The default page size for API calls, can be between 1-100.
        asana_tag_name: Defines the name of the Asana tag to add to synced items.
        asana_tag_gid: stores the tag id for the named asana tag in asana_tag_name.
        db: TinyDB database.
        matches: TinyDB table named "matches".
        config: TinyDB table named "config".
    """

    def __init__(
        self,
        ado_pat: str = "",
        ado_url: str = "",
        asana_token: str = "",
        asana_workspace_name: str = "",
        applicationinsights_connection_string: Optional[str] = None,
    ) -> None:
        self.ado_pat = ado_pat or os.environ.get("ADO_PAT", "")
        self.ado_url = ado_url or os.environ.get("ADO_URL", "")
        self.asana_token = asana_token or os.environ.get("ASANA_TOKEN", "")
        self.asana_workspace_name = asana_workspace_name or os.environ.get(
            "ASANA_WORKSPACE_NAME", ""
        )
        self.applicationinsights_connection_string = (
            applicationinsights_connection_string
            or os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", None)
        )
        if not self.applicationinsights_connection_string:
            os.environ["OTEL_LOGS_EXPORTER"] = "None"
            os.environ["OTEL_METRICS_EXPORTER"] = "None"
            os.environ["OTEL_TRACES_EXPORTER"] = "None"
        self.ado_core_client = None
        self.ado_wit_client = None
        self.ado_work_client = None
        self.asana_client = None
        self.asana_page_size = ASANA_PAGE_SIZE
        self.asana_tag_gid = None
        self.asana_tag_name = ASANA_TAG_NAME
        self.db = None
        self.matches = None
        self.config = None
        self.sleep_time = SLEEP_TIME

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
        # Connect Asana.
        _LOGGER.debug("Connecting to Asana")
        asana_config = asana.Configuration()
        asana_config.access_token = self.asana_token
        self.asana_client = asana.ApiClient(asana_config)
        # Configure application insights.
        configure_azure_monitor(
            connection_string=self.applicationinsights_connection_string,
        )
        # Setup tinydb.
        _LOGGER.debug("Opening local database")
        self.db = TinyDB(
            os.path.join(os.path.dirname(__package__), "data", "appdata.json")
        )
        self.matches = self.db.table("matches")
        self.config = self.db.table("config")
