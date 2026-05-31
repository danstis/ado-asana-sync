"""Dry-run tracking helpers for sync operations."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)


@dataclass
class DryRunReport:
    task_creates: list[dict[str, int | str]] = field(default_factory=list)
    task_updates: list[dict[str, int | str]] = field(default_factory=list)
    task_closes: list[dict[str, int | str]] = field(default_factory=list)
    pr_creates: list[dict[str, int | str]] = field(default_factory=list)
    pr_updates: list[dict[str, int | str]] = field(default_factory=list)
    pr_closes: list[dict[str, int | str]] = field(default_factory=list)

    @property
    def task_create_ids(self) -> list[int]:
        return [int(item["ado_id"]) for item in self.task_creates]

    @property
    def task_update_ids(self) -> list[int]:
        return [int(item["ado_id"]) for item in self.task_updates]

    @property
    def task_close_ids(self) -> list[int]:
        return [int(item["ado_id"]) for item in self.task_closes]

    @property
    def pr_create_ids(self) -> list[int]:
        return [int(item["ado_pr_id"]) for item in self.pr_creates]

    @property
    def pr_update_ids(self) -> list[int]:
        return [int(item["ado_pr_id"]) for item in self.pr_updates]

    @property
    def pr_close_ids(self) -> list[int]:
        return [int(item["ado_pr_id"]) for item in self.pr_closes]

    def record_task_create(self, ado_id: int, title: str) -> None:
        self.task_creates.append({"ado_id": ado_id, "title": title})

    def record_task_update(self, ado_id: int, title: str) -> None:
        self.task_updates.append({"ado_id": ado_id, "title": title})

    def record_task_close(self, ado_id: int, title: str) -> None:
        self.task_closes.append({"ado_id": ado_id, "title": title})

    def record_pr_create(self, ado_pr_id: int, title: str) -> None:
        self.pr_creates.append({"ado_pr_id": ado_pr_id, "title": title})

    def record_pr_update(self, ado_pr_id: int, title: str) -> None:
        self.pr_updates.append({"ado_pr_id": ado_pr_id, "title": title})

    def record_pr_close(self, ado_pr_id: int, title: str) -> None:
        self.pr_closes.append({"ado_pr_id": ado_pr_id, "title": title})

    def log_summary(self) -> None:
        _LOGGER.info(
            "Dry-run summary: tasks create=%d update=%d close=%d ids=%s/%s/%s",
            len(self.task_creates),
            len(self.task_updates),
            len(self.task_closes),
            self.task_create_ids,
            self.task_update_ids,
            self.task_close_ids,
        )
        _LOGGER.info(
            "Dry-run summary: pull_requests create=%d update=%d close=%d ids=%s/%s/%s",
            len(self.pr_creates),
            len(self.pr_updates),
            len(self.pr_closes),
            self.pr_create_ids,
            self.pr_update_ids,
            self.pr_close_ids,
        )
