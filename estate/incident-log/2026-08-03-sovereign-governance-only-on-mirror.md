# 2026-08-03: governance-as-config was built on the mirror, not the sovereign source of truth

## Starting state

Immediately after codifying GitHub branch protection as IaC (control
`main-branch-protection-enforced`, incident 2026-08-03-advisory-ci-unprotected-main),
the obvious next question exposed the real gap: **GitHub is the mirror, not the source
of truth.** The estate's stated direction is GitHub ⇄ sovereign parity/cutover — sovereign
git is Gitea (`gitea-sovereign` L0 substrate + `prophet-platform/deploy/gitea-authority`),
sovereign registry is zot (`prophet-platform/infra/k8s/zot`), and sovereign work-tracking is
**agora** over HellGraph (the "Jira/Confluence killer", `prophet-platform/apps/agora`) — with
external Jira/Linear/GitHub-Issues only ever optional connectors. Yet the only committed,
audited desired-state governance in the estate was for GitHub repos. The sovereign substrates
that are meant to *become* the source of truth had **no unified estate-wide desired-state
control** tying their committed config to an audited, reconciled stable state.

## The concrete gaps this surfaced

- **Sovereign git (Gitea): no repo-protection desired-state exists at all.** `gitea-sovereign`
  is a deliberate non-mutating L0 scaffold (schemas + validators; `governance/` is an explicit
  *projection boundary, not authority*); `prophet-platform/deploy/gitea-authority` deploys the
  authority + Gitea but declares no per-repo protection/ruleset stable state. Live mutation is
  correctly gated behind ADR-0006 (runtime-binding gates), but the *declared* protection an
  audit would reconcile against is simply absent.
- **Sovereign registry (zot): desired-state exists but signing is unenforced.** The zot
  configmap declares retention, a login-wall (no anonymous), and pull-through sync, and ArgoCD
  reconciles it. But the Kyverno `verify-signed-images` ClusterPolicy is *written and not
  installed* (no controller connected — stated in the policy file itself), so signature
  verification is declared, not enforced: a declared control that isn't a control yet.
- **Sovereign work-tracking (agora): source-of-truth not asserted or wired as governance.**
  agora exists and is HellGraph-backed, but nothing asserts, as an audited estate control, that
  it is the sovereign source of truth (not an external Jira) and that it is integrated with
  prophet-workspace, the sociosphere CI, and the graph.

This is the same disease as `github-ci-health-current` and `main-branch-protection-enforced`:
a control that is declared but not enforced, or enforced only on the mirror, is not a control.
Governance stated only on GitHub is stated on the copy.

## The fix

A unified sovereign desired-state governance surface in `git-ops-standards` (the canonical
control plane), following the committed-spec + read-only-audit + deliberate-`workflow_dispatch`-
reconcile idiom, with credentials **minted in-cluster via WIF** (`provision-secrets.yml`),
never a static PAT, a laptop-held secret, or a standing admin App
(`ci-secrets-minted-never-static-pat`):

- controls `sovereign-git-protection-declared`, `sovereign-registry-policy-enforced`,
  `sovereign-worktracking-native-integrated`;
- `scripts/estate_sovereign_governance_audit.py` (read-only, pure `evaluate` over fetched
  substrate facts, hermetic tests) + `.github/workflows/estate-sovereign-governance.yml`
  (WIF→GKE; audit on schedule, reconcile only on a deliberate dispatch).

Reconcile against the sovereign substrates, from CI, in-cluster — so the source of truth is the
sovereign side and GitHub is treated, correctly, as the mirror.
