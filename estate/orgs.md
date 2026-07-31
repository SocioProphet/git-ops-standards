# This estate's orgs and conventions

The `estate/` layer's job: bind `core/`'s generic rules to this specific
estate's real names, so an agent (or a new human contributor) doesn't have
to reverse-engineer them from the directory listing.

## GitHub orgs in active use

- **SocioProphet** — primary org; most product repos (prophet-platform,
  sociosphere, socioprophet, hellgraph, ontogenesis, etc.)
- **SourceOS-Linux** — the SourceOS Linux distro + its OS-layer services
  (source-os, sourceos-boot, sourceos-continuum, sourceos-spec, agent-machine,
  homebrew-tap, etc.)
- **SociOS-Linux** — a related but distinct org (socios, speechlab,
  cloudshell-fog, socioslinux-web, SourceOS [meta-repo, not to be confused
  with SourceOS-Linux/source-os]). Genuinely separate from SourceOS-Linux —
  don't conflate the two when disambiguating a same-named repo.
- **mdheller** (personal account, not an org) — occasional personal-scope
  repos (e.g. m2-env-bootstrap).

When two orgs really do have a same-named repo (e.g. `cloudshell-fog` exists
under both SocioProphet and SociOS-Linux, as genuinely different projects):
keep the SocioProphet one under the bare name, and give the other an
explicit disambiguating name (not an `Org__repo` underscore convention —
pick a real name and keep it).

## Worktree naming in practice

The `<repo>-<feature-slug>.wt` convention (see
`core/resources/day-to-day-git-workflow.md` §2) is already the dominant
pattern across this estate — e.g. `sociosphere-gbrg-wave2.wt`,
`prophet-platform-jit-review-gate.wt` (after cleanup renamed from
`pp-reviewer.wt`), `hellgraph-rust-parallel-analytics.wt`. The violations
found in the 2026-07-31 cleanup were the exceptions, not the rule — which is
exactly why they stood out once looked for.

## Squash-merge is the estate-wide default

Every repo audited during the 2026-07-31 cleanup squash-merges PRs. Treat
`squash-merge-false-signal` (see `core/controls.yaml`) as always in effect
here — never trust a bare ahead/behind or is-ancestor check without
cross-referencing `gh pr list --head <branch> --state all`.

## No Copilot on most repos

Per prior estate policy, GitHub Copilot review is wired up on
`prophet-platform` and a small number of others, but **not** most repos
(sociosphere, ontogenesis, prophet-workspace, sourceos-continuum, and others
reviewed during 2026-07-31 had zero automated review comments — not because
the code was flawless, but because nothing was reviewing it). The
`pr-merge-gate` control's adversarial-self-review clause is the default
expectation on this estate, not the fallback case.
