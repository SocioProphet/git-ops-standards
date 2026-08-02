#!/usr/bin/env python3
"""Estate CI health audit -- implements core/controls.yaml's
github-ci-health-current.

Read-only. Scans every non-fork, non-archived repo in an org and reports
which ones have a FAILING latest run on their default branch -- the class of
problem found on 2026-08-02 in holmes (red since 2026-07-19) and prophet-mesh
(red since 2026-07-30), neither caught until someone happened to be working
in that specific repo. See estate/incident-log/2026-08-02-silent-ci-failures.md.

The detection logic (`evaluate`) is a pure function over already-fetched
repo/run data so it can be tested hermetically, without hitting the GitHub
API in CI for this repo's own tests -- see tests/test_estate_ci_health_audit.py.
`main()` does the real `gh` calls and is the only part that needs network.

Deliberately narrow, on purpose (see the incident log for why a first draft
that also flagged `cancelled` and no-CI-runs as hard failures was too noisy):
  - `failure` on the default branch  -> HARD finding.
  - `cancelled`                      -> soft note (often a superseding push).
  - no CI runs at all                -> soft note (often a release-only
                                         trigger that's simply never fired).

Usage:
    python3 estate_ci_health_audit.py --org SocioProphet [--json]
    python3 estate_ci_health_audit.py --org SocioProphet --repos holmes,sociosphere
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any


def sh_json(args: list[str], timeout: int = 30) -> Any:
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def list_first_party_repos(org: str) -> list[str]:
    """Non-fork, non-archived repos only -- CI health of vendored upstream
    code isn't this estate's responsibility to watch or fix."""
    data = sh_json([
        "gh", "repo", "list", org, "--limit", "500",
        "--json", "name,isFork,isArchived",
    ], timeout=60)
    if not data:
        return []
    return sorted(
        r["name"] for r in data if not r["isFork"] and not r["isArchived"]
    )


def fetch_repo_status(org: str, repo: str) -> dict[str, Any]:
    """One repo's default branch + latest CI run conclusion. Best-effort:
    a repo with no workflows, or one `gh` can't reach, reports conclusion=None
    rather than raising -- the caller decides what None means."""
    slug = f"{org}/{repo}"
    view = sh_json(["gh", "repo", "view", slug, "--json", "defaultBranchRef"])
    default_branch = (view or {}).get("defaultBranchRef", {}).get("name")
    if not default_branch:
        return {"repo": repo, "default_branch": None, "conclusion": None}

    runs = sh_json([
        "gh", "run", "list", "--repo", slug, "--branch", default_branch,
        "--limit", "1", "--json", "conclusion,createdAt,name",
    ], timeout=30)
    if not runs:
        return {"repo": repo, "default_branch": default_branch, "conclusion": None}

    latest = runs[0]
    return {
        "repo": repo,
        "default_branch": default_branch,
        "conclusion": latest.get("conclusion"),
        "workflow": latest.get("name"),
        "created_at": latest.get("createdAt"),
    }


def evaluate(statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure: given already-fetched repo statuses, return findings.
    No network, no subprocess -- this is what tests/test_estate_ci_health_audit.py
    exercises hermetically."""
    findings = []
    for s in statuses:
        conclusion = s.get("conclusion")
        repo = s["repo"]
        if conclusion == "failure":
            findings.append({
                "control": "github-ci-health-current",
                "severity": "high",
                "repo": repo,
                "detail": (
                    f"latest run on '{s.get('default_branch')}' FAILED "
                    f"(workflow: {s.get('workflow')!r}, at {s.get('created_at')})"
                ),
            })
        elif conclusion == "cancelled":
            findings.append({
                "control": "github-ci-health-current",
                "severity": "note",
                "repo": repo,
                "detail": (
                    f"latest run on '{s.get('default_branch')}' was cancelled "
                    "-- often benign (superseding push), worth a glance if it recurs"
                ),
            })
        elif conclusion is None:
            findings.append({
                "control": "github-ci-health-current",
                "severity": "note",
                "repo": repo,
                "detail": "no CI runs found on the default branch (no workflows, or a release-only trigger that's never fired)",
            })
        # conclusion == "success" -> healthy, no finding.
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", default="SocioProphet")
    ap.add_argument("--repos", help="comma-separated repo names, skip org-wide listing")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    repos = args.repos.split(",") if args.repos else list_first_party_repos(args.org)
    if not repos:
        print(f"No first-party repos found for org '{args.org}' (or `gh` call failed).", file=sys.stderr)
        return 1

    statuses = [fetch_repo_status(args.org, r) for r in repos]
    findings = evaluate(statuses)
    hard_findings = [f for f in findings if f["severity"] == "high"]

    if args.json:
        print(json.dumps({"scanned": len(repos), "findings": findings}, indent=2))
    else:
        print(f"Scanned {len(repos)} first-party repos in {args.org}")
        print(f"Findings: {len(findings)} ({len(hard_findings)} high-severity)\n")
        for f in sorted(findings, key=lambda x: (x["severity"] != "high", x["repo"])):
            marker = "FAIL" if f["severity"] == "high" else "note"
            print(f"  [{marker}] {f['repo']}: {f['detail']}")

    return 1 if hard_findings else 0


if __name__ == "__main__":
    sys.exit(main())
