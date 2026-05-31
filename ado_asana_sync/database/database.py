"""Backward-compatible database module exports."""

from .connection import Database, DatabaseTable
from .migrations import CURRENT_SCHEMA_VERSION

__all__ = ["Database", "DatabaseTable", "CURRENT_SCHEMA_VERSION"]
