# 2026-08-03: A fail-closed CI gate that wasn't enforced, then drifted

## Starting state

`cybernetic-genesis` had a well-built, fail-closed CI: a schema/contract/deploy
teeth suite that exits non-zero on any violation, aggregated behind a single
`CI gate (fail-closed aggregate)` status check. Every piece worked. And it was
**advisory** — `main` had no branch protection at all, so nothing actually
required the gate to be green before a merge. The teeth were a lock on an open
door: present, correct, and enforcing nothing. This is the merge-gate sibling of
`github-ci-health-current` — there the *watching* wasn't where it could be
watched; here the *gate* wasn't wired to the door.

## What was done, and the second failure it exposed

Branch protection was then enabled — but with a one-shot `gh api -X PUT
.../branches/main/protection`. That closed the door but created a new problem:
the protection now existed only as live GitHub state, set by an imperative
command that lived in a terminal, not in the repo. It was invisible to review,
not reproducible, and — crucially — undriftable: nothing could tell you if it
later changed. It did. Within the same day, a re-read found `enforce_admins`
had flipped from the `true` it was set to, back to `false`, changed out of band
(most likely a break-glass `DELETE .../enforce_admins` that was never re-asserted).
An imperative security control with no declared source of truth silently weakened
and nothing noticed — the exact failure mode `IaC-everything, no thousand cuts`
exists to prevent.

## The broader pattern

Branch protection is estate security posture (who can merge, on what evidence,
whether admins can bypass, whether `main` can be force-pushed). Applying it by
hand, per repo, is a thousand small cuts: each repo's real policy is whatever
someone last typed, knowable only by querying live state, defensible by no
committed artifact. The estate already learned this lesson for GCP/WIF (codified
in tofu) and for CI health (`estate-ci-health`); repo protection was the gap.

## The fix

- Each repo that opts in commits `.github/branch-protection.main.json` — the
  declarative source of truth (the exact classic-protection API body; the org is
  not on GitHub Team, so rulesets are unavailable — migrate if the tier changes).
- `scripts/estate_branch_protection_audit.py` + `.github/workflows/estate-branch-protection.yml`
  — an org-wide, read-only scan (sibling to `estate-ci-health`, minted GitHub App
  token, never a PAT) that flags any repo whose live protection drifts from, or is
  absent despite, its committed spec. Reconcile is a deliberate `workflow_dispatch`,
  never a blind scheduled auto-mutation of live security state.
- Control `main-branch-protection-enforced` in `core/controls.yaml` makes the rule
  checkable and traceable to this incident.

Deliberately scoped, like `github-ci-health-current`: only repos that DECLARE a
spec can produce a hard finding. A repo with no spec hasn't opted in and is not
nagged — the check is precise, not a "every repo must be protected" wolf-cry.
The first run against `cybernetic-genesis` reproduced the incident exactly: it
flagged `enforce_admins: spec=True live=False`, the very drift found by hand.
