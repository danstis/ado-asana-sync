import logging
import os
import asana
from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
from tinydb import TinyDB

_LOGGER = logging.getLogger(__name__)


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
        db: TinyDB database.
        matches: TinyDB table named "matches".
    """

    def __init__(
        self,
        ado_pat: str = None,
        ado_url: str = None,
        asana_token: str = None,
        asana_workspace_name: str = None,
    ) -> None:
        self.ado_pat = ado_pat or os.environ.get("ADO_PAT")
        self.ado_url = ado_url or os.environ.get("ADO_URL")
        self.asana_token = asana_token or os.environ.get("ASANA_TOKEN")
        self.asana_workspace_name = asana_workspace_name or os.environ.get(
            "ASANA_WORKSPACE_NAME"
        )
        self.ado_core_client = None
        self.ado_work_client = None
        self.ado_wit_client = None
        self.asana_client = None
        self.asana_page_size = 100

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

    def connect(self):
        """
        Connects to ADO and Asana, and sets up the TinyDB database.
        """
        # connect ADO
        ado_credentials = BasicAuthentication("", self.ado_pat)
        ado_connection = Connection(base_url=self.ado_url, creds=ado_credentials)
        self.ado_core_client = ado_connection.clients.get_core_client()
        self.ado_work_client = ado_connection.clients.get_work_client()
        self.ado_wit_client = ado_connection.clients.get_work_item_tracking_client()
        # connect Asana
        asana_config = asana.Configuration()
        asana_config.access_token = self.asana_token
        self.asana_client = asana.ApiClient(asana_config)
        # setup tinydb
        self.db = TinyDB(
            os.path.join(os.path.dirname(__package__), "data", "appdata.json")
        )
        self.matches = self.db.table("matches")
