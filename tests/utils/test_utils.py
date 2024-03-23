import unittest

from ado_asana_sync.utils.utils import safe_get


class TestSafeGet(unittest.TestCase):
    def test_safe_get_dict(self):
        """
        Test the safe_get function with a dictionary object as input.
        """
        obj = {"a": {"b": {"c": "value"}}}
        self.assertEqual(safe_get(obj, "a", "b", "c"), "value")

    def test_safe_get_object(self):
        """
        Testing safe_get with an object
        """

        class Obj:
            def __init__(self, value):
                self.value = value

        obj = Obj(5)
        self.assertEqual(safe_get(obj, "value"), 5)

    def test_safe_get_none(self):
        """
        Testing safe_get with None
        """
        obj = None
        self.assertIsNone(safe_get(obj, "a", "b", "c"))

    def test_safe_get_missing_key(self):
        """
        Testing safe_get with a missing key
        """
        obj = {"a": {"b": {"c": "value"}}}
        self.assertIsNone(safe_get(obj, "a", "b", "d"))
