#!/usr/bin/env python3
"""Adversarial proof that estate_ci_health_audit.py's detection logic fires
both ways.

Per feedback_ask_what_calls_this.md ("prove teeth BOTH ways") and this
repo's own self-validate convention (see test_estate_drift_audit.py) -- a
detector never shown to detect anything, and never shown to stay quiet on a
clean case, is exactly as suspect as an unenforced rule.

This exercises `evaluate()` directly with synthetic repo-status data --
no `gh`, no network -- because `evaluate()` is a pure function over
already-fetched data by design (see the module's own docstring for why:
this repo's own convention already treats `gh`-calling checks as out of
scope for the hermetic suite, same as estate_drift_audit.py's
worktree-definition-of-done check).

Run: python3 tests/test_estate_ci_health_audit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from estate_ci_health_audit import evaluate  # noqa: E402


def fails(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def main() -> int:
    # Case 1: a real failure must produce a HIGH-severity finding naming the repo.
    bad = [{"repo": "holmes", "default_branch": "main", "conclusion": "failure",
            "workflow": "validate", "created_at": "2026-07-19T00:00:00Z"}]
    findings = evaluate(bad)
    if len(findings) != 1:
        fails(f"expected exactly 1 finding for a failing repo, got {len(findings)}")
    if findings[0]["severity"] != "high":
        fails(f"a real CI failure must be severity=high, got {findings[0]['severity']!r}")
    if findings[0]["repo"] != "holmes":
        fails("finding must name the actual failing repo")
    print("OK: a failing repo produces a high-severity finding")

    # Case 2: a clean repo must produce NOTHING -- this is the "stays quiet"
    # half of the proof, at least as important as detecting the bad case.
    good = [{"repo": "sociosphere", "default_branch": "main", "conclusion": "success",
             "workflow": "ci", "created_at": "2026-08-02T00:00:00Z"}]
    findings = evaluate(good)
    if findings:
        fails(f"a passing repo must produce zero findings, got {findings}")
    print("OK: a passing repo produces no findings")

    # Case 3: cancelled and no-runs must be soft notes, NOT high-severity --
    # this is the noise-control half of the design (see the incident log for
    # why a first draft that hard-failed on these was too noisy to trust).
    mixed = [
        {"repo": "prophet-core-catalog", "default_branch": "main", "conclusion": "cancelled"},
        {"repo": "api-contracts", "default_branch": "main", "conclusion": None},
    ]
    findings = evaluate(mixed)
    if len(findings) != 2:
        fails(f"expected 2 soft notes, got {len(findings)}")
    if any(f["severity"] == "high" for f in findings):
        fails("cancelled/no-runs must never be high-severity -- that's the noise this design exists to avoid")
    print("OK: cancelled and no-runs are soft notes, not hard failures")

    # Case 4: a mixed batch must isolate the real failure from the healthy
    # ones -- proves the scan doesn't cross-contaminate results between repos.
    batch = bad + good + mixed
    findings = evaluate(batch)
    high = [f for f in findings if f["severity"] == "high"]
    if len(high) != 1 or high[0]["repo"] != "holmes":
        fails(f"expected exactly 1 high-severity finding (holmes) in a mixed batch, got {high}")
    if len(findings) != 3:
        fails(f"expected 3 total findings (1 high + 2 notes) in a mixed batch, got {len(findings)}")
    print("OK: a mixed batch correctly isolates the real failure from healthy/noisy repos")

    print("\nAll estate_ci_health_audit.py adversarial checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
