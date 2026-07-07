import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RENOVATE_CONFIG = REPO_ROOT / "renovate.json"
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
SEMVER_COMMENTED_SHA_PIN_PATTERN = re.compile(r"uses:\s+[^\s@]+@[0-9a-f]{40}\b.*#\s*v\d")
SEMVER_TAG_PATTERN = re.compile(r"uses:\s+[^\s@]+@v\d+(?:\.\d+)*\b")


def test_renovate_enables_github_action_digest_pinning() -> None:
    config = json.loads(RENOVATE_CONFIG.read_text())

    if "helpers:pinGitHubActionDigests" not in config["extends"]:
        raise AssertionError("Renovate must enable GitHub Action digest pinning")

    if "helpers:pinGitHubActionDigestsToSemver" in config["extends"]:
        raise AssertionError("Renovate must not convert GitHub Action digests to semver tags")


def test_workflows_keep_semver_commented_actions_on_sha_pins() -> None:
    missing_sha_pins = []
    semver_tags = []

    for workflow_file in sorted(WORKFLOW_DIR.glob("*.yml")):
        for line_number, line in enumerate(workflow_file.read_text().splitlines(), start=1):
            if "# v" in line and "uses:" in line:
                if SEMVER_TAG_PATTERN.search(line):
                    semver_tags.append(f"{workflow_file.name}:{line_number}")
                elif not SEMVER_COMMENTED_SHA_PIN_PATTERN.search(line):
                    missing_sha_pins.append(f"{workflow_file.name}:{line_number}")

    if semver_tags:
        refs = ", ".join(semver_tags)
        raise AssertionError(f"Expected digest pins instead of semver tags, found: {refs}")

    if missing_sha_pins:
        refs = ", ".join(missing_sha_pins)
        raise AssertionError(f"Expected semver-commented action refs to stay on SHAs, found: {refs}")
