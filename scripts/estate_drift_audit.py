#!/usr/bin/env python3
"""Estate drift audit — implements the checks in ../core/controls.yaml.

Read-only. Reports findings; does not fix anything (that's a deliberate
choice per the estate's git-ops-standards: a destructive fix always needs
the capture-before-delete-verified check applied explicitly by whoever acts
on the report, not silently by an unattended script).

Usage:
    python3 estate_drift_audit.py [--root ~/dev] [--json]

Implements:
    naming-canonical-bare-name
    naming-worktree-suffix
    duplicate-remote-clones
    worktree-definition-of-done
    ops-workflows-run-from-default-branch  (scheduled workflow pinned to a
     hardcoded non-default ref; the fuller "exists on the default branch"
     comparison stays a review flag -- see the control's own note)
    ci-secrets-minted-never-static-pat
    (cross-repo-path-dependency-pinned and ci-cross-repo-checkout-explicit
     are intentionally NOT automated here -- they require judgment about
     what a path dependency "needs," which is exactly the kind of check
     this standard says not to fake. Flag path deps for human/agent review
     instead of asserting correctness.)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def sh(args: list[str], cwd: str | None = None, timeout: int = 15) -> str:
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def remote_url(repo: Path) -> str | None:
    url = sh(["git", "-C", str(repo), "remote", "get-url", "origin"])
    return url or None


def default_branch(repo: Path) -> str | None:
    """The repo's default branch (e.g. main/master/trunk) from origin/HEAD,
    or None when it can't be determined offline (no fetched remote HEAD)."""
    out = sh(["git", "-C", str(repo), "symbolic-ref", "--quiet", "--short",
              "refs/remotes/origin/HEAD"])
    if out:
        return out.split("/", 1)[1] if "/" in out else out
    return None


def repo_name_from_url(url: str) -> str | None:
    m = re.search(r"[:/]([\w.-]+)/([\w.-]+?)(\.git)?$", url)
    return m.group(2) if m else None


def is_git_repo(p: Path) -> bool:
    return (p / ".git").exists()


def is_worktree(p: Path) -> bool:
    gitpath = p / ".git"
    return gitpath.is_file()  # linked worktrees have a .git FILE, not a dir


def find_repos(root: Path, max_depth: int = 3) -> list[Path]:
    found: list[Path] = []

    def walk(base: Path, depth: int) -> None:
        try:
            entries = sorted(base.iterdir())
        except OSError:
            return
        for e in entries:
            if not e.is_dir() or e.is_symlink():
                continue
            if is_git_repo(e):
                found.append(e)
            elif depth < max_depth:
                walk(e, depth + 1)

    walk(root, 0)
    return found


def check_naming(repos: list[Path]) -> list[dict]:
    findings = []
    for repo in repos:
        name = repo.name
        if "__" in name:
            findings.append({
                "control": "naming-canonical-bare-name",
                "path": str(repo),
                "detail": f"org-prefixed name '{name}' -- should be the bare repo name",
            })
        elif re.search(r" \d+$", name) or name.endswith("-main"):
            findings.append({
                "control": "naming-canonical-bare-name",
                "path": str(repo),
                "detail": f"looks like a duplicate-download artifact: '{name}'",
            })
        if is_worktree(repo):
            url = remote_url(repo)
            real_name = repo_name_from_url(url) if url else None
            if not name.endswith(".wt"):
                findings.append({
                    "control": "naming-worktree-suffix",
                    "path": str(repo),
                    "detail": f"linked worktree missing .wt suffix: '{name}'",
                })
            elif real_name and not name.startswith(real_name):
                findings.append({
                    "control": "naming-worktree-suffix",
                    "path": str(repo),
                    "detail": f"worktree name '{name}' doesn't start with repo name '{real_name}'",
                })
    return findings


def check_duplicates(repos: list[Path]) -> list[dict]:
    by_remote: dict[str, list[Path]] = {}
    for repo in repos:
        url = remote_url(repo)
        if not url:
            continue
        key = url.lower()  # GitHub org/repo names are case-insensitive
        by_remote.setdefault(key, []).append(repo)

    findings = []
    for url, paths in by_remote.items():
        if len(paths) <= 1:
            continue
        # Worktrees of the same repo are expected to share a remote -- only
        # flag if more than one is a PRIMARY checkout (not a linked worktree).
        primaries = [p for p in paths if not is_worktree(p)]
        if len(primaries) > 1:
            findings.append({
                "control": "duplicate-remote-clones",
                "path": ", ".join(str(p) for p in primaries),
                "detail": f"{len(primaries)} separate primary clones of {url}",
            })
    return findings


def check_worktree_done(repos: list[Path]) -> list[dict]:
    findings = []
    for repo in repos:
        if not is_worktree(repo):
            continue
        branch = sh(["git", "-C", str(repo), "branch", "--show-current"])
        if not branch or branch in ("main", "master"):
            continue
        url = remote_url(repo)
        if not url:
            continue
        m = re.search(r"[:/]([\w.-]+)/([\w.-]+?)(\.git)?$", url)
        if not m:
            continue
        slug = f"{m.group(1)}/{m.group(2)}"
        out = sh(["gh", "pr", "list", "--repo", slug, "--head", branch,
                  "--state", "all", "--json", "number,state"], timeout=20)
        try:
            prs = json.loads(out) if out else []
        except json.JSONDecodeError:
            prs = []
        states = {p["state"] for p in prs}
        if not states:
            findings.append({
                "control": "worktree-definition-of-done",
                "path": str(repo),
                "detail": f"branch '{branch}' has no PR at all (open or closed) -- unmanaged Project",
            })
        elif states == {"MERGED"} or states == {"CLOSED"} or states <= {"MERGED", "CLOSED"}:
            findings.append({
                "control": "worktree-definition-of-done",
                "path": str(repo),
                "detail": f"branch '{branch}' is merged/closed -- worktree ready to remove (verify no unpushed commits first)",
            })
    return findings


def workflow_files(repo: Path) -> list[Path]:
    wf = repo / ".github" / "workflows"
    if not wf.is_dir():
        return []
    out: list[Path] = []
    for pat in ("*.yml", "*.yaml"):
        out += sorted(wf.glob(pat))
    return out


# A `schedule:` trigger is the machine-detectable marker of an operational
# workflow. `${{ ... }}` expressions never match HARDCODED_REF (the value
# class excludes `$`, `{`, whitespace), so a dynamic ref is implicitly allowed.
_SCHEDULE_TRIGGER = re.compile(r"^\s*schedule\s*:", re.M)
_HARDCODED_REF = re.compile(r"^\s*ref\s*:\s*[\"']?([A-Za-z0-9._/\-]+)[\"']?\s*$", re.M)


def check_ops_workflows_default_branch(repos: list[Path]) -> list[dict]:
    findings = []
    for repo in repos:
        # Compare against the repo's ACTUAL default branch (origin/HEAD) so a
        # repo whose default is named `trunk`/`develop` isn't falsely flagged;
        # fall back to the common defaults when it can't be determined offline.
        default = default_branch(repo)
        allowed = {default} if default else {"main", "master"}
        for wf in workflow_files(repo):
            text = wf.read_text(errors="ignore")
            if not _SCHEDULE_TRIGGER.search(text):
                continue  # only scheduled (operational) workflows are auto-checked
            if "actions/checkout" not in text:
                continue  # a `ref:` we can't attribute to a checkout is a review flag, not a hard finding
            for m in _HARDCODED_REF.finditer(text):
                ref = m.group(1)
                if ref in allowed:
                    continue
                findings.append({
                    "control": "ops-workflows-run-from-default-branch",
                    "path": str(wf),
                    "detail": f"scheduled workflow pins non-default checkout ref '{ref}' -- schedules only fire from the default branch",
                })
                break
    return findings


# (1) a *_PAT / PAT_* / *PERSONAL_ACCESS_TOKEN* secret used as a credential;
# bounded so PATREON-style names don't false-positive. (2) a static SA key.
_STATIC_PAT = re.compile(
    r"secrets\.[A-Za-z0-9_]+_PAT\b"
    r"|secrets\.PAT_[A-Za-z0-9_]+"
    r"|secrets\.[A-Za-z0-9_]*PERSONAL_ACCESS_TOKEN[A-Za-z0-9_]*",
    re.I,
)
_STATIC_SA_KEY = re.compile(r"^\s*credentials_json\s*:", re.M)


def check_ci_secret_minting(repos: list[Path]) -> list[dict]:
    findings = []
    for repo in repos:
        for wf in workflow_files(repo):
            text = wf.read_text(errors="ignore")
            # Do NOT echo the matched secret reference into the finding: a
            # secrets-hygiene tool must not itself emit secret references
            # (CodeQL py/clear-text-logging-sensitive-data). Report the file
            # and rule; a human can grep the workflow for the exact name.
            if _STATIC_PAT.search(text):
                findings.append({
                    "control": "ci-secrets-minted-never-static-pat",
                    "path": str(wf),
                    "detail": "a static *_PAT / PERSONAL_ACCESS_TOKEN secret is used as a credential -- mint in CI (WIF / App token) instead",
                })
            if _STATIC_SA_KEY.search(text) and "google-github-actions/auth" in text:
                findings.append({
                    "control": "ci-secrets-minted-never-static-pat",
                    "path": str(wf),
                    "detail": "google-github-actions/auth uses a static credentials_json key -- use workload_identity_provider (WIF)",
                })
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.expanduser("~/dev"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = Path(args.root)
    repos = find_repos(root)

    findings = []
    findings += check_naming(repos)
    findings += check_duplicates(repos)
    findings += check_worktree_done(repos)
    findings += check_ops_workflows_default_branch(repos)
    findings += check_ci_secret_minting(repos)

    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        print(f"Scanned {len(repos)} git repos/worktrees under {root}")
        print(f"Findings: {len(findings)}\n")
        by_control: dict[str, list[dict]] = {}
        for f in findings:
            by_control.setdefault(f["control"], []).append(f)
        for control, items in sorted(by_control.items()):
            print(f"=== {control} ({len(items)}) ===")
            for item in items:
                print(f"  {item['path']}")
                print(f"    {item['detail']}")
            print()

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
