"""Cache for ADO group member resolution results.

Stores resolved ADOAssignedUser lists keyed by ADO group reviewer GUID.
Supports an optional persistent JSON backing file with a configurable TTL
(default 6 hours) so group membership does not need to be re-fetched on every
sync run. When no cache file is given the cache is in-memory only (for the
current process lifetime) with no TTL enforcement.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from .ado_parser import ADOAssignedUser

_LOGGER = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS: float = 6 * 3600  # 6 hours


class GroupMemberCache:
    """In-memory (and optionally persistent) cache for ADO group member lists.

    Key: reviewer.id  (ADO storage GUID, globally unique within ADO)
    Value: list of ADOAssignedUser resolved from the group's Graph API membership
    """

    def __init__(
        self,
        cache_file: Optional[str] = None,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        self._store: dict[str, dict] = {}
        self._cache_file = cache_file
        self._ttl_seconds = ttl_seconds
        if cache_file:
            self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, reviewer_id: str) -> Optional[List[ADOAssignedUser]]:
        """Return cached members for *reviewer_id* if present and not expired.

        Returns None when the entry is absent or has expired (entry is evicted).
        """
        entry = self._store.get(reviewer_id)
        if entry is None:
            return None
        if self._is_expired(entry):
            del self._store[reviewer_id]
            return None
        return [ADOAssignedUser(m["display_name"], m["email"]) for m in entry["members"]]

    def set(self, reviewer_id: str, members: List[ADOAssignedUser]) -> None:
        """Store *members* for *reviewer_id* and persist if a cache file is configured."""
        self._store[reviewer_id] = {
            "members": [{"display_name": m.display_name, "email": m.email} for m in members],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if self._cache_file:
            self._save()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_expired(self, entry: dict) -> bool:
        if self._ttl_seconds is None:
            return False
        try:
            updated_at = datetime.fromisoformat(entry["updated_at"])
            age = (datetime.now(timezone.utc) - updated_at).total_seconds()
            return age > self._ttl_seconds
        except (KeyError, ValueError):
            return True

    def _load(self) -> None:
        if not self._cache_file or not os.path.exists(self._cache_file):
            return
        try:
            with open(self._cache_file, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self._store = data
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _LOGGER.warning("Could not load group member cache from %s: %s", self._cache_file, exc)

    def _save(self) -> None:
        try:
            with open(self._cache_file, "w", encoding="utf-8") as fh:  # type: ignore[arg-type]
                json.dump(self._store, fh)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _LOGGER.warning("Could not save group member cache to %s: %s", self._cache_file, exc)
