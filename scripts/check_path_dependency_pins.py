#!/usr/bin/env python3
"""CI check implementing controls.yaml's cross-repo-path-dependency-pinned.

Scans the PR's diff for new/modified local path dependencies that cross a
repo boundary (Cargo `path = "../.."`, npm `"file:../.."`, a Python
`sys.path.insert`/`sys.path.append` pointing outside the repo) and requires
a comment within a few lines documenting which branch/ref the dependency
needs. Fails the check (exit 1) if an unpinned one is found -- this is a
blocking check, not a report.

Deliberately narrow: it only looks at lines the diff actually touched, and
only recognizes a handful of common patterns. False negatives are possible
(see git-ops-standards/README.md on control provenance) -- it catches the
literal cases from the 2026-07-31 incident, not every conceivable cross-repo
dependency mechanism.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

PATTERNS = [
    re.compile(r'path\s*=\s*"\.\./.*"'),                 # Cargo.toml path dep
    re.compile(r'"file:\.\./'),                            # npm file: dep
    re.compile(r'sys\.path\.(insert|append)\([^)]*\.\.'),  # python sys.path escape
]

PIN_HINT = re.compile(r"(branch|commit|ref|PR|pull request)", re.IGNORECASE)


def diff_added_lines(base: str, head: str) -> list[tuple[str, int, str, list[str]]]:
    """Returns (file, line_no, added_line, context_lines) for each added line."""
    out = subprocess.run(
        ["git", "diff", "--unified=3", base, head],
        capture_output=True, text=True,
    ).stdout
    results = []
    current_file = None
    new_line_no = 0
    context: list[str] = []
    for line in out.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            continue
        if line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            if m:
                new_line_no = int(m.group(1)) - 1
            context = []
            continue
        if line.startswith("+") and not line.startswith("+++"):
            new_line_no += 1
            context.append(line[1:])
            if current_file:
                results.append((current_file, new_line_no, line[1:], list(context[-6:])))
        elif line.startswith("-") and not line.startswith("---"):
            continue
        else:
            new_line_no += 1
            context.append(line[1:] if line.startswith(" ") else line)
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    args = ap.parse_args()

    added = diff_added_lines(args.base, args.head)
    violations = []
    for path, lineno, added_line, context in added:
        for pat in PATTERNS:
            if pat.search(added_line):
                nearby = "\n".join(context)
                if not PIN_HINT.search(nearby):
                    violations.append((path, lineno, added_line.strip()))
                break

    if violations:
        print("FAIL: cross-repo-path-dependency-pinned -- found unpinned path "
              "dependencies (no nearby comment naming the branch/commit/PR needed):\n")
        for path, lineno, line in violations:
            print(f"  {path}:{lineno}: {line}")
        print("\nAdd a comment above the dependency stating which branch/commit it "
              "needs (see git-ops-standards core/resources/day-to-day-git-workflow.md #8).")
        return 1

    print("OK: no unpinned cross-repo path dependencies found in this diff.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
