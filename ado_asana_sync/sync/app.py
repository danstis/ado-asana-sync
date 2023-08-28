import os
import asana
from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
from tinydb import TinyDB


class App:
    """
    Represents an application that connects to Azure DevOps (ADO) and Asana, and sets up a TinyDB database.

    Args:
        ado_pat (str, optional): ADO Personal Access Token. Defaults to value retrieved from environment variable "ADO_PAT".
        ado_url (str, optional): ADO URL. Defaults to value retrieved from environment variable "ADO_URL".
        asana_token (str, optional): Asana access token. Defaults to value retrieved from environment variable "ASANA_TOKEN".

    Attributes:
        ado_pat (str): ADO Personal Access Token.
        ado_url (str): ADO URL.
        asana_token (str): Asana access token.
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
        ado_pat=os.environ.get("ADO_PAT"),
        ado_url=os.environ.get("ADO_URL"),
        asana_token=os.environ.get("ASANA_TOKEN"),
    ) -> None:
        """
        Initializes the App object with the provided ADO PAT, ADO URL, and Asana token.

        Args:
            ado_pat (str, optional): ADO Personal Access Token. Defaults to value retrieved from environment variable "ADO_PAT".
            ado_url (str, optional): ADO URL. Defaults to value retrieved from environment variable "ADO_URL".
            asana_token (str, optional): Asana access token. Defaults to value retrieved from environment variable "ASANA_TOKEN".
        """
        self.ado_pat = ado_pat
        self.ado_url = ado_url
        self.asana_token = asana_token
        self.ado_core_client = None
        self.ado_work_client = None
        self.ado_wit_client = None
        self.asana_client = None
        self.asana_page_size = 100

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
