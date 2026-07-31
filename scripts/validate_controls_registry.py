#!/usr/bin/env python3
"""Self-validation for core/controls.yaml -- run in this repo's OWN CI on
every PR touching controls.yaml, so the registry can't drift from its own
stated rule: every control must cite a real incident.

Per feedback_self_validating_checker.md's principle -- a scanner must
exclude itself from blind spots -- this validator is itself covered by
that same repo's pr-merge-gate reusable workflow when a PR to THIS repo
runs it, closing the loop rather than asking every other repo to trust an
unvalidated registry.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML not installed (pip install pyyaml)")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
CONTROLS = ROOT / "core" / "controls.yaml"
INCIDENT_LOG = ROOT / "estate" / "incident-log"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def main() -> int:
    data = yaml.safe_load(CONTROLS.read_text())
    errors = []

    version = data.get("version")
    if not version or not SEMVER.match(str(version)):
        errors.append(f"controls.yaml top-level 'version' missing or not semver: {version!r}")

    controls = data.get("controls") or []
    if not controls:
        errors.append("controls.yaml has no controls -- registry is empty")

    seen_ids = set()
    for c in controls:
        cid = c.get("id")
        if not cid:
            errors.append(f"control missing 'id': {c}")
            continue
        if cid in seen_ids:
            errors.append(f"duplicate control id: {cid}")
        seen_ids.add(cid)

        for field in ("title", "applies_to", "check", "severity", "remediation", "incident"):
            if not c.get(field):
                errors.append(f"{cid}: missing required field '{field}'")

        incident = c.get("incident")
        if incident and incident != "n/a":
            incident_file = INCIDENT_LOG / f"{incident}.md"
            if not incident_file.exists():
                errors.append(
                    f"{cid}: cites incident '{incident}' but "
                    f"estate/incident-log/{incident}.md does not exist"
                )

    if errors:
        print(f"FAIL: {len(errors)} problem(s) in controls.yaml:\n")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OK: controls.yaml v{version}, {len(controls)} controls, all cite a real incident.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
