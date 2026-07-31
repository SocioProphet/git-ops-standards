# PARA for Git Knowledge-Ops

[PARA](https://fortelabs.com/blog/para/) (Projects / Areas / Resources /
Archives) organizes by *actionability*, not by topic. Applied to git:

## Projects — has an end state, has an owner

A branch, a PR, a worktree. Each one needs:
- an **owner** (who's driving it to done — a human or an agent session)
- a **target** (which repo, which base branch)
- a **definition of done** — merged, or explicitly closed as abandoned.
  "I'll get back to it" is not a definition of done; it's how a worktree
  becomes an Area problem six weeks later.

A Project that has no definition of done isn't a project — it's an
unmanaged Area problem wearing a branch name.

## Areas — no end date, standing responsibility

Naming convention compliance, CI health, cross-repo dependency hygiene,
license compliance, worktree lifecycle across the whole estate. Nobody
"finishes" an Area; you maintain it, and drift is the failure mode, not a
missed deadline.

This is where `estate_drift_audit.py` (see `scripts/`) operates: it doesn't
check whether any *one* branch is done, it checks whether the *standing
rules* (naming, no orphaned duplicates, no stale path dependencies) still
hold across everything.

## Resources — reference material, consulted not maintained-to-completion

`core/resources/day-to-day-git-workflow.md` is the canonical resource: naming,
checkout, branching, rebasing, push/pull, stash, cross-repo dependencies,
capture-before-delete, PR-merge gate. Written once, referenced constantly,
updated only when a new incident teaches something the current version
doesn't cover.

## Archives — done, kept for provenance, not for daily reference

Merged branches (pruned locally — the content lives in the target's history
now), closed PRs, safety-net bundles (`git bundle` snapshots taken before a
risky operation). Archives need a **retention policy**, not indefinite
accumulation:
- Local worktrees: removed once merged/abandoned (see day-to-day-git-workflow §2).
- Safety-net bundles: kept until the operation they insured against is
  confirmed safe (typically: until the next full audit cycle finds nothing
  wrong), then deleted. A bundle nobody will ever restore from is disk
  clutter pretending to be a backup strategy.
- Stale local branch refs (after a squash-merge, or after a remote branch is
  deleted post-merge): pruned on a schedule, not left to accumulate into the
  hundreds.

## Why this matters for an agent-operated estate specifically

An agent session doesn't have the same continuity a human does — it can be
interrupted (rate limit, crash, context reset) mid-Project. If Projects
don't carry an explicit definition-of-done and Areas aren't audited on a
schedule independent of any one session, drift compounds invisibly between
sessions until someone (or something) finally does a manual sweep and finds
270 directories where there should be 170.
