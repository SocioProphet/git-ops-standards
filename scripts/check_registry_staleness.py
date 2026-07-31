#!/usr/bin/env python3
"""Is this local clone of git-ops-standards behind origin/main's controls.yaml?

Staleness is itself a finding, not a silent condition. Run this from a local
clone before trusting anything cached about the standard (a memory entry
that paraphrased it, a CLAUDE.md pointer that's never been rechecked).

Usage: python3 check_registry_staleness.py [--repo-path ~/dev/git-ops-standards]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

SEMVER = re.compile(r'version:\s*"?(\d+\.\d+\.\d+)"?')


def sh(args: list[str], cwd: str) -> str:
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=20)
    return r.stdout.strip()


def extract_version(text: str) -> str | None:
    m = SEMVER.search(text)
    return m.group(1) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-path", default=None)
    args = ap.parse_args()

    import os
    repo = args.repo_path or os.path.expanduser("~/dev/git-ops-standards")

    local_text = open(os.path.join(repo, "core", "controls.yaml")).read()
    local_version = extract_version(local_text)

    sh(["git", "fetch", "origin", "main", "--quiet"], cwd=repo)
    remote_text = sh(["git", "show", "origin/main:core/controls.yaml"], cwd=repo)
    remote_version = extract_version(remote_text)

    if not local_version or not remote_version:
        print("WARN: could not determine version from local or remote controls.yaml")
        return 1

    if local_version != remote_version:
        print(f"STALE: local clone is at v{local_version}, origin/main is at "
              f"v{remote_version}. Run `git -C {repo} pull` and re-check any "
              f"binding (memory, CLAUDE.md pointer) that assumed the old version.")
        return 1

    print(f"OK: local clone matches origin/main at v{local_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
