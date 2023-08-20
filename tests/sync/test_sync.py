import unittest
from asana import UserResponse
from ado_asana_sync.sync.sync import work_item, get_task_user_email, matching_user
from azure.devops.v7_0.work_item_tracking.models import WorkItem


class TestWorkItem(unittest.TestCase):
    def setUp(self) -> None:
        self.test_item = work_item(
            ado_id=123,
            title="Test Title",
            item_type="User Story",
            status="Test Status",
            description="Test Description",
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
        work_item_obj = work_item(
            ado_id=1,
            title="Test Title",
            item_type="Task",
            status="In Progress",
            description="Test Description",
            url="https://example.com",
            assigned_to="John Doe",
            priority="High",
            due_date="2022-01-01",
            created_date="2021-01-01",
            updated_date="2021-12-31",
        )

        # Assert that the asana_title returns the correct formatted title
        assert work_item_obj.asana_title == "Task 1: Test Title"

    # Tests that the asana_title returns the correct formatted title when only mandatory parameters are provided
    def test_asana_title_with_mandatory_parameters(self):
        # Create a work_item object with only mandatory parameters provided
        work_item_obj = work_item(
            ado_id=1,
            title="Test Title",
            item_type="Task",
            status="In Progress",
            description="Test Description",
        )

        # Assert that the asana_title returns the correct formatted title
        assert work_item_obj.asana_title == "Task 1: Test Title"

    # Tests that the asana_title returns the correct formatted title when all parameters are provided with empty values
    def test_asana_title_with_empty_values(self):
        # Create a work_item object with all parameters provided as empty values
        work_item_obj = work_item(
            ado_id=None, title="", item_type="", status="", description=""
        )

        # Assert that the asana_title returns the correct formatted title
        assert work_item_obj.asana_title == " None: "

    # Tests that the asana_title returns the correct formatted title when all parameters are provided with invalid values
    def test_asana_title_with_invalid_values(self):
        # Create a work_item object with all parameters provided with invalid values
        work_item_obj = work_item(
            ado_id="invalid", title=123, item_type=True, status=None, description=456
        )

        # Assert that the asana_title returns the correct formatted title
        assert work_item_obj.asana_title == "True invalid: 123"


class TestGetTaskUserEmail(unittest.TestCase):
    # Tests that the function returns the email address of the user assigned to the work item when the System.AssignedTo field has a uniqueName
    def test_assigned_user_with_uniqueName(self):
        task = WorkItem()
        task.fields = {"System.AssignedTo": {"uniqueName": "john.doe@example.com"}}
        assert get_task_user_email(task) == "john.doe@example.com"

    # Tests that the function returns None when the System.AssignedTo field is not present in the work item
    def test_no_assigned_user(self):
        task = WorkItem()
        task.fields = {}
        assert get_task_user_email(task) == None

    # Tests that the function returns None when the System.AssignedTo field is present but does not have a uniqueName field
    def test_missing_uniqueName(self):
        task = WorkItem()
        task.fields = {"System.AssignedTo": {}}
        assert get_task_user_email(task) == None

    # Tests that the function returns the email address even if the uniqueName field in the System.AssignedTo field is not a valid email address
    def test_invalid_email_address(self):
        task = WorkItem()
        task.fields = {"System.AssignedTo": {"uniqueName": "john.doe"}}
        assert get_task_user_email(task) == "john.doe"

    # Tests that the function returns None when the System.AssignedTo field is present but is None
    def test_assigned_user_is_None(self):
        task = WorkItem()
        task.fields = {"System.AssignedTo": None}
        assert get_task_user_email(task) == None

    # Tests that the function returns None when the System.AssignedTo field is present but is an empty dictionary
    def test_assigned_user_is_empty_dict(self):
        task = WorkItem()
        task.fields = {"System.AssignedTo": {}}
        assert get_task_user_email(task) == None


class TestMatchingUser(unittest.TestCase):
    # Tests that matching_user returns the matching user when the email exists in the user_list.
    def test_matching_user_matching_email_exists(self):
        user_list = [
            UserResponse(email="user1@example.com", name="User 1"),
            UserResponse(email="user2@example.com", name="User 2"),
            UserResponse(email="user3@example.com", name="User 3"),
        ]
        email = "user2@example.com"

        result = matching_user(user_list, email)

        assert result == UserResponse(email="user2@example.com", name="User 2")

    # Tests that matching_user returns None when the email does not exist in the user_list.
    def test_matching_user_matching_email_does_not_exist(self):
        user_list = [
            UserResponse(email="user1@example.com", name="User 1"),
            UserResponse(email="user2@example.com", name="User 2"),
            UserResponse(email="user3@example.com", name="User 3"),
        ]
        email = "user4@example.com"

        result = matching_user(user_list, email)

        assert result is None

    # Tests that matching_user returns None when the user_list is empty.
    def test_matching_user_user_list_empty(self):
        user_list = []
        email = "user1@example.com"

        result = matching_user(user_list, email)

        assert result is None

    # Tests that matching_user returns None when the email is an empty string.
    def test_matching_user_email_empty(self):
        user_list = [
            UserResponse(email="user1@example.com", name="User 1"),
            UserResponse(email="user2@example.com", name="User 2"),
            UserResponse(email="user3@example.com", name="User 3"),
        ]
        email = ""

        result = matching_user(user_list, email)

        assert result is None

    # Tests that matching_user returns the user when the user_list contains only one user and the email matches that user's email.
    def test_matching_user_user_list_contains_one_user_email_matches(self):
        user_list = [
            UserResponse(email="user1@example.com", name="User 1"),
        ]
        email = "user1@example.com"

        result = matching_user(user_list, email)

        assert result == UserResponse(email="user1@example.com", name="User 1")

    # Tests that matching_user returns None when the user_list contains only one user and the email does not match that user's email.
    def test_matching_user_user_list_contains_one_user_email_does_not_match(self):
        user_list = [
            UserResponse(email="user1@example.com", name="User 1"),
        ]
        email = "user2@example.com"

        result = matching_user(user_list, email)

        assert result is None


if __name__ == "__main__":
    unittest.main()
