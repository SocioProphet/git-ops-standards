#!/usr/bin/env python3
"""Adversarial proof that estate_drift_audit.py fires both ways.

Per core/resources/day-to-day-git-workflow.md's own governing principle (and
feedback_ask_what_calls_this.md: "prove teeth BOTH ways") -- a detector that
has never been shown to actually detect anything, and never been shown to
stay quiet on a clean case, is exactly as suspect as an unenforced rule.

This builds two throwaway fixture trees under a temp root:
  - fixtures/bad/  -- a deliberately duplicate-remote clone and a
    deliberately non-canonical worktree name
  - fixtures/good/ -- a single clean clone, canonically named

and asserts the script's naming + duplicate-clone checks fire on the bad
tree and stay silent on the good one. Does NOT test worktree-definition-of-
done (that check calls `gh`, i.e. needs real network + a real PR; out of
scope for a fast, offline unit test -- see the script's own README for why
that check isn't part of the fully-automated set either).

Run: python3 tests/test_estate_drift_audit.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIT_SCRIPT = HERE.parent / "scripts" / "estate_drift_audit.py"


def make_bare_repo(path: Path) -> None:
    subprocess.run(["git", "init", "--quiet", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "--allow-empty", "-q", "-m", "init"], check=True)


def set_fake_remote(path: Path, url: str) -> None:
    subprocess.run(["git", "-C", str(path), "remote", "add", "origin", url], check=True)


def run_audit(root: Path) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), "--root", str(root), "--json"],
        capture_output=True, text=True,
    )
    return r.returncode, r.stdout


def test_bad_fixture_fires() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="git_ops_standards_bad_"))
    try:
        # Duplicate clone: two directories, same fake remote.
        make_bare_repo(tmp / "some-repo")
        set_fake_remote(tmp / "some-repo", "git@github.com:example-org/some-repo.git")
        make_bare_repo(tmp / "Org__some-repo")
        set_fake_remote(tmp / "Org__some-repo", "git@github.com:example-org/some-repo.git")

        rc, out = run_audit(tmp)
        assert rc == 1, "expected nonzero exit when findings exist"
        assert "duplicate-remote-clones" in out, "expected duplicate-remote-clones finding"
        assert "naming-canonical-bare-name" in out, "expected the org-prefixed name to be flagged"
        print("PASS: bad fixture -- audit fires on real violations")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_good_fixture_stays_quiet() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="git_ops_standards_good_"))
    try:
        make_bare_repo(tmp / "clean-repo")
        set_fake_remote(tmp / "clean-repo", "git@github.com:example-org/clean-repo.git")

        rc, out = run_audit(tmp)
        assert rc == 0, f"expected zero exit on a clean tree, got findings:\n{out}"
        print("PASS: good fixture -- audit stays silent on a clean tree")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_bad_fixture_fires()
    test_good_fixture_stays_quiet()
    print("\nBoth directions proven: the detector fires on real violations and "
          "stays quiet on a clean tree.")
