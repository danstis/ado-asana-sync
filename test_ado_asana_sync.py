import unittest
from ado_asana_sync import work_item

class TestWorkItem(unittest.TestCase):
    def test_asana_notes_link(self):
        # Create a work_item instance with dummy data
        item = work_item(
            ado_id=123,
            title="Test Title",
            type="Test Type",
            status="Test Status",
            description="Test Description",
            url="http://testurl.com"
        )
        
        # Call the asana_notes_link method
        result = item.asana_notes_link()
        
        # Assert that the output is as expected
        self.assertEqual(result, '<a href="http://testurl.com">Test Type 123</a>: Test Title')

if __name__ == "__main__":
    unittest.main()
