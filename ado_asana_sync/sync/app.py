import os
import asana
from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication


class app:
    def __init__(
        self,
        ado_pat=os.environ.get("ADO_PAT"),
        ado_url=os.environ.get("ADO_URL"),
        asana_token=os.environ.get("ASANA_TOKEN"),
    ) -> None:
        self.ado_pat = ado_pat
        self.ado_url = ado_url
        self.asana_token = asana_token
        self.ado_core_client = None
        self.ado_work_client = None
        self.ado_wit_client = None
        self.asana_client = None

    def connect(self):
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
