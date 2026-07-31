# Git Ops Standards

A portable, agent-agnostic standard for git workflow, code management, and
devops hygiene — from org-wide policy down to a single contributor's daily
habits. Written so it can be read and enforced by a human, by Claude Code, or
by any other agent framework — nothing in `core/` depends on a specific
tool's config format.

## Layering

- **`core/`** — generic, team-shareable. The rules and checklists here apply
  to any git-based org. No org names, no repo names, no tool-specific syntax.
  If you handed this to a different company, only `core/` would travel with
  you.
- **`estate/`** — this org's specific bindings: actual org names (SocioProphet,
  SourceOS-Linux, SociOS-Linux), the `<repo>-<feature>.wt` worktree naming
  convention actually in use, and a growing incident log of real cases where
  a `core/` rule was violated, what it cost, and how it was caught.
- **`bindings/`** — thin adapters per consumer. How to wire this standard
  into Claude Code (CLAUDE.md + memory) vs. into an arbitrary agent
  framework. The standard itself never assumes one of these.

## Why this exists

Every rule in `core/controls.yaml` was extracted from a real incident, not
written speculatively. See `estate/incident-log/` for the worked examples.
A control with no incident behind it is a guess; a control with an incident
behind it is a lesson. Keep them traceable to each other — when you add a
control, link the incident that justified it.

## Start here

- New to this repo: read `core/PARA.md`, then `core/resources/` for the
  actionable checklists.
- Wiring this into an agent: read `bindings/` for your framework.
- Auditing an estate against these controls: `scripts/estate_drift_audit.py`.
