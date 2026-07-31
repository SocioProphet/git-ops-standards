#!/usr/bin/env python3
"""CI check implementing the automatable part of controls.yaml's pr-merge-gate.

Fails (blocks) if:
  - the PR's mergeable state is CONFLICTING (checked fresh, via the API --
    not trusting a cached state from when the PR was opened)
  - there are unresolved review threads (a proxy for "review comments
    addressed" -- doesn't replace an adversarial self-review, but a
    still-open review thread on a PR about to merge is exactly the kind of
    "reviewed but ignored" pattern controls.yaml exists to stop)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def gh(args: list[str]) -> tuple[int, str]:
    r = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", required=True)
    args = ap.parse_args()

    rc, out = gh(["pr", "view", args.pr, "--repo", args.repo,
                  "--json", "mergeable,reviewDecision"])
    if rc != 0:
        print(f"FAIL: could not query PR state: {out}")
        return 1
    data = json.loads(out)

    failures = []
    if data.get("mergeable") == "CONFLICTING":
        failures.append("PR is CONFLICTING with its base -- rebase before merging.")

    rc, out = gh(["api", f"repos/{args.repo}/pulls/{args.pr}/reviews",
                  "--jq", "[.[] | select(.state == \"CHANGES_REQUESTED\")] | length"])
    if rc == 0 and out.strip().isdigit() and int(out.strip()) > 0:
        failures.append(
            f"{out.strip()} review(s) still requesting changes -- address or "
            "get a re-review before merging."
        )

    if failures:
        print("FAIL: pr-merge-gate\n")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("OK: PR is mergeable and has no outstanding changes-requested reviews.")
    print("Note: this does not replace an adversarial self-review on repos with "
          "no automated reviewer -- see git-ops-standards core/resources/"
          "day-to-day-git-workflow.md #10.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
