# Binding: Claude Code

How this standard gets consulted and enforced inside a Claude Code session,
without any of the standard's actual content living in Claude-specific
format. This file is the only thing here that should ever mention "CLAUDE.md"
or "memory" by name.

## 1. Memory entry (durable, cross-session recall)

A single `reference`-type memory should point here, not duplicate the
content:

```markdown
---
name: git-ops-standards
description: Canonical git workflow/devops standard for this estate — naming, branching, worktrees, PR-merge gate, cross-repo dependencies. Consult before any bulk git operation (delete, worktree removal, PR merge) or when naming anything new.
metadata:
  type: reference
  pinned_version: "1.0.0"
---

SocioProphet/git-ops-standards is the canonical, agent-agnostic standard.
core/ = generic rules, estate/ = this org's specific bindings and incident
log, core/controls.yaml = machine-checkable rule registry (currently v1.0.0
-- run scripts/check_registry_staleness.py before trusting this pin is
still current).

Before: naming anything new, removing a worktree, deleting a branch/clone,
merging a PR, or adding a cross-repo path dependency — check the relevant
control in core/controls.yaml and the day-to-day-git-workflow.md section.
Note: as of v1.0.0 this is also technically enforced, not just advisory --
see §3 below.

[[project_stranded_work_register]] and other estate-cleanup memories are
now superseded by estate/incident-log/2026-07-31-estate-cleanup.md in this
repo — the repo is the durable copy going forward.
```

## 2. CLAUDE.md (per-repo, applies while working in that repo)

Any repo in this estate should have a short pointer in its `CLAUDE.md`
(not a copy of the rules):

```markdown
## Git workflow
Follow SocioProphet/git-ops-standards (clone at ~/dev/git-ops-standards).
In particular: naming convention (core/resources/day-to-day-git-workflow.md
§1-3), the PR-merge gate (§10) before merging anything, and
capture-before-delete (§9) before any destructive git operation.
```

## 3. Pre-flight check before risky actions -- as of v1.0.0, this is enforced

`scripts/pretooluse_git_safety_hook.py`, wired as a `PreToolUse` hook on the
`Bash` matcher in `~/.claude/settings.json`, intercepts `rm -rf`, `git
worktree remove`, `git push --force` (not `--force-with-lease`), and `git
branch -D` on every Bash call in this session, and **blocks** them unless
the target branch passes `capture-before-delete-verified`'s bar (fetched
fresh, not from a cached ref). Proven live, not just configured: it denied
a genuinely-unpushed test branch, allowed an already-merged one, and caught
its own creator trying to clean up disposable test fixtures that happened
to be unpushed -- see the commit that introduced it for the full proof
transcript.

This closes what was previously an honest gap: earlier versions of this
binding said "there is no enforced gate preventing an agent from skipping
it." That's no longer true for the four operations above. It's still true
for anything the hook's regex doesn't recognize (dynamically constructed
commands, wrapper scripts) -- see the hook's own docstring for the stated
limitation. Don't treat the hook's silence as proof an action was safe;
it's a net, not a guarantee.

## 4. Scheduled audit (local disk, detective)

`scripts/estate_drift_audit.py` (agent-agnostic, plain Python + `git` +
`gh`) runs on a local `launchd` schedule (crontab is blocked by macOS TCC
permissions in this environment) -- weekly, logs to
`~/Library/Logs/git-ops-standards/`. This is detective, not preventive: it
reports drift, it doesn't block anything. `tests/test_estate_drift_audit.py`
proves it fires on real violations and stays quiet on a clean tree --
re-run that after any change to the audit script's logic, not just once.

## 5. CI gate (cross-repo, preventive, agent-agnostic)

`.github/workflows/pr-merge-gate.yml` is a reusable workflow. Any repo in
the estate adopts it by adding to its own workflow file:

```yaml
jobs:
  git-ops-standards:
    uses: SocioProphet/git-ops-standards/.github/workflows/pr-merge-gate.yml@main
```

and then marking that check as **required** in branch protection. That
last step is what actually gives it teeth across the estate: a required
check blocks the merge button regardless of who -- or what -- authored the
PR, independent of any one Claude Code session's discipline. Not yet
adopted by any repo as of v1.0.0 -- this binding documents how to, it
doesn't claim it's rolled out everywhere.
