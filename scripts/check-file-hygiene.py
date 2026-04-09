#!/usr/bin/env python3
from __future__ import annotations

"""Check that all Identus repos contain the canonical hygiene config files.

Compares .gitattributes, .editorconfig, .markdownlint.yml, and .yamllint.yml
in every repo against the templates in the .github repo.

Requires: gh CLI authenticated with access to hyperledger-identus org.

Usage:
    python3 scripts/check-file-hygiene.py
"""

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

ORG = "hyperledger-identus"
TEMPLATE_REPO = ".github"
FILES = [".gitattributes", ".editorconfig", ".markdownlint.yml", ".yamllint.yml"]

# Repos to skip (the template repo itself)
SKIP_REPOS = {TEMPLATE_REPO}


def gh_api(endpoint: str) -> dict | list | None:
    """Call the GitHub API via gh CLI."""
    result = subprocess.run(
        ["gh", "api", endpoint, "--paginate"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def get_repo_names() -> list[str]:
    """Get all repo names in the org."""
    repos = gh_api(f"orgs/{ORG}/repos?per_page=100")
    if not repos:
        print("Error: could not fetch repos. Is `gh` authenticated?", file=sys.stderr)
        sys.exit(1)
    return sorted(r["name"] for r in repos if not r["archived"])


def get_file_content(repo: str, path: str, ref: str = "main") -> str | None:
    """Fetch a file's content from a repo via the GitHub API."""
    data = gh_api(f"repos/{ORG}/{repo}/contents/{path}?ref={ref}")
    if not data or "content" not in data:
        return None
    return base64.b64decode(data["content"]).decode("utf-8")


def load_template(path: str) -> str:
    """Load a template file from the local .github repo."""
    template_path = Path(__file__).resolve().parent.parent / path
    if not template_path.exists():
        print(f"Error: template {template_path} not found", file=sys.stderr)
        sys.exit(1)
    return template_path.read_text()


def main():
    parser = argparse.ArgumentParser(description="Check file hygiene across Identus repos")
    parser.parse_args()

    repos = get_repo_names()
    templates = {f: load_template(f) for f in FILES}

    # Status tracking
    results: dict[str, dict[str, str]] = {}

    for repo in repos:
        if repo in SKIP_REPOS:
            continue
        results[repo] = {}
        for filename in FILES:
            content = get_file_content(repo, filename)
            if content is None:
                results[repo][filename] = "MISSING"
            elif content == templates[filename]:
                results[repo][filename] = "OK"
            else:
                results[repo][filename] = "OUTDATED"

    # Print table
    col_width = max(len(r) for r in results) + 2
    file_widths = {f: max(len(f), 8) + 2 for f in FILES}

    header = "Repo".ljust(col_width) + "".join(f.ljust(file_widths[f]) for f in FILES)
    print(header)
    print("-" * len(header))

    all_ok = True
    for repo, statuses in results.items():
        row = repo.ljust(col_width)
        for filename in FILES:
            status = statuses[filename]
            if status != "OK":
                all_ok = False
            row += status.ljust(file_widths[filename])
        print(row)

    # Summary
    print()
    total = len(results) * len(FILES)
    ok_count = sum(1 for r in results.values() for s in r.values() if s == "OK")
    missing = sum(1 for r in results.values() for s in r.values() if s == "MISSING")
    outdated = sum(1 for r in results.values() for s in r.values() if s == "OUTDATED")
    print(f"Total: {ok_count}/{total} OK, {missing} missing, {outdated} outdated")

    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
