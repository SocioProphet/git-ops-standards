#!/usr/bin/env python3
"""Adversarial proof that estate_sovereign_governance_audit.py's detection logic fires both
ways, per this repo's self-validate convention (see test_estate_ci_health_audit.py). Exercises
`evaluate()` on synthetic substrate facts -- no `gh`, no network, no cluster.

Run: python3 tests/test_estate_sovereign_governance_audit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from estate_sovereign_governance_audit import evaluate  # noqa: E402


def fails(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


# A fully-healthy, fully-verified estate (all in-cluster facts known-good).
CLEAN = {
    "git": {"spec_present": True, "spec_schema_valid": True, "live_status": "ok", "live_matches": True},
    "registry": {"configmap_present": True, "retention_present": True, "login_wall": True,
                 "signing_policy_present": True, "signing_installed": True},
    "worktracking": {"external_jira_as_sor": False, "agora_deployed": True, "hellgraph_backed": True,
                     "prophet_workspace_integrated": True, "sociosphere_ci_integrated": True,
                     "graph_integrated": True},
}


def has(findings, control, sev):
    return [f for f in findings if f["control"] == control and f["severity"] == sev]


def main() -> int:
    # Case 0: a fully-healthy, fully-verified estate -> zero findings (the "stays quiet" half).
    if evaluate(CLEAN):
        fails(f"a clean, fully-verified estate must produce no findings, got {evaluate(CLEAN)}")
    print("OK: clean fully-verified estate produces no findings")

    # Case 1: no committed sovereign-git protection spec -> HIGH.
    f = evaluate({**CLEAN, "git": {**CLEAN["git"], "spec_present": False}})
    if not has(f, "sovereign-git-protection-declared", "high"):
        fails(f"missing sovereign-git protection spec must be high, got {f}")
    print("OK: absent sovereign-git protection spec is a high finding")

    # Case 2: signing policy present but NOT installed -> HIGH (declared != enforced).
    f = evaluate({**CLEAN, "registry": {**CLEAN["registry"], "signing_installed": False}})
    if not has(f, "sovereign-registry-policy-enforced", "high"):
        fails(f"present-but-not-installed signing must be high, got {f}")
    print("OK: signing policy declared-but-not-installed is a high finding")

    # Case 3: zot allows anonymous access -> HIGH.
    f = evaluate({**CLEAN, "registry": {**CLEAN["registry"], "login_wall": False}})
    if not has(f, "sovereign-registry-policy-enforced", "high"):
        fails(f"anonymous zot access must be high, got {f}")
    print("OK: zot without a login-wall is a high finding")

    # Case 4: external Jira as system of record -> HIGH.
    f = evaluate({**CLEAN, "worktracking": {**CLEAN["worktracking"], "external_jira_as_sor": True}})
    if not has(f, "sovereign-worktracking-native-integrated", "high"):
        fails(f"external-Jira-as-SoR must be high, got {f}")
    print("OK: external Jira as system of record is a high finding")

    # Case 5: agora deployed + HellGraph-backed but an integration is missing -> soft NOTE, not high.
    f = evaluate({**CLEAN, "worktracking": {**CLEAN["worktracking"], "sociosphere_ci_integrated": False}})
    notes = [x for x in f if x["control"] == "sovereign-worktracking-native-integrated"]
    if not notes or any(x["severity"] == "high" for x in notes):
        fails(f"a missing integration must be a soft note, not high, got {f}")
    print("OK: a missing agora integration is a soft note, not a hard failure")

    # Case 6: in-cluster facts UNKNOWN (running outside the cluster) -> soft notes, never high.
    outside = {
        "git": {"spec_present": True, "spec_schema_valid": True, "live_status": "unknown", "live_matches": None},
        # committed configmap present but embedded posture not parseable, controller state unknown:
        "registry": {"configmap_present": True, "retention_present": None, "login_wall": None,
                     "signing_policy_present": True, "signing_installed": None},
        "worktracking": CLEAN["worktracking"],
    }
    f = evaluate(outside)
    if any(x["severity"] == "high" for x in f):
        fails(f"unknown in-cluster facts must never produce a hard finding, got {f}")
    if not [x for x in f if x["severity"] == "note"]:
        fails("unknown in-cluster facts should surface soft notes")
    print("OK: unverifiable in-cluster facts are soft notes, never false hard failures")

    print("\nALL PASS: sovereign-governance audit fires on real gaps and stays quiet when clean/unverifiable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
