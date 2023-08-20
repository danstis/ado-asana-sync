import unittest
from ado_asana_sync.sync.sync import work_item


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
        # Call the asana_notes_link method
        result = self.test_item.asana_notes_link()

        # Assert that the output is as expected
        self.assertEqual(
            result, '<a href="https://testurl.example">User Story 123</a>: Test Title'
        )

    # Tests that the asana_title() method returns the correct formatted title when all parameters are provided
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

        # Assert that the asana_title() method returns the correct formatted title
        assert work_item_obj.asana_title() == "Task 1: Test Title"

    # Tests that the asana_title() method returns the correct formatted title when only mandatory parameters are provided
    def test_asana_title_with_mandatory_parameters(self):
        # Create a work_item object with only mandatory parameters provided
        work_item_obj = work_item(
            ado_id=1,
            title="Test Title",
            item_type="Task",
            status="In Progress",
            description="Test Description",
        )

        # Assert that the asana_title() method returns the correct formatted title
        assert work_item_obj.asana_title() == "Task 1: Test Title"

    # Tests that the asana_title() method returns the correct formatted title when all parameters are provided with empty values
    def test_asana_title_with_empty_values(self):
        # Create a work_item object with all parameters provided as empty values
        work_item_obj = work_item(
            ado_id=None, title="", item_type="", status="", description=""
        )

        # Assert that the asana_title() method returns the correct formatted title
        assert work_item_obj.asana_title() == " None: "

    # Tests that the asana_title() method returns the correct formatted title when all parameters are provided with invalid values
    def test_asana_title_with_invalid_values(self):
        # Create a work_item object with all parameters provided with invalid values
        work_item_obj = work_item(
            ado_id="invalid", title=123, item_type=True, status=None, description=456
        )

        # Assert that the asana_title() method returns the correct formatted title
        assert work_item_obj.asana_title() == "True invalid: 123"


if __name__ == "__main__":
    unittest.main()
