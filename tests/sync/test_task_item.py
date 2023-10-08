import unittest
from unittest.mock import MagicMock

import pytest
import pytz

from ado_asana_sync.sync.task_item import TaskItem


class TestTaskItem(unittest.TestCase):
    def test_task_item_str(self):
        # Create a TaskItem object with a title
        task_item = TaskItem(
            1,
            1,
            "Test Task",
            "Bug",
            "https://dev.azure.com/ado_org/ado_project/_workitems/edit/1",
        )

        # Call the __str__ method and check the result
        assert str(task_item) == "Bug 1: Test Task"
