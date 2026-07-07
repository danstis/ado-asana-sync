import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RENOVATE_CONFIG = REPO_ROOT / "renovate.json"
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
SHA_PIN_PATTERN = re.compile(r"uses:\s+[^\s@]+@[0-9a-f]{40}\b.*#\s*v\d")


def test_renovate_does_not_enable_github_action_digest_pinning() -> None:
    config = json.loads(RENOVATE_CONFIG.read_text())

    if "helpers:pinGitHubActionDigestsToSemver" in config["extends"]:
        raise AssertionError("Renovate must not enable GitHub Action digest pinning")

    if not any(
        rule.get("matchDepTypes") == ["action"] and rule.get("pinDigests") is False for rule in config.get("packageRules", [])
    ):
        raise AssertionError("Renovate must explicitly disable GitHub Action digest pinning")


def test_workflows_use_version_tags_for_github_actions() -> None:
    sha_pinned_refs = []

    for workflow_file in sorted(WORKFLOW_DIR.glob("*.yml")):
        for line_number, line in enumerate(workflow_file.read_text().splitlines(), start=1):
            if SHA_PIN_PATTERN.search(line):
                sha_pinned_refs.append(f"{workflow_file.name}:{line_number}")

    if sha_pinned_refs:
        refs = ", ".join(sha_pinned_refs)
        raise AssertionError(f"Expected semver-tagged action refs without SHAs, found: {refs}")
