# 2026-07-31: Estate-wide directory cleanup

The incident that produced every control in `core/controls.yaml`. Kept as a
worked example, not just a summary — the point is to show *how* each
violation was actually found and fixed, so the detection method is reusable.

## Starting state

`~/dev` had grown to 270 top-level directories across 177 unique underlying
git repositories — 93 of those directories were linked worktrees, many with
non-canonical names (`pp-copilot-t1.wt`, `wt-source-os-rollback-loud`).
Separately, 34 directories were never git-initialized at all (extracted
zip/tarball payloads, some duplicating content that had long since been
absorbed into a real repo under a different name).

## What triggered it

A cluster of interactive sessions hit their account usage limit
simultaneously mid-task (see the separate multi-account session review). Recovering that work required auditing which local branches actually held
unique content vs. which were safe to abandon — which is what surfaced how
much naming and duplication drift had already accumulated independent of the
immediate incident.

## Findings, by control

**`duplicate-remote-clones`** — 12 groups of duplicate clones found by
grouping every local repo directory by `git remote get-url origin`. Examples:
`.github` had three separate clones (`dot-github`, `dotgithub-org`,
`socioprophet-dotgithub`); `homebrew-tap` had three (`homebrew-tap`,
`SourceOS-Linux__homebrew-tap`, `homebrew-tap-pub`). For each group, branch/
dirty/sync state was compared and the most current copy kept.

**`squash-merge-false-signal`** — the first pass at finding "stranded"
branches used ahead/behind counts and is-ancestor-of-main checks. Both
signals produced enormous false-positive rates: ~250 branches looked
possibly-stranded; cross-referencing actual GitHub PR state
(`gh pr list --head <branch> --state all`) found all but 5 were already
merged (via squash, hence the stale local signal) or superseded. **Lesson:
never trust ahead/behind or ancestor checks alone as evidence of loss.**

**`cross-repo-path-dependency-pinned`** — `sociosphere`'s `gbrg-core` crate
depends on `hellgraph`'s `hg_analytics` crate via a hardcoded relative path
naming a specific worktree directory (`hellgraph-rust`). That worktree got
deleted during cleanup (its branch showed as "MERGED" — but that check had
matched a *different*, already-merged PR against the same branch name; the
actual PR needed, hellgraph#47, was still open and unmerged). Deleting the
worktree broke the build. Fix: recreated the worktree under a canonical name
(`hellgraph-rust-parallel-analytics.wt`), repointed the path dependency, and
added a comment documenting exactly which unmerged branch it needs.

**`ci-cross-repo-checkout-explicit`** — a governance test
(`test_gate_fires_both_ways` — the "prove teeth both ways" control) shells
out to a sibling repo's script (`agent-registry/tools/authorize.py`) via a
hardcoded fallback path (`~/dev/agent-registry`). That path exists on the
developer's machine but not in CI, so the test was silently exercising only
the fail-closed path in CI (a control that can't prove it fires both ways is
itself suspect). Fix: added an explicit second `actions/checkout` step in
CI for the sibling repo, verified locally first by simulating the exact
directory layout CI would produce (symlinking the dependency into the repo
root the same way the checkout step would place it) before pushing.

**`pr-merge-gate`** — of the PRs reviewed for merge, several needed real
fixes first, not just a rubber-stamp: two Copilot-flagged code-quality
issues (an unused import; a loop that iterated only to build one
loop-invariant entry — the "unused variable" comment was cosmetic, the real
bug was the loop itself), a missing dev-dependency declaration
(`jsonschema`), and one PR built on stale pre-merge commits producing an
add/add conflict, fixed by rebasing to just the genuinely-unique commit
rather than resolving the whole branch's history.

**`worktree-definition-of-done`** — 87 worktrees across 15 repos were
confirmed merged (via fresh PR-state check, not cached ahead/behind) and
removed in one pass; 3 more turned out to be stale plain-`main` checkouts
(19-27 commits behind, no unique branch work) sitting alongside proper
worktrees for no reason and were removed too.

**`archive-retention-policy`** — found two automated safety-net backup
directories (`_captures/`, `_gbrg_backups/`) containing git bundles taken
during the triggering incident. Confirmed via `gsutil ls` that a separate,
already-completed backup (Noetica's branch graveyard) had a durable GCS copy
before treating any of it as safe to eventually retire.

## The estate-wide pattern this revealed

None of these were isolated mistakes — they're the same failure mode
(unmanaged drift between audits) recurring at every layer: directory names,
branch lifecycle, cross-repo dependencies, CI parity with local dev, and PR
hygiene. That's the case for `scripts/estate_drift_audit.py` running on a
schedule instead of waiting for the next incident to force a manual sweep.
