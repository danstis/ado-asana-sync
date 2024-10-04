import unittest
from unittest.mock import MagicMock

from azure.devops.v7_0.work_item_tracking.models import WorkItem

from ado_asana_sync.sync.sync import (
    ADOAssignedUser,
    get_task_user,
    matching_user,
    get_asana_task_by_name,
)
from ado_asana_sync.sync.task_item import TaskItem


class TestTaskItem(unittest.TestCase):
    def setUp(self) -> None:
        self.test_item = TaskItem(
            ado_id=123,
            ado_rev=3,
            title="Test Title",
            item_type="User Story",
            url="https://testurl.example",
        )

    def test_asana_notes_link(self):
        result = self.test_item.asana_notes_link

        # Assert that the output is as expected
        self.assertEqual(
            result, '<a href="https://testurl.example">User Story 123</a>: Test Title'
        )

    # Tests that the asana_title returns the correct formatted title when all parameters are provided
    def test_asana_title_with_all_parameters(self):
        # Create a work_item object with all parameters provided
        work_item_obj = TaskItem(
            ado_id=1,
            ado_rev=1,
            title="Test Title",
            item_type="Task",
            url="https://example.com",
            assigned_to="John Doe",
            created_date="2021-01-01",
            updated_date="2021-12-31",
        )

        # Assert that the asana_title returns the correct formatted title
        self.assertEqual(work_item_obj.asana_title, "Task 1: Test Title")

    # Tests that the asana_title returns the correct formatted title when only mandatory parameters are provided
    def test_asana_title_with_mandatory_parameters(self):
        # Create a work_item object with only mandatory parameters provided
        work_item_obj = TaskItem(
            ado_id=1,
            ado_rev=42,
            title="Test Title",
            item_type="Task",
            url="https://example.com",
        )

        # Assert that the asana_title returns the correct formatted title
        self.assertEqual(work_item_obj.asana_title, "Task 1: Test Title")

    # Tests that the asana_title returns the correct formatted title when all parameters are provided with empty values
    def test_asana_title_with_empty_values(self):
        # Create a work_item object with all parameters provided as empty values
        work_item_obj = TaskItem(
            ado_id=None, ado_rev=None, title="", item_type="", url=""
        )

        # Assert that the asana_title returns the correct formatted title
        self.assertEqual(work_item_obj.asana_title, " None: ")

    # Tests that the asana_title returns the correct formatted title when all parameters are provided with invalid values
    def test_asana_title_with_invalid_values(self):
        # Create a work_item object with all parameters provided with invalid values
        work_item_obj = TaskItem(
            ado_id="invalid",
            ado_rev="invalid",
            title=123,
            item_type=True,
            url="https://example.com",
        )

        # Assert that the asana_title returns the correct formatted title
        self.assertEqual(work_item_obj.asana_title, "True invalid: 123")


class TestGetTaskUserEmail(unittest.TestCase):
    # Tests that the function returns the email address of the user assigned to the work item when the System.AssignedTo field has a uniqueName
    def test_assigned_user_with_uniqueName(self):
        task = WorkItem()
        task.fields = {
            "System.AssignedTo": {
                "uniqueName": "john.doe@example.com",
                "displayName": "John Doe",
            }
        }
        ado_user = ADOAssignedUser(
            display_name="John Doe", email="john.doe@example.com"
        )
        result = get_task_user(task)
        self.assertEqual(result, ado_user)

    # Tests that the function returns None when the System.AssignedTo field is not present in the work item
    def test_no_assigned_user(self):
        task = WorkItem()
        task.fields = {}
        result = get_task_user(task)
        self.assertIsNone(result)

    # Tests that the function returns None when the System.AssignedTo field is present but does not have a uniqueName field
    def test_missing_uniqueName(self):
        task = WorkItem()
        task.fields = {"System.AssignedTo": {}}
        result = get_task_user(task)
        self.assertIsNone(result)

    # Tests that the function returns the email address even if the uniqueName field in the System.AssignedTo field is not a valid email address
    def test_invalid_email_address(self):
        task = WorkItem()
        task.fields = {
            "System.AssignedTo": {
                "uniqueName": "john.doe",
                "displayName": "John Doe",
            }
        }
        ado_user = ADOAssignedUser(display_name="John Doe", email="john.doe")
        result = get_task_user(task)
        self.assertEqual(result, ado_user)

    # Tests that the function returns None when the System.AssignedTo field is present but is None
    def test_assigned_user_is_None(self):
        task = WorkItem()
        task.fields = {"System.AssignedTo": None}
        result = get_task_user(task)
        self.assertIsNone(result)


class TestMatchingUser(unittest.TestCase):
    # Tests that matching_user returns the matching user when the email exists in the user_list.
    def test_matching_user_matching_email_exists(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
            {"email": "user2@example.com", "name": "User 2"},
            {"email": "user3@example.com", "name": "User 3"},
        ]
        ado_user = ADOAssignedUser(display_name="User Two", email="user2@example.com")

        result = matching_user(user_list, ado_user)

        self.assertEqual(result, {"email": "user2@example.com", "name": "User 2"})

    # Tests that matching_user returns the matching user when the display name exists in the user_list.
    def test_matching_user_matching_display_name_exists(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
            {"email": "user2@example.com", "name": "User 2"},
            {"email": "user3@example.com", "name": "User 3"},
        ]
        ado_user = ADOAssignedUser(display_name="User 2", email="user2@example.co.uk")

        result = matching_user(user_list, ado_user)

        self.assertEqual(result, {"email": "user2@example.com", "name": "User 2"})

    # Tests that matching_user returns None when the email does not exist in the user_list.
    def test_matching_user_matching_email_does_not_exist(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
            {"email": "user2@example.com", "name": "User 2"},
            {"email": "user3@example.com", "name": "User 3"},
        ]
        ado_user = ADOAssignedUser(display_name="User 4", email="user4@example.com")

        result = matching_user(user_list, ado_user)

        self.assertIsNone(result)

    # Tests that matching_user returns None when the user_list is empty.
    def test_matching_user_user_list_empty(self):
        user_list = []
        ado_user = ADOAssignedUser(display_name="User 1", email="user1@example.com")

        result = matching_user(user_list, ado_user)

        self.assertIsNone(result)

    # Tests that matching_user returns None when the email is an empty string.
    def test_matching_user_email_empty(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
            {"email": "user2@example.com", "name": "User 2"},
            {"email": "user3@example.com", "name": "User 3"},
        ]
        ado_user = ADOAssignedUser(display_name="", email="")

        result = matching_user(user_list, ado_user)

        self.assertIsNone(result)

    # Tests that matching_user returns the user when the user_list contains only one user and the email matches that user's email.
    def test_matching_user_user_list_contains_one_user_email_matches(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
        ]
        ado_user = ADOAssignedUser(display_name="User 1", email="user1@example.com")

        result = matching_user(user_list, ado_user)

        self.assertEqual(result, {"email": "user1@example.com", "name": "User 1"})

    # Tests that matching_user returns None when the user_list contains only one user and the email does not match that user's email.
    def test_matching_user_user_list_contains_one_user_email_does_not_match(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
        ]
        ado_user = ADOAssignedUser(display_name="User 2", email="user2@example.com")

        result = matching_user(user_list, ado_user)

        self.assertIsNone(result)

    # Tests that matching_user returns None when the ado_user is None.
    def test_matching_user_ado_user_none(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
            {"email": "user2@example.com", "name": "User 2"},
            {"email": "user3@example.com", "name": "User 3"},
        ]
        ado_user = None

        result = matching_user(user_list, ado_user)

        self.assertIsNone(result)


class TestGetAsanaTaskByName(unittest.TestCase):
    def test_task_found(self):
        """
        Test case for verifying that a task can be found by name.
        """

        task_list = [
            {"name": "Task 1", "gid": "1"},
            {"name": "Task 2", "gid": "2"},
            {"name": "Task 3", "gid": "3"},
        ]

        # Call the function being tested
        result = get_asana_task_by_name(task_list, "Task 1")

        # Assert that the result is the task dictionary
        self.assertEqual(result, {"name": "Task 1", "gid": "1"})

    def test_task_not_found(self):
        """
        Test case for the scenario where the task is not found in the task list.
        """

        task_list = [{"name": "Task 1"}]

        # Call the function being tested
        result = get_asana_task_by_name(task_list, "Task 2")

        # Assert that the result is None
        self.assertIsNone(result)


class TestMatchingUser(unittest.TestCase):
    # Tests that matching_user returns the matching user when the email exists in the user_list.
    def test_matching_user_matching_email_exists(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
            {"email": "user2@example.com", "name": "User 2"},
            {"email": "user3@example.com", "name": "User 3"},
        ]
        ado_user = ADOAssignedUser(display_name="User Two", email="user2@example.com")

        result = matching_user(user_list, ado_user)

        self.assertEqual(result, {"email": "user2@example.com", "name": "User 2"})

    # Tests that matching_user returns the matching user when the display name exists in the user_list.
    def test_matching_user_matching_display_name_exists(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
            {"email": "user2@example.com", "name": "User 2"},
            {"email": "user3@example.com", "name": "User 3"},
        ]
        ado_user = ADOAssignedUser(display_name="User 2", email="user2@example.co.uk")

        result = matching_user(user_list, ado_user)

        self.assertEqual(result, {"email": "user2@example.com", "name": "User 2"})

    # Tests that matching_user returns the matching user when the email exists in another case in the user_list.
    def test_matching_user_matching_email_exists_other_case(self):
        user_list = [
            {"email": "USER1@EXAMPLE.COM", "name": "USER 1"},
            {"email": "USER2@EXAMPLE.COM", "name": "USER 2"},
            {"email": "USER3@EXAMPLE.COM", "name": "USER 3"},
        ]
        ado_user = ADOAssignedUser(display_name="User Two", email="user2@example.com")

        result = matching_user(user_list, ado_user)

        self.assertEqual(result, {"email": "USER2@EXAMPLE.COM", "name": "USER 2"})

    # Tests that matching_user returns the matching user when the display name exists in another case in the user_list.
    def test_matching_user_matching_display_name_exists_other_case(self):
        user_list = [
            {"email": "USER1@EXAMPLE.COM", "name": "USER 1"},
            {"email": "USER2@EXAMPLE.COM", "name": "USER 2"},
            {"email": "USER3@EXAMPLE.COM", "name": "USER 3"},
        ]
        ado_user = ADOAssignedUser(display_name="User 2", email="user2@example.co.uk")

        result = matching_user(user_list, ado_user)

        self.assertEqual(result, {"email": "USER2@EXAMPLE.COM", "name": "USER 2"})

    # Tests that matching_user returns None when the email does not exist in the user_list.
    def test_matching_user_matching_email_does_not_exist(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
            {"email": "user2@example.com", "name": "User 2"},
            {"email": "user3@example.com", "name": "User 3"},
        ]
        ado_user = ADOAssignedUser(display_name="User 4", email="user4@example.com")

        result = matching_user(user_list, ado_user)

        self.assertIsNone(result)

    # Tests that matching_user returns None when the user_list is empty.
    def test_matching_user_user_list_empty(self):
        user_list = []
        ado_user = ADOAssignedUser(display_name="User 1", email="user1@example.com")

        result = matching_user(user_list, ado_user)

        self.assertIsNone(result)

    # Tests that matching_user returns None when the email is an empty string.
    def test_matching_user_email_empty(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
            {"email": "user2@example.com", "name": "User 2"},
            {"email": "user3@example.com", "name": "User 3"},
        ]
        ado_user = ADOAssignedUser(display_name="", email="")

        result = matching_user(user_list, ado_user)

        self.assertIsNone(result)

    # Tests that matching_user returns the user when the user_list contains only one user and the email matches that user's email.
    def test_matching_user_user_list_contains_one_user_email_matches(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
        ]
        ado_user = ADOAssignedUser(display_name="User 1", email="user1@example.com")

        result = matching_user(user_list, ado_user)

        self.assertEqual(result, {"email": "user1@example.com", "name": "User 1"})

    # Tests that matching_user returns None when the user_list contains only one user and the email does not match that user's email.
    def test_matching_user_user_list_contains_one_user_email_does_not_match(
        self,
    ):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
        ]
        ado_user = ADOAssignedUser(display_name="User 2", email="user2@example.com")

        result = matching_user(user_list, ado_user)

        self.assertIsNone(result)

    # Tests that matching_user returns None when the ado_user is None.
    def test_matching_user_ado_user_none(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
            {"email": "user2@example.com", "name": "User 2"},
            {"email": "user3@example.com", "name": "User 3"},
        ]
        ado_user = None

        result = matching_user(user_list, ado_user)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
