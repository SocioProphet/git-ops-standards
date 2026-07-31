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
---

SocioProphet/git-ops-standards is the canonical, agent-agnostic standard.
core/ = generic rules, estate/ = this org's specific bindings and incident
log, core/controls.yaml = machine-checkable rule registry.

Before: naming anything new, removing a worktree, deleting a branch/clone,
merging a PR, or adding a cross-repo path dependency — check the relevant
control in core/controls.yaml and the day-to-day-git-workflow.md section.

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

## 3. Pre-flight check before risky actions

Before a bulk destructive action (multiple `rm -rf`, mass `git worktree
remove`, force-push), a Claude Code session should:
1. Re-read the relevant `core/controls.yaml` entries.
2. Apply `capture-before-delete-verified`'s bar explicitly, not from memory
   of "probably fine."
3. Note in its own response which control(s) it checked, so the check is
   visible to the user, not just asserted.

This is a discipline to self-apply, not a technical hook — there is no
enforced gate preventing an agent from skipping it. Treat skipping it as
the same category of error the 2026-07-31 incident log describes.

## 4. Scheduled audit

`scripts/estate_drift_audit.py` (agent-agnostic, plain Python + `git` +
`gh`) is what a Claude Code scheduled task (or cron) actually runs. The
schedule wraps it; the script and the controls it checks are the portable
part — see `scripts/README.md` for how to wire the schedule.
