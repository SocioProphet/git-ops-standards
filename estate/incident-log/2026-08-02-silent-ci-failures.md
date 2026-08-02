# 2026-08-02: Silent CI failures found only by manual sweep

## Starting state

During an unrelated CHRONOS-doctrine integration sweep across eight repos, a
by-hand check of `gh run list --branch main` on each repo (because the work
happened to touch them) turned up two repos with red `main` CI that nobody
had noticed:

- **holmes** — `validate` workflow failing since 2026-07-19 (two weeks). A
  first attempt to diagnose it locally found a `dyld: missing LC_UUID load
  command` crash and treated that as the root cause. That diagnosis was
  wrong: `dyld` is a macOS-only dynamic-linker error, and the actual CI
  runner is `ubuntu-latest` (Linux, ELF binaries, no `dyld` at all). The
  local machine's Go build happened to produce a broken Mach-O binary for
  unrelated reasons, and that got conflated with the real failure. The real
  cause, found only by reproducing the exact `make validate` sequence inside
  a real `golang:1.23-bookworm` container: `bin/holmes search` makes a live
  HTTP call to hellgraph-service's port and gets `connection refused` — no
  crash, just an unhandled expected failure, and the command's own `doctor`
  subcommand had already declared that same backend `"not-yet-wired"`.
- **prophet-mesh** — `ci` workflow failing since 2026-07-30 (three days),
  52 real `ruff` lint errors, most auto-fixable. Nobody had looked because
  nothing surfaces a red `main` unless someone happens to check.

Neither repo has any mechanism that would have surfaced these on its own —
each only fails its own CI, which nobody is watching unless they're actively
working in that specific repo that week.

## The broader pattern (same incident, wider lens)

The same session repeatedly found a narrower version of this disease inside
individual repos: a validator/gate script exists, is well-written, has real
fixtures — and is never invoked by any CI workflow (or is invoked but the
dispatch/path-filter logic silently skips the case it's meant to catch).
Confirmed instances the same day: sociosphere's CHRONOS validator, gaia-
world-model's ingest script, alexandrian-academy's promotion gate,
ontogenesis's entire `vocab/` directory, superconscious's decision-emission
dispatch rule, and (a level up) prophet-platform's Argo Rollouts/Cilium
manifest that had never been reconciled at all. This incident is the
org-wide version of the same root cause: nothing was watching whether the
watching itself was actually happening.

## What triggered fixing it

Explicit direction, after landing the CHRONOS work: don't just fix the two
repos found by accident — build the system that would have caught them
without a manual sweep, and make sure it actually runs.

## The fix

`scripts/estate_ci_health_audit.py` + `.github/workflows/estate-ci-health.yml`
— a scheduled, org-wide scan of every first-party (non-fork, non-archived)
repo's latest default-branch CI conclusion. See `core/controls.yaml`'s
`github-ci-health-current` entry for the checkable rule itself.

Deliberately scoped narrow: only "latest run conclusion is `failure`" is a
hard finding. `cancelled` and "no CI runs at all" are surfaced as lower-
confidence notes, not failures — a first draft that also hard-failed on
those produced noise on repos where cancellation is routine (a newer push
superseding an in-flight run) or where CI legitimately only runs on release
events. A checker that cries wolf gets ignored, which is worse than no
checker (see `feedback_self_validating_checker.md`'s sibling principle).
