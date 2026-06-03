"""Tests for GroupMemberCache."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from ado_asana_sync.sync.ado_parser import ADOAssignedUser
from ado_asana_sync.sync.group_member_cache import GroupMemberCache


def _alice() -> ADOAssignedUser:
    return ADOAssignedUser("Alice Smith", "alice@corp.com")


def _bob() -> ADOAssignedUser:
    return ADOAssignedUser("Bob Jones", "bob@corp.com")


class TestGroupMemberCacheInMemory(unittest.TestCase):
    def setUp(self):
        self.cache = GroupMemberCache()

    def test_get_missing_key_returns_none(self):
        self.assertIsNone(self.cache.get("unknown-id"))

    def test_set_then_get_returns_members(self):
        self.cache.set("group-1", [_alice()])
        result = self.cache.get("group-1")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].email, "alice@corp.com")

    def test_set_multiple_members(self):
        self.cache.set("group-2", [_alice(), _bob()])
        result = self.cache.get("group-2")
        self.assertEqual(len(result), 2)

    def test_no_ttl_entries_never_expire(self):
        self.cache.set("group-3", [_alice()])
        # Set a very old timestamp manually
        self.cache._store["group-3"]["updated_at"] = "2000-01-01T00:00:00+00:00"
        result = self.cache.get("group-3")
        self.assertIsNotNone(result)

    def test_ttl_expired_entry_returns_none(self):
        cache = GroupMemberCache(ttl_seconds=1)
        cache.set("group-ttl", [_alice()])
        # Manually back-date the entry
        cache._store["group-ttl"]["updated_at"] = "2000-01-01T00:00:00+00:00"
        self.assertIsNone(cache.get("group-ttl"))

    def test_ttl_fresh_entry_returned(self):
        cache = GroupMemberCache(ttl_seconds=3600)
        cache.set("group-fresh", [_bob()])
        result = cache.get("group-fresh")
        self.assertIsNotNone(result)
        self.assertEqual(result[0].email, "bob@corp.com")


class TestGroupMemberCachePersistence(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.cache_file = os.path.join(self.tmp_dir, "test_cache.json")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_set_persists_to_file(self):
        cache = GroupMemberCache(cache_file=self.cache_file)
        cache.set("group-persist", [_alice()])
        self.assertTrue(os.path.exists(self.cache_file))
        with open(self.cache_file, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertIn("group-persist", data)

    def test_second_instance_loads_from_file(self):
        cache1 = GroupMemberCache(cache_file=self.cache_file)
        cache1.set("group-cross-run", [_alice()])

        cache2 = GroupMemberCache(cache_file=self.cache_file)
        result = cache2.get("group-cross-run")
        self.assertIsNotNone(result)
        self.assertEqual(result[0].email, "alice@corp.com")

    def test_expired_entry_not_returned_by_new_instance(self):
        cache1 = GroupMemberCache(cache_file=self.cache_file, ttl_seconds=3600)
        cache1.set("group-old", [_alice()])
        # Manually expire the entry in the file
        with open(self.cache_file, encoding="utf-8") as fh:
            data = json.load(fh)
        data["group-old"]["updated_at"] = "2000-01-01T00:00:00+00:00"
        with open(self.cache_file, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

        cache2 = GroupMemberCache(cache_file=self.cache_file, ttl_seconds=3600)
        self.assertIsNone(cache2.get("group-old"))

    def test_missing_file_loads_empty_cache(self):
        cache = GroupMemberCache(cache_file=os.path.join(self.tmp_dir, "nonexistent.json"))
        self.assertIsNone(cache.get("any-id"))

    def test_corrupt_file_loads_empty_cache(self):
        with open(self.cache_file, "w", encoding="utf-8") as fh:
            fh.write("not valid json {{")
        cache = GroupMemberCache(cache_file=self.cache_file)
        self.assertIsNone(cache.get("any-id"))
