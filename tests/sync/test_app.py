import unittest
from unittest.mock import MagicMock

import pytest
import pytz

from ado_asana_sync.sync.sync import *


class TestApp(unittest.TestCase):
    # Tests that an App instance is created successfully with valid arguments
    def test_app_instance_created_successfully(self):
        app = App(
            ado_pat="ado_pat",
            ado_url="ado_url",
            asana_token="asana_token",
            asana_workspace_name="asana_workspace_name",
        )
        assert app.ado_pat == "ado_pat"
        assert app.ado_url == "ado_url"
        assert app.asana_token == "asana_token"
        assert app.asana_workspace_name == "asana_workspace_name"
        assert app.ado_core_client is None
        assert app.ado_work_client is None
        assert app.ado_wit_client is None
        assert app.ado_git_client is None
        assert app.asana_client is None
        assert app.asana_page_size == 100
        assert app.custom_fields_available is True

    # Tests that the Asana page size is set correctly
    def test_asana_page_size_set_correctly(self):
        app = App(
            ado_pat="ado_pat",
            ado_url="ado_url",
            asana_token="asana_token",
            asana_workspace_name="asana_workspace_name",
        )
        assert app.asana_page_size == 100
        app.asana_page_size = 50
        assert app.asana_page_size == 50
