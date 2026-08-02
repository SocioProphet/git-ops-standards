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
    # Local (not --global) identity: a fresh CI runner has no global git
    # user.name/user.email configured, unlike a developer's own machine.
    # This was caught by the real CI run, not assumed -- see commit history.
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
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


def _repo_with_workflow(root: Path, name: str, wf_name: str, wf_body: str) -> None:
    make_bare_repo(root / name)
    set_fake_remote(root / name, f"git@github.com:example-org/{name}.git")
    wf_dir = root / name / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / wf_name).write_text(wf_body)


# A scheduled workflow pinned to a feature ref AND leaking a static PAT.
_BAD_WORKFLOW = (
    "on:\n"
    "  schedule:\n"
    "    - cron: '0 3 * * *'\n"
    "jobs:\n"
    "  mirror:\n"
    "    runs-on: ubuntu-latest\n"
    "    steps:\n"
    "      - uses: actions/checkout@v4\n"
    "        with:\n"
    "          ref: fix/some-feature\n"
    "      - run: echo sync\n"
    "        env:\n"
    "          TOKEN: ${{ secrets.GITEA_PAT }}\n"
)

# A scheduled workflow that mints via WIF, no hardcoded ref, no PAT.
_GOOD_WORKFLOW = (
    "on:\n"
    "  schedule:\n"
    "    - cron: '0 3 * * *'\n"
    "permissions:\n"
    "  id-token: write\n"
    "  contents: read\n"
    "jobs:\n"
    "  reconcile:\n"
    "    runs-on: ubuntu-latest\n"
    "    steps:\n"
    "      - uses: actions/checkout@v4\n"
    "      - uses: google-github-actions/auth@v2\n"
    "        with:\n"
    "          workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}\n"
    "          service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}\n"
)


def test_bad_workflow_fires() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="git_ops_standards_wf_bad_"))
    try:
        _repo_with_workflow(tmp, "bad-ops-repo", "mirror.yml", _BAD_WORKFLOW)
        rc, out = run_audit(tmp)
        assert rc == 1, "expected nonzero exit when findings exist"
        assert "ops-workflows-run-from-default-branch" in out, "feature-ref schedule not flagged"
        assert "ci-secrets-minted-never-static-pat" in out, "static PAT not flagged"
        print("PASS: bad workflow -- ops-from-main + minted-secrets controls fire")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_good_workflow_stays_quiet() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="git_ops_standards_wf_good_"))
    try:
        _repo_with_workflow(tmp, "clean-ops-repo", "reconcile.yml", _GOOD_WORKFLOW)
        rc, out = run_audit(tmp)
        assert rc == 0, f"expected zero exit on a WIF/default-branch workflow, got:\n{out}"
        print("PASS: good workflow -- CI-ops controls stay silent on a minted/default-branch workflow")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_bad_fixture_fires()
    test_good_fixture_stays_quiet()
    test_bad_workflow_fires()
    test_good_workflow_stays_quiet()
    print("\nBoth directions proven: the detector fires on real violations and "
          "stays quiet on a clean tree.")
