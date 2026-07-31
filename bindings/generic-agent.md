# Binding: arbitrary agent framework

For a non-Claude agent (your own deployed agents, or any other framework)
consuming this standard.

## What to load

- `core/PARA.md` + `core/resources/day-to-day-git-workflow.md` as system-prompt
  or retrieved context whenever the agent is about to touch git.
- `core/controls.yaml` as a structured rule set your agent's tool-permission
  layer can gate against — e.g. before allowing a `rm -rf` or `git worktree
  remove` tool call, check `capture-before-delete-verified`'s conditions
  programmatically rather than trusting the agent's own judgment.
- `estate/` only if the agent operates inside this specific estate; skip it
  entirely for a general-purpose or third-party deployment.

## Minimum viable integration

1. Give the agent read access to this repo (clone or fetch at session
   start).
2. Inject `core/resources/day-to-day-git-workflow.md` verbatim into its
   system prompt or an always-loaded memory/context slot — it's short
   enough to afford this, and paraphrasing it risks losing the specific
   "why" that makes each rule enforceable rather than aspirational.
3. Wire `core/controls.yaml`'s IDs into whatever your framework uses for
   tool-call interception or pre-action validation, if it has one. If it
   doesn't, at minimum require the agent to name which control it checked
   before a destructive action, in its own output — visibility beats
   nothing.
4. Point the agent at `scripts/estate_drift_audit.py` as a callable tool
   for self-auditing, not just something a human runs.

## What NOT to do

Don't fork this content into your own agent's config format and let the
copy drift from `core/`. If your framework needs a different format,
generate it from `core/controls.yaml` and `core/resources/` at
build/deploy time rather than hand-maintaining a translation.
