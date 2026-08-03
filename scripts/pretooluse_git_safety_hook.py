#!/usr/bin/env python3
"""PreToolUse hook enforcing capture-before-delete-verified (git-ops-standards
core/controls.yaml) on risky Bash calls.

It also blocks a plain `git push` when the target repo is mid-rebase, mid-merge,
or has unresolved conflicts in the index -- so a mis-read rebase exit code can
never publish a half-finished rebase (state-based, fails open).

Reads the Claude Code hook input JSON on stdin. If tool_input.command matches
a risky pattern (rm -rf, git worktree remove, git push --force, git branch
-D), extracts the target repo/branch and verifies it against the same bar as
core/resources/day-to-day-git-workflow.md #9:
  1. exact branch tip is an ancestor of the remote default branch, OR
  2. branch is pushed AND has an open/merged PR, OR
  3. branch is merely pushed (weakest acceptable bar -- allowed with a
     warning, not blocked)
Anything else (not pushed, can't determine, not even a git repo when one was
expected) blocks the call.

Known limitation, stated plainly rather than pretended away: this is a
regex-based command parser, not a shell interpreter. It will not catch every
way to construct these commands (dynamic variables, commands assembled via
xargs/eval, commands run through a wrapper script). It catches the literal,
common forms an agent or human actually types. Treat it as a net, not a
guarantee -- see core/controls.yaml's own failure-mode list.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys


def sh(args: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "").strip()
    except Exception as exc:
        return 1, str(exc)


def allow(msg: str | None = None) -> None:
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}
    if msg:
        out["systemMessage"] = msg
    print(json.dumps(out))
    sys.exit(0)


def deny(reason: str) -> None:
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
        "systemMessage": f"[git-ops-standards capture-before-delete] BLOCKED: {reason}",
    }
    print(json.dumps(out))
    sys.exit(0)


def repo_default_branch(repo: str) -> str | None:
    for cand in ("main", "master"):
        rc, _ = sh(["git", "-C", repo, "rev-parse", "--verify", "--quiet", f"origin/{cand}"])
        if rc == 0:
            return cand
    rc, out = sh(["git", "-C", repo, "symbolic-ref", "refs/remotes/origin/HEAD"])
    if rc == 0 and out:
        return out.rsplit("/", 1)[-1]
    return None


def repo_slug(repo: str) -> str | None:
    rc, url = sh(["git", "-C", repo, "remote", "get-url", "origin"])
    if rc != 0 or not url:
        return None
    m = re.search(r"[:/]([\w.-]+)/([\w.-]+?)(\.git)?$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def verify_branch_safe(repo: str, branch: str) -> tuple[bool, str]:
    """Returns (safe, reason)."""
    if not os.path.isdir(os.path.join(repo, ".git")) and not os.path.isfile(os.path.join(repo, ".git")):
        return True, "not a git repo/worktree"

    default = repo_default_branch(repo)
    if default:
        sh(["git", "-C", repo, "fetch", "origin", default, "--quiet"], timeout=25)
        rc, _ = sh(["git", "-C", repo, "merge-base", "--is-ancestor", branch, f"origin/{default}"])
        if rc == 0:
            return True, f"'{branch}' is an ancestor of origin/{default} -- already captured"

    slug = repo_slug(repo)
    if slug:
        rc, out = sh(["gh", "pr", "list", "--repo", slug, "--head", branch,
                      "--state", "all", "--json", "number,state"], timeout=20)
        if rc == 0 and out:
            try:
                prs = json.loads(out)
            except json.JSONDecodeError:
                prs = []
            states = {p["state"] for p in prs}
            if states:
                return True, f"'{branch}' has a PR ({', '.join(sorted(states))}) -- recoverable"

    rc, out = sh(["git", "-C", repo, "ls-remote", "origin", f"refs/heads/{branch}"])
    if rc == 0 and out.strip():
        return True, f"'{branch}' is pushed to origin (no PR) -- weakest acceptable bar, allowed"

    return False, (
        f"'{branch}' in {repo} has no evidence of upstream capture: not an ancestor of "
        f"origin/{default or '<default>'}, no PR found, and not pushed to origin. "
        "Push it before deleting anything referencing it (see git-ops-standards "
        "core/resources/day-to-day-git-workflow.md #9)."
    )


def extract_targets(cmd: str) -> list[tuple[str, str | None]]:
    """Returns list of (repo_path, branch) to verify, or [] if nothing risky matched."""
    targets: list[tuple[str, str]] = []

    for m in re.finditer(r"git\s+(?:-C\s+(\S+)\s+)?worktree\s+remove\s+(?:--force\s+)?(\S+)", cmd):
        repo_c, wt_path = m.group(1), m.group(2).rstrip("/")
        wt_path = os.path.expanduser(wt_path)
        rc, branch = sh(["git", "-C", wt_path, "branch", "--show-current"])
        repo_c_expanded = os.path.expanduser(repo_c) if repo_c else None
        repo_for_slug = repo_c_expanded or wt_path
        if rc == 0 and branch:
            targets.append((repo_for_slug, branch))

    for m in re.finditer(r"git\s+(?:-C\s+(\S+)\s+)?branch\s+-D\s+(\S+)", cmd):
        repo_c, branch = m.group(1), m.group(2)
        targets.append((os.path.expanduser(repo_c) if repo_c else ".", branch))

    if re.search(r"git\s+(?:-C\s+(\S+)\s+)?push\b", cmd) and re.search(r"--force\b", cmd) and "--force-with-lease" not in cmd:
        m = re.search(r"git\s+(?:-C\s+(\S+)\s+)?push\b", cmd)
        repo_c = m.group(1) if m else None
        repo = os.path.expanduser(repo_c) if repo_c else "."
        rc, branch = sh(["git", "-C", repo, "branch", "--show-current"])
        if rc == 0 and branch:
            targets.append((repo, branch))

    for m in re.finditer(r"\brm\s+(?:-\w*r\w*f\w*|-\w*f\w*r\w*)\s+(.+)", cmd):
        rest = m.group(1)
        for tok in rest.split():
            if tok.startswith("-"):
                continue
            path = os.path.expanduser(tok.rstrip("/"))
            if os.path.isdir(os.path.join(path, ".git")) or os.path.isfile(os.path.join(path, ".git")):
                rc, branch = sh(["git", "-C", path, "branch", "--show-current"])
                if rc == 0 and branch:
                    targets.append((path, branch))

    return targets


def push_target_repo(cmd: str) -> str:
    """Best-effort target repo dir for a `git push` in cmd:
    `git -C <dir> push`, else a leading `cd <dir>`, else the current dir."""
    m = re.search(r"git\s+-C\s+(\S+)\s+push\b", cmd)
    if m:
        return os.path.expanduser(m.group(1).strip("\"'"))
    m = re.search(r"\bcd\s+(\"[^\"]+\"|'[^']+'|[^\s;&|]+)", cmd)
    if m:
        return os.path.expanduser(m.group(1).strip("\"'"))
    return "."


def rebase_or_conflict_reason(repo: str) -> str | None:
    """Reason string if `repo` is mid-rebase/merge or has unresolved conflicts,
    else None. Uses git state (not text scanning), so no false positives on docs
    that merely mention conflict markers. Fails open: a non-repo returns None."""
    rc, gitdir = sh(["git", "-C", repo, "rev-parse", "--git-dir"])
    if rc != 0:
        return None
    gd = gitdir if os.path.isabs(gitdir) else os.path.join(repo, gitdir)
    if os.path.isdir(os.path.join(gd, "rebase-merge")) or os.path.isdir(os.path.join(gd, "rebase-apply")):
        return "a rebase is in progress"
    if os.path.isfile(os.path.join(gd, "MERGE_HEAD")):
        return "a merge is in progress"
    rc, unmerged = sh(["git", "-C", repo, "ls-files", "-u"])
    if rc == 0 and unmerged.strip():
        n = len({ln.split("\t")[-1] for ln in unmerged.splitlines() if ln})
        return f"{n} unresolved/conflicted file(s) in the index"
    return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()
        return

    if payload.get("tool_name") != "Bash":
        allow()
        return

    cmd = (payload.get("tool_input") or {}).get("command", "")
    if not cmd:
        allow()
        return

    # Guard: never push a half-finished rebase/merge or a conflicted tree.
    # (Retrospective fix: an agent script mis-read a rebase exit code and pushed
    # a mid-rebase branch with an unresolved conflict. State-based, fails open.)
    if re.search(r"git\s+(?:-C\s+\S+\s+)?push\b", cmd):
        repo = push_target_repo(cmd)
        why = rebase_or_conflict_reason(repo)
        if why:
            deny(
                f"git push blocked: {why} in {repo}. Finish or abort the "
                "rebase/merge and resolve all conflicts before pushing."
            )
            return

    targets = extract_targets(cmd)
    if not targets:
        allow()
        return

    reasons = []
    for repo, branch in targets:
        safe, reason = verify_branch_safe(repo, branch)
        reasons.append(reason)
        if not safe:
            deny(reason)
            return

    allow("[git-ops-standards] capture-before-delete check passed: " + "; ".join(reasons))


if __name__ == "__main__":
    main()
