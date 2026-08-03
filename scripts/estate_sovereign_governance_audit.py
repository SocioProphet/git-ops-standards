#!/usr/bin/env python3
"""Estate sovereign-governance audit -- implements core/controls.yaml's
sovereign-git-protection-declared, sovereign-registry-policy-enforced, and
sovereign-worktracking-native-integrated.

Read-only. Audits the desired-state of the three sovereign substrates -- git (Gitea),
registry (zot), work-tracking (agora over HellGraph) -- so governance is enforced on the
SOURCE OF TRUTH, not just the GitHub mirror. See
estate/incident-log/2026-08-03-sovereign-governance-only-on-mirror.md.

Two fact sources, kept separate so the pure logic stays hermetic:
  * COMMITTED artifacts (gh api contents across the substrate repos) -- readable with any
    token, from anywhere. This is what most hard findings key on.
  * IN-CLUSTER live state (is the Kyverno controller admitting verify-signed-images? does the
    Gitea authority's live protection match the committed spec?) -- reachable only from CI via
    WIF -> GKE. From outside the cluster these facts are UNKNOWN and reported as soft notes,
    never false hard findings; the estate-sovereign-governance workflow injects them via flags.

`evaluate()` is a pure function over an already-assembled facts dict -- see
tests/test_estate_sovereign_governance_audit.py. `main()` assembles the facts.

Usage:
    python3 estate_sovereign_governance_audit.py [--json]
    # workflow injects in-cluster results it gathered under WIF->GKE:
    python3 estate_sovereign_governance_audit.py --kyverno-installed true --gitea-live match
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from typing import Any

# Where each substrate's committed desired-state lives (source of truth is the sovereign side).
GITEA_REPO = "SocioProphet/gitea-sovereign"
PLATFORM_REPO = "SocioProphet/prophet-platform"
GIT_PROTECTION_SPEC = "governance/sovereign-repo-protection.json"          # created in gitea-sovereign (Phase 2)
ZOT_CONFIGMAP = "infra/k8s/zot/base/configmap.yaml"
KYVERNO_SIGNING = "infra/policy/cloudshell-fog/kyverno/verify-signed-images.yaml"
AGORA_VALUES = "deploy/values/agora.yaml"
AGORA_WEB_CLIENT = "apps/socioprophet-web/src/services/agoraApi.ts"


def sh(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def gh_contents(repo: str, path: str) -> str | None:
    """Raw text of a committed file, or None if it does not exist / is unreachable."""
    code, out, _ = sh(["gh", "api", f"repos/{repo}/contents/{path}"])
    if code != 0 or not out.strip():
        return None
    try:
        return base64.b64decode(json.loads(out)["content"]).decode()
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# evaluate -- pure, hermetic
# --------------------------------------------------------------------------- #
def evaluate(facts: dict[str, Any]) -> list[dict[str, Any]]:
    """facts = {'git': {...}, 'registry': {...}, 'worktracking': {...}}. Pure. Fail-closed.
    In-cluster facts that are None mean 'not verifiable here' -> soft note, never a hard finding."""
    out: list[dict[str, Any]] = []
    g, r, w = facts.get("git", {}), facts.get("registry", {}), facts.get("worktracking", {})

    # --- sovereign-git-protection-declared ---
    if not g.get("spec_present"):
        out.append(_f("high", "sovereign-git-protection-declared", "git",
                      "no committed sovereign-git protection desired-state exists "
                      f"({GITEA_REPO}/{GIT_PROTECTION_SPEC}) -- protection is GitHub-mirror-only"))
    elif g.get("spec_schema_valid") is False:
        out.append(_f("high", "sovereign-git-protection-declared", "git",
                      "committed sovereign-git protection spec is not schema-valid"))
    elif g.get("live_matches") is False:
        out.append(_f("high", "sovereign-git-protection-declared", "git",
                      "live Gitea authority protection DRIFTS from the committed spec"))
    elif g.get("live_status") in (None, "unknown", "unreachable"):
        out.append(_f("note", "sovereign-git-protection-declared", "git",
                      "committed spec present; live authority state not verifiable here "
                      "(in-cluster via WIF only)"))

    # --- sovereign-registry-policy-enforced ---
    if not r.get("configmap_present"):
        out.append(_f("high", "sovereign-registry-policy-enforced", "registry",
                      f"zot desired-state configmap missing ({PLATFORM_REPO}/{ZOT_CONFIGMAP})"))
    else:
        # tri-state: False = confirmed-bad (HIGH); None = couldn't verify from the committed
        # artifact (note, the in-cluster step confirms); True = confirmed-good (quiet).
        if r.get("retention_present") is False:
            out.append(_f("high", "sovereign-registry-policy-enforced", "registry",
                          "zot config declares no storage retention/gc policy"))
        elif r.get("retention_present") is None:
            out.append(_f("note", "sovereign-registry-policy-enforced", "registry",
                          "zot config present but retention/gc not parseable from the committed artifact"))
        if r.get("login_wall") is False:
            out.append(_f("high", "sovereign-registry-policy-enforced", "registry",
                          "zot grants anonymous access (a non-empty anonymousPolicy) -- no login-wall"))
        elif r.get("login_wall") is None:
            out.append(_f("note", "sovereign-registry-policy-enforced", "registry",
                          "zot config present but the anonymous/access posture not parseable here"))
    if not r.get("signing_policy_present"):
        out.append(_f("high", "sovereign-registry-policy-enforced", "registry",
                      f"image-signing policy file missing ({PLATFORM_REPO}/{KYVERNO_SIGNING})"))
    elif r.get("signing_installed") is False:
        out.append(_f("high", "sovereign-registry-policy-enforced", "registry",
                      "verify-signed-images policy is DECLARED but NOT INSTALLED (no Kyverno controller "
                      "admitting it) -- signature verification is not actually enforced"))
    elif r.get("signing_installed") is None:
        out.append(_f("note", "sovereign-registry-policy-enforced", "registry",
                      "signing policy present; controller-installed state not verifiable here (in-cluster only)"))

    # --- sovereign-worktracking-native-integrated ---
    if w.get("external_jira_as_sor"):
        out.append(_f("high", "sovereign-worktracking-native-integrated", "worktracking",
                      "an external Jira/Linear is configured as the system of record -- sovereign "
                      "agora-over-HellGraph must be the source of truth (external = optional connector only)"))
    if not w.get("agora_deployed"):
        out.append(_f("high", "sovereign-worktracking-native-integrated", "worktracking",
                      f"agora (sovereign work-tracking) is not deployed ({PLATFORM_REPO}/{AGORA_VALUES} absent)"))
    elif not w.get("hellgraph_backed"):
        out.append(_f("high", "sovereign-worktracking-native-integrated", "worktracking",
                      "agora is deployed but not HellGraph-backed -- work items are not native graph facts"))
    else:
        missing = [k for k in ("prophet_workspace_integrated", "sociosphere_ci_integrated", "graph_integrated")
                   if not w.get(k)]
        if missing:
            out.append(_f("note", "sovereign-worktracking-native-integrated", "worktracking",
                          "agora deployed + HellGraph-backed, but integration(s) not detected: "
                          + ", ".join(m.replace("_integrated", "").replace("_", "-") for m in missing)))
    return out


def _f(sev: str, control: str, substrate: str, detail: str) -> dict:
    return {"severity": sev, "control": control, "substrate": substrate, "detail": detail}


# --------------------------------------------------------------------------- #
# fact assembly -- committed artifacts (anywhere) + injected in-cluster facts (workflow)
# --------------------------------------------------------------------------- #
def _tri(v: str | None) -> bool | None:
    return {"true": True, "false": False, "match": True, "drift": False}.get((v or "").lower())


def _zot_posture(cm_text: str | None) -> tuple[bool | None, bool | None]:
    """(retention_present, login_wall) parsed from the zot ConfigMap's embedded config.json.
    Returns None for a fact that cannot be determined from the committed artifact (-> soft note,
    never a false hard finding). login_wall is True iff accessControl exists and NO anonymousPolicy
    anywhere grants a non-empty action set (an empty/absent anonymousPolicy == no anonymous)."""
    if not cm_text:
        return None, None
    try:
        import yaml  # provided by self-validate CI (pip install pyyaml)
    except Exception:
        return None, None
    try:
        doc = yaml.safe_load(cm_text)
        raw = (doc.get("data") or {}).get("config.json")
        cfg = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:
        return None, None

    retention = "retention" in json.dumps(cfg.get("storage", {}))

    ac = cfg.get("accessControl") or (cfg.get("http") or {}).get("accessControl")
    if not ac:
        return retention, (False if ac is not None else None)  # accessControl absent => not a login-wall / unknown
    anon_granted = False

    def scan(node):
        nonlocal anon_granted
        if isinstance(node, dict):
            if node.get("anonymousPolicy"):      # non-empty list of actions == anonymous access
                anon_granted = True
            for v in node.values():
                scan(v)
        elif isinstance(node, list):
            for v in node:
                scan(v)

    scan(ac)
    return retention, (not anon_granted)


def assemble_facts(args) -> dict[str, Any]:
    # GIT: committed protection spec present + schema-valid (best-effort JSON parse).
    git_spec = gh_contents(GITEA_REPO, GIT_PROTECTION_SPEC)
    spec_valid = None
    if git_spec is not None:
        try:
            json.loads(git_spec); spec_valid = True
        except json.JSONDecodeError:
            spec_valid = False
    git = {
        "spec_present": git_spec is not None,
        "spec_schema_valid": spec_valid,
        # live authority reconcile state is in-cluster only; workflow injects --gitea-live.
        "live_status": "ok" if args.gitea_live else "unknown",
        "live_matches": _tri(args.gitea_live),
    }

    # REGISTRY: zot configmap (retention + login-wall) + kyverno policy presence.
    cm = gh_contents(PLATFORM_REPO, ZOT_CONFIGMAP)
    retention_present, login_wall = _zot_posture(cm)
    registry = {
        "configmap_present": cm is not None,
        "retention_present": retention_present,   # tri-state
        "login_wall": login_wall,                 # tri-state
        "signing_policy_present": gh_contents(PLATFORM_REPO, KYVERNO_SIGNING) is not None,
        "signing_installed": _tri(args.kyverno_installed),  # in-cluster only; workflow injects.
    }

    # WORKTRACKING: agora deployed + HellGraph-backed + integrations.
    agora_vals = gh_contents(PLATFORM_REPO, AGORA_VALUES)
    web_client = gh_contents(PLATFORM_REPO, AGORA_WEB_CLIENT)
    worktracking = {
        "external_jira_as_sor": False,  # no committed config makes external Jira the SoR (connector-only by doctrine)
        "agora_deployed": agora_vals is not None,
        "hellgraph_backed": bool(agora_vals) and "hellgraph" in agora_vals.lower(),
        "prophet_workspace_integrated": web_client is not None,
        "sociosphere_ci_integrated": bool(agora_vals) and ("ci" in agora_vals.lower() or "sociosphere" in agora_vals.lower()),
        "graph_integrated": bool(agora_vals) and ("graph" in agora_vals.lower() or "hellgraph" in agora_vals.lower()),
    }
    return {"git": git, "registry": registry, "worktracking": worktracking}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--kyverno-installed", choices=["true", "false"],
                    help="in-cluster fact injected by the workflow: is the Kyverno controller admitting the policy?")
    ap.add_argument("--gitea-live", choices=["match", "drift"],
                    help="in-cluster fact injected by the workflow: does live Gitea protection match the committed spec?")
    args = ap.parse_args()

    facts = assemble_facts(args)
    findings = evaluate(facts)
    hard = [f for f in findings if f["severity"] == "high"]

    if args.json:
        print(json.dumps({"facts": facts, "findings": findings}, indent=2))
    else:
        print("Sovereign-governance audit (git / registry / work-tracking)\n")
        for f in sorted(findings, key=lambda x: (x["severity"] != "high", x["substrate"])):
            print(f"  [{'FAIL' if f['severity'] == 'high' else 'note'}] {f['substrate']}: {f['detail']}")
        print(f"\n{len(hard)} hard finding(s), {len(findings) - len(hard)} note(s).")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
