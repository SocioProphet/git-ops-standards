# Scripts

`estate_drift_audit.py` — implements the automatable controls from
`../core/controls.yaml` (naming, duplicate clones, worktree
definition-of-done). Read-only; reports, doesn't fix. Requires `git` and
`gh` (for the worktree-done check) on PATH.

```bash
python3 estate_drift_audit.py --root ~/dev
python3 estate_drift_audit.py --root ~/dev --json   # machine-readable
```

Exit code is nonzero if any findings were reported — suitable for a
scheduled job that should surface a notification on drift.

Not automated here (deliberately — see the script's docstring):
`cross-repo-path-dependency-pinned` and `ci-cross-repo-checkout-explicit`.
Both require judging *intent* (does this path dependency need an unmerged
branch, does this test genuinely need a sibling repo checked out) that
shouldn't be faked by a heuristic. Review these manually against the
checklist in `core/controls.yaml` when touching a cross-repo dependency.
