import unittest
from ado_asana_sync.sync.sync import work_item


class TestWorkItem(unittest.TestCase):
    def setUp(self) -> None:
        self.test_item = work_item(
            ado_id=123,
            title="Test Title",
            type="User Story",
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

    def test_asana_title(self):
        # Call the asana_notes_link method
        result = self.test_item.asana_title()

        # Assert that the output is as expected
        self.assertEqual(result, "User Story 123: Test Title")


if __name__ == "__main__":
    unittest.main()
