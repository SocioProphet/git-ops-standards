#!/usr/bin/env python3
"""Estate branch-protection audit -- implements core/controls.yaml's
main-branch-protection-enforced.

Read-only. For every first-party repo that DECLARES its branch protection in
a committed `.github/branch-protection.main.json`, checks that the repo's live
default-branch protection actually MATCHES that declared spec. The spec is the
source of truth; live protection drifting from it (or being absent entirely) is
the finding -- the class of problem from 2026-08-03, when main's fail-closed
gate was applied imperatively (`gh api PUT`), invisible and undriftable, and was
later observed to have silently drifted (enforce_admins flipped off out of band).
See estate/incident-log/2026-08-03-advisory-ci-unprotected-main.md.

Scope discipline (same as github-ci-health-current): the ONLY hard findings are
for repos that have OPTED IN by committing a spec. A repo with no spec is not
nagged -- absence of a spec is a note at most, never a high-severity failure --
so the check is precise, not a wolf-crying "every repo must be protected" sweep.

The detection logic (`evaluate`) is a pure function over already-fetched
spec/live pairs so it can be tested hermetically -- see
tests/test_estate_branch_protection_audit.py. `main()` does the real `gh` calls.

Token scope: reading LIVE protection needs `administration: read`; the committed
SPEC needs only `contents: read`. When the token can't read live protection
(HTTP 403) the repo is reported as a soft note ("cannot verify"), never a false
high finding -- coverage degrades gracefully exactly like estate_ci_health_audit.

Usage:
    python3 estate_branch_protection_audit.py --org SocioProphet [--json]
    python3 estate_branch_protection_audit.py --org SocioProphet --repos cybernetic-genesis
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from typing import Any

SPEC_PATH = ".github/branch-protection.main.json"

# The protection fields this estate enforces, normalized from BOTH the PUT-body
# spec shape and the GET-protection live shape into one comparable dict.
ENFORCED_FIELDS = (
    "strict",
    "contexts",
    "enforce_admins",
    "required_linear_history",
    "allow_force_pushes",
    "allow_deletions",
    "required_conversation_resolution",
    "required_reviews",
)


def sh(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def sh_json(args: list[str], timeout: int = 30) -> Any:
    code, out, _ = sh(args, timeout)
    if code != 0 or not out.strip():
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------- #
# normalization -- pure
# --------------------------------------------------------------------------- #
def _norm_spec(spec: dict) -> dict:
    """Canonical comparable dict from a PUT-body spec (branch-protection.main.json)."""
    rsc = spec.get("required_status_checks") or {}
    reviews = spec.get("required_pull_request_reviews")
    return {
        "strict": bool(rsc.get("strict", False)),
        "contexts": sorted(rsc.get("contexts") or []),
        "enforce_admins": bool(spec.get("enforce_admins", False)),
        "required_linear_history": bool(spec.get("required_linear_history", False)),
        "allow_force_pushes": bool(spec.get("allow_force_pushes", False)),
        "allow_deletions": bool(spec.get("allow_deletions", False)),
        "required_conversation_resolution": bool(spec.get("required_conversation_resolution", False)),
        "required_reviews": None if reviews is None else int((reviews or {}).get("required_approving_review_count", 0)),
    }


def _norm_live(live: dict) -> dict:
    """Canonical comparable dict from a GET branches/{b}/protection response
    (nested `{enabled: ...}` shape), which differs from the PUT body."""
    rsc = live.get("required_status_checks") or {}
    contexts = rsc.get("contexts")
    if contexts is None:  # newer API returns checks[].context
        contexts = [c.get("context") for c in (rsc.get("checks") or [])]
    reviews = live.get("required_pull_request_reviews")
    return {
        "strict": bool(rsc.get("strict", False)),
        "contexts": sorted(contexts or []),
        "enforce_admins": bool((live.get("enforce_admins") or {}).get("enabled", False)),
        "required_linear_history": bool((live.get("required_linear_history") or {}).get("enabled", False)),
        "allow_force_pushes": bool((live.get("allow_force_pushes") or {}).get("enabled", False)),
        "allow_deletions": bool((live.get("allow_deletions") or {}).get("enabled", False)),
        "required_conversation_resolution": bool((live.get("required_conversation_resolution") or {}).get("enabled", False)),
        "required_reviews": None if reviews is None else int((reviews or {}).get("required_approving_review_count", 0)),
    }


def _diff(spec_norm: dict, live_norm: dict) -> list[str]:
    return [
        f"{k}: spec={spec_norm[k]!r} live={live_norm[k]!r}"
        for k in ENFORCED_FIELDS
        if spec_norm[k] != live_norm[k]
    ]


# --------------------------------------------------------------------------- #
# evaluate -- pure, hermetic (what the test exercises)
# --------------------------------------------------------------------------- #
def evaluate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """records: [{repo, default_branch, spec, live_status, live}]
      spec        : PUT-body dict, or None if the repo declares no spec
      live_status : 'ok' | 'absent' (unprotected) | 'forbidden' (token scope) | 'error'
      live        : GET-protection dict when live_status == 'ok', else None
    Only repos that DECLARED a spec can produce a HIGH finding. Pure."""
    findings: list[dict[str, Any]] = []
    for r in records:
        repo, spec, status = r["repo"], r.get("spec"), r.get("live_status")

        if spec is None:
            if status == "ok":
                findings.append(_note(repo, "main is protected but no committed "
                                             f"{SPEC_PATH} declares it -- codify it (undeclared protection)"))
            continue  # no spec, no live protection -> repo hasn't opted in; stay quiet

        # spec present -> it is the source of truth and MUST be enforced.
        if status == "absent":
            findings.append(_high(repo, f"declares {SPEC_PATH} but main is UNPROTECTED "
                                        "(spec not enforced -- fail-closed gate is advisory)"))
        elif status == "forbidden":
            findings.append(_note(repo, "declares a spec but live protection is unreadable "
                                        "(token lacks administration:read) -- cannot verify"))
        elif status == "ok":
            drift = _diff(_norm_spec(spec), _norm_live(r["live"]))
            if drift:
                findings.append(_high(repo, "live protection DRIFTS from the committed spec: "
                                            + "; ".join(drift)))
        else:  # 'error'
            findings.append(_note(repo, "could not fetch live protection (transient/unknown) -- not verified"))
    return findings


def _high(repo: str, detail: str) -> dict:
    return {"control": "main-branch-protection-enforced", "severity": "high", "repo": repo, "detail": detail}


def _note(repo: str, detail: str) -> dict:
    return {"control": "main-branch-protection-enforced", "severity": "note", "repo": repo, "detail": detail}


# --------------------------------------------------------------------------- #
# fetch layer -- the only part that needs network
# --------------------------------------------------------------------------- #
def list_first_party_repos(org: str) -> list[str]:
    data = sh_json(["gh", "repo", "list", org, "--limit", "500",
                    "--json", "name,isFork,isArchived"], timeout=60)
    if not data:
        return []
    return sorted(r["name"] for r in data if not r["isFork"] and not r["isArchived"])


def _default_branch(slug: str) -> str | None:
    v = sh_json(["gh", "repo", "view", slug, "--json", "defaultBranchRef"])
    return (v or {}).get("defaultBranchRef", {}).get("name")


def fetch_spec(slug: str, ref: str) -> dict | None:
    code, out, _ = sh(["gh", "api", f"repos/{slug}/contents/{SPEC_PATH}?ref={ref}"])
    if code != 0 or not out.strip():
        return None  # 404 => no committed spec
    try:
        payload = json.loads(out)
        return json.loads(base64.b64decode(payload["content"]).decode())
    except Exception:
        return None


def fetch_live(slug: str, ref: str) -> tuple[str, dict | None]:
    code, out, err = sh(["gh", "api", f"repos/{slug}/branches/{ref}/protection"])
    if code == 0 and out.strip():
        try:
            return "ok", json.loads(out)
        except json.JSONDecodeError:
            return "error", None
    blob = (err or "") + (out or "")
    if "404" in blob or "Not Found" in blob or "Branch not protected" in blob:
        return "absent", None
    if "403" in blob or "Forbidden" in blob or "not accessible" in blob:
        return "forbidden", None
    return "error", None


def fetch_record(org: str, repo: str) -> dict[str, Any]:
    slug = f"{org}/{repo}"
    ref = _default_branch(slug)
    if not ref:
        return {"repo": repo, "default_branch": None, "spec": None, "live_status": "error", "live": None}
    spec = fetch_spec(slug, ref)
    status, live = fetch_live(slug, ref)
    return {"repo": repo, "default_branch": ref, "spec": spec, "live_status": status, "live": live}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", default="SocioProphet")
    ap.add_argument("--repos", help="comma-separated repo names, skip org-wide listing")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    repos = args.repos.split(",") if args.repos else list_first_party_repos(args.org)
    if not repos:
        print(f"No first-party repos found for org '{args.org}' (or `gh` call failed).", file=sys.stderr)
        return 1

    records = [fetch_record(args.org, r) for r in repos]
    findings = evaluate(records)
    hard = [f for f in findings if f["severity"] == "high"]
    declared = sum(1 for r in records if r["spec"] is not None)

    if args.json:
        print(json.dumps({"scanned": len(repos), "declared_specs": declared, "findings": findings}, indent=2))
    else:
        print(f"Scanned {len(repos)} first-party repos in {args.org} ({declared} declare a protection spec)")
        print(f"Findings: {len(findings)} ({len(hard)} high-severity)\n")
        for f in sorted(findings, key=lambda x: (x["severity"] != "high", x["repo"])):
            print(f"  [{'FAIL' if f['severity'] == 'high' else 'note'}] {f['repo']}: {f['detail']}")

    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
