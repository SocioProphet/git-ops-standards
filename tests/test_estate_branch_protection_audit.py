#!/usr/bin/env python3
"""Adversarial proof that estate_branch_protection_audit.py's detection logic
fires both ways.

Per feedback_ask_what_calls_this.md ("prove teeth BOTH ways") and this repo's
self-validate convention (see test_estate_ci_health_audit.py): a detector never
shown to detect, and never shown to stay quiet on a clean case, is as suspect as
an unenforced rule. Exercises `evaluate()` (and the normalizers it calls)
directly with synthetic spec/live pairs -- no `gh`, no network.

Run: python3 tests/test_estate_branch_protection_audit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from estate_branch_protection_audit import evaluate  # noqa: E402


def fails(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


# A representative committed spec (PUT-body shape) and the MATCHING live
# protection (GET shape -- note the nested {enabled: ...}, deliberately
# different so the test also proves the two normalizers agree).
SPEC = {
    "required_status_checks": {"strict": True, "contexts": ["CI gate (fail-closed aggregate)"]},
    "enforce_admins": True,
    "required_pull_request_reviews": None,
    "required_linear_history": True,
    "allow_force_pushes": False,
    "allow_deletions": False,
    "required_conversation_resolution": True,
}
LIVE_MATCH = {
    "required_status_checks": {"strict": True, "contexts": ["CI gate (fail-closed aggregate)"]},
    "enforce_admins": {"enabled": True},
    "required_pull_request_reviews": None,
    "required_linear_history": {"enabled": True},
    "allow_force_pushes": {"enabled": False},
    "allow_deletions": {"enabled": False},
    "required_conversation_resolution": {"enabled": True},
}


def main() -> int:
    # Case 1: spec matches live EXACTLY (across the two different shapes) -> silent.
    f = evaluate([{"repo": "cybernetic-genesis", "default_branch": "main",
                   "spec": SPEC, "live_status": "ok", "live": LIVE_MATCH}])
    if f:
        fails(f"a repo whose live protection matches its spec must produce no findings, got {f}")
    print("OK: spec == live (across PUT/GET shapes) produces no findings")

    # Case 2: DRIFT (enforce_admins flipped off live) -> HIGH finding naming the field.
    live_drift = {**LIVE_MATCH, "enforce_admins": {"enabled": False}}
    f = evaluate([{"repo": "cybernetic-genesis", "default_branch": "main",
                   "spec": SPEC, "live_status": "ok", "live": live_drift}])
    if len(f) != 1 or f[0]["severity"] != "high":
        fails(f"drift must yield exactly one high finding, got {f}")
    if "enforce_admins" not in f[0]["detail"]:
        fails("drift finding must name the field that drifted")
    print("OK: live drifting from spec is a high-severity finding that names the field")

    # Case 3: spec declared but main UNPROTECTED -> HIGH (advisory gate).
    f = evaluate([{"repo": "cybernetic-genesis", "default_branch": "main",
                   "spec": SPEC, "live_status": "absent", "live": None}])
    if len(f) != 1 or f[0]["severity"] != "high":
        fails(f"declared-but-unprotected must be high, got {f}")
    print("OK: declared spec with no live protection is a high-severity finding")

    # Case 4: token can't read live protection -> soft NOTE, never high (noise control).
    f = evaluate([{"repo": "x", "default_branch": "main", "spec": SPEC,
                   "live_status": "forbidden", "live": None}])
    if len(f) != 1 or f[0]["severity"] != "note":
        fails(f"unreadable live protection must be a soft note, got {f}")
    print("OK: unverifiable (403) is a soft note, not a hard failure")

    # Case 5: NO committed spec + no protection -> repo hasn't opted in -> stay quiet.
    f = evaluate([{"repo": "some-scratch-repo", "default_branch": "main",
                   "spec": None, "live_status": "absent", "live": None}])
    if f:
        fails(f"a repo with no spec and no protection must be silent (opt-in), got {f}")
    print("OK: no spec + no protection is silent -- the check does not cry wolf")

    # Case 6: protected but NO committed spec -> soft note (codify it), not high.
    f = evaluate([{"repo": "legacy", "default_branch": "main",
                   "spec": None, "live_status": "ok", "live": LIVE_MATCH}])
    if len(f) != 1 or f[0]["severity"] != "note":
        fails(f"protected-but-undeclared must be a soft note, got {f}")
    print("OK: protected but undeclared is a soft note (codify it)")

    print("\nALL PASS: branch-protection audit fires on real drift and stays quiet when clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
