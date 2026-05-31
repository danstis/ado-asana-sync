from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPI_SIMPLE_INDEX = "https://pypi.org/simple"


class TestUvSecurityConfig(unittest.TestCase):
    def test_pyproject_explicitly_uses_https_default_index(self) -> None:
        pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        indexes = pyproject["tool"]["uv"]["index"]

        self.assertIn(
            {
                "name": "pypi",
                "url": PYPI_SIMPLE_INDEX,
                "default": True,
            },
            indexes,
        )

    def test_dockerfile_sets_https_index_for_uv(self) -> None:
        dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn(f"UV_DEFAULT_INDEX={PYPI_SIMPLE_INDEX}", dockerfile)

    def test_ci_workflows_set_https_index_for_uv(self) -> None:
        workflow_paths = [
            REPO_ROOT / ".github" / "workflows" / "build.yml",
            REPO_ROOT / ".github" / "workflows" / "release.yml",
        ]

        for workflow_path in workflow_paths:
            with self.subTest(workflow=workflow_path.name):
                workflow = workflow_path.read_text(encoding="utf-8")
                self.assertIn(f"UV_DEFAULT_INDEX: {PYPI_SIMPLE_INDEX}", workflow)
