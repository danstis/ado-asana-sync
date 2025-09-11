#!/usr/bin/env python3
"""
Quality assurance commands for ado-asana-sync.
Cross-platform Python scripts to replace tox functionality.
"""

import concurrent.futures
import subprocess
import sys
from typing import List, Tuple


def run_command(cmd: List[str], description: str) -> Tuple[str, int]:
    """Run a command and return its output and exit code."""
    print(f"🔍 {description}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return description, result.returncode
    except Exception as e:
        print(f"❌ Error running {description}: {e}")
        return description, 1


def lint():
    """Run ruff linting."""
    result = subprocess.run(["ruff", "check", "."], check=False)
    sys.exit(result.returncode)


def format_code():
    """Format code with ruff."""
    result = subprocess.run(["ruff", "format", "."], check=False)
    sys.exit(result.returncode)


def format_check():
    """Check if code is properly formatted."""
    result = subprocess.run(["ruff", "format", "--check", "."], check=False)
    sys.exit(result.returncode)


def type_check():
    """Run mypy type checking."""
    result = subprocess.run(["mypy", "ado_asana_sync", "--ignore-missing-imports"], check=False)
    sys.exit(result.returncode)


def test():
    """Run pytest with coverage."""
    result = subprocess.run(["pytest", "--cov=.", "--cov-report=xml", "--cov-branch"], check=False)
    sys.exit(result.returncode)


def check_all():
    """Run all quality checks in parallel (like tox)."""
    print("🚀 Running all quality checks in parallel...")

    # Define all checks to run
    checks = [
        (["ruff", "check", "."], "Ruff linting"),
        (["ruff", "format", "--check", "."], "Ruff formatting check"),
        (["mypy", "ado_asana_sync", "--ignore-missing-imports"], "MyPy type checking"),
    ]

    # Run checks in parallel
    failed_checks = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(checks)) as executor:
        future_to_check = {executor.submit(run_command, cmd, desc): (cmd, desc) for cmd, desc in checks}

        for future in concurrent.futures.as_completed(future_to_check):
            cmd, description = future_to_check[future]
            try:
                desc, exit_code = future.result()
                if exit_code == 0:
                    print(f"✅ {desc} passed")
                else:
                    print(f"❌ {desc} failed")
                    failed_checks.append(desc)
            except Exception as exc:
                print(f"❌ {description} generated an exception: {exc}")
                failed_checks.append(description)

    # Summary
    if failed_checks:
        print(f"\n❌ {len(failed_checks)} check(s) failed:")
        for check in failed_checks:
            print(f"  - {check}")
        sys.exit(1)
    else:
        print("\n✅ All quality checks passed!")
        sys.exit(0)


if __name__ == "__main__":
    # Allow running individual functions from command line
    import sys

    if len(sys.argv) > 1:
        func_name = sys.argv[1]
        if func_name in globals() and callable(globals()[func_name]):
            globals()[func_name]()
        else:
            print(f"Unknown command: {func_name}")
            sys.exit(1)
    else:
        check_all()
