# Day-to-Day Git Workflow

The concrete answer to "how do I do X." If a developer (human or agent) has
to guess how to name a branch, whether to rebase or merge, or where a
checkout should live, this document failed. Every rule below exists because
its absence caused a real problem — see the incident reference at the end of
each section.

## 1. Naming

**Repo directory name = the repo name, exactly, lowercase-with-hyphens,
no prefix.** Not the org name, not an abbreviation, not a project codename.

- Right: `sourceos-boot`, `agent-machine`, `homebrew-tap`
- Wrong: `SourceOS-Linux__sourceos-boot` (org-prefixed), `pp-reviewer` (abbreviated),
  `hellgraph_dl` (an ad-hoc variant name for a repo that's actually `hellgraph`)

One clone directory per repo, period. If you need the org for disambiguation
(two different orgs really do have a same-named repo), put the org in the
name explicitly and keep it there forever — don't let a coincidental
underscore convention (`Org__repo`) stand in for a real decision.

**Never** create a second local clone of a repo you already have checked out
just because you're not sure where the first one is. Find it first
(`find ~/dev -name ".git" -execdir git remote get-url origin \; 2>/dev/null | grep <repo>`).

*Incident: 12 duplicate-remote groups found in one estate sweep — three
separate clones of `.github` alone. See `estate/incident-log/2026-07-31-estate-cleanup.md`.*

## 2. Worktrees — when and how

Use a linked worktree (`git worktree add`), never a second `git clone`, when
you need to work on more than one branch of the same repo at once. A second
clone doubles disk, drifts independently, and (as of this standard) is a
naming-collision generator.

**Worktree directory name:** `<repo>-<short-feature-slug>.wt` — the `.wt`
suffix is load-bearing, not decorative: it's how a human (or a script) can
tell at a glance "this directory is disposable once the branch merges,"
distinct from a permanent second checkout.

- Right: `sociosphere-gbrg-wave2.wt`, `prophet-platform-jit-review-gate.wt`
- Wrong: `pp-reviewer.wt` (abbreviated repo name — which repo? which branch?),
  `wt-source-os-rollback-loud` (prefix instead of suffix, obscures the repo name)

**Definition of done for a worktree:** its branch is merged (or its PR is
explicitly closed as abandoned) AND it has zero unpushed commits. Both
conditions, checked freshly (`git fetch` first — see §7), before removal.

**Before `git worktree remove`:** check whether anything else in the estate
has a **path dependency** on this exact worktree directory (see §8). A
worktree being "merged" doesn't mean it's safe to delete if another repo's
build points a relative path at it.

*Incident: deleting `hellgraph-rust` (confirmed-merged by branch/PR status)
broke `gbrg-core`'s Cargo.toml, which path-depended on that exact directory
name for an *unmerged* sibling crate. Confirmed-merged and safe-to-delete are
not the same fact.*

## 3. Checkout

`git clone` once, to the canonical bare name, directly under the standard
dev root (`~/dev/<repo>`, not nested inside another project). Don't clone
into a temp directory "to look at something" and then forget about it —
that's how `_prwork`, `_gbrg_recon`, and half a dozen `*_from_home` /
`*_reupload` staging directories accumulated. If you need a throwaway
checkout for a one-off investigation, put it under a directory that makes
its disposability obvious (`/tmp/`, or a clearly-named `_scratch/` you
actually clean up), not a bare project-shaped name sitting next to real work.

## 4. Branching

**Branch name = `<type>/<short-slug>`.** Types in use across this estate:
`feat/`, `fix/`, `chore/`, `docs/`, `test/`, `security/`, `rescue/` (recovered
uncommitted work), `capture/` (automated safety-net snapshot, not meant to be
worked on further), `backup/` (pre-risky-operation snapshot).

One branch, one concern. Don't let a branch drift to cover unrelated work
just because it was already checked out — that's how `_sp_docs_restore`'s
`feat/marketing-signin-button` ended up containing four unrelated "unify
apps" commits alongside its original scope.

**Before creating a branch:** fetch and branch from the current tip of the
target's default branch, not from whatever your local clone happened to have
cached. A branch built on stale `main` produces exactly the add/add
conflicts and duplicate-file situations covered in §6.

## 5. Push / Pull

**Push early, push often.** An uncommitted or unpushed piece of work only
exists on one machine, in one process's memory, one crash away from gone.
This is not a style preference — see §9's account-exhaustion incident.

**Before pushing a new branch:** run whatever the repo's local gate is
(`make validate`, `pytest`, `cargo test --workspace`) — not to guarantee CI
passes (see §10, run in a different environment than yours), but to catch
the class of error that's identical everywhere (real logic bugs, real syntax
errors).

**Pull with `--ff-only` for a checkout you're not actively developing on**
(e.g., the primary worktree of a repo you mostly consume). A merge commit
you didn't intend to create is worse than an error telling you to rebase.

**Before assuming a branch is "N commits behind, 0 ahead" (i.e., safe/stale):
fetch first.** A cached remote-tracking ref can be arbitrarily stale, and
"ahead of origin" is frequently a false signal on a squash-merge workflow —
see §7.

## 6. Rebasing vs. merging vs. cherry-picking

- **Rebase your own feature branch onto the target's current tip** before
  opening a PR, if it's more than a few commits behind. This is what avoids
  the add/add conflicts in §4.
- **Cherry-pick specific commits onto a fresh branch off current main**
  when your branch has some commits already merged (via an earlier,
  differently-scoped PR) mixed with commits that are still unique. Don't try
  to rebase/resolve the whole branch — isolate exactly what's new.
- **Never rewrite history on a branch other people (or other agent sessions)
  might be building on.** `--force-with-lease`, never bare `--force`, and
  only on a branch you're certain is exclusively yours.

*Incident: PR built on pre-merge commits from an already-merged sibling PR
produced an add/add conflict on two files. Fix was a fresh branch off
current main + `git cherry-pick` of just the one genuinely-unique commit,
not a manual conflict resolution of the whole branch.*

## 7. Stash

Use `git stash` for a genuine "I need to switch context for 5 minutes and
come back" — not as a substitute for a commit. A stash is not pushed
anywhere; it is exactly as fragile as an uncommitted change, and stashes are
easy to forget entirely once you've switched branches twice.

If you're stashing because you're about to do something destructive
(rebase, reset, a branch switch that might conflict): commit to a
throwaway `wip/` branch and push it instead. That survives a crashed
process; a stash on disk does not survive an account/session boundary the
same way a pushed branch does.

## 8. Cross-repo dependencies

If repo B's build/test needs repo A's code via a local path dependency
(Cargo `path =`, a relative Python `sys.path` insert, an npm `file:`
reference): the path must resolve to a **name that's part of this standard's
naming convention**, and a comment at the dependency declaration must say
*which branch/commit* repo A needs to be at, not just "assume it exists."

For CI, the equivalent is an explicit second `actions/checkout` step with a
named `path:`, checked out to a pinned ref — see
`estate/incident-log/2026-07-31-estate-cleanup.md` for the working pattern.
A path dependency that only resolves on one person's machine because of
what else happens to be checked out there is not a dependency, it's a bet.

## 9. Capture before delete

Before deleting anything — a worktree, a stale clone, a whole directory —
confirm the content is **actually recoverable from git history**, not just
"probably merged." The bar, in order of strength:
1. The exact commit is an ancestor of the target's current default branch
   (strongest — content is definitely already integrated).
2. The branch is pushed to origin and has a PR (open or merged) referencing
   it (recoverable, and there's a paper trail).
3. The branch is merely pushed to origin, no PR (recoverable, but check
   whether anyone else knows it exists).
4. Anything else — not safe to delete. Push it first.

**Squash-merge workflows make (1) and "ahead of upstream" checks lie to
each other.** A squash-merged branch is permanently "ahead of its own
tracking ref" (new commit hash on the target) and permanently "not an
ancestor" of the target (same reason) — neither check alone tells you
whether the *content* is safe. Cross-check against the actual PR state
(`gh pr list --head <branch> --state all`) before trusting either signal.

*Incident: an entire estate sweep initially flagged ~250 branches as
"possibly stranded" using ahead/behind and ancestor checks. Cross-referencing
actual PR merge state found all but 5 were already false alarms.*

## 10. Before merging a PR

1. **CI is green**, or every failure is understood and either (a) fixed, or
   (b) confirmed as an unrelated environment flake (e.g., a transient network
   error during a scanning tool's init step) — never merge past a failure
   you haven't looked at.
2. **Review comments are addressed**, not dismissed. If the repo has an
   automated reviewer (Copilot or equivalent), read every comment — an empty
   comment body doesn't mean nothing to do; check for inline comments too
   (`gh api repos/<org>/<repo>/pulls/<n>/comments`).
3. **If there's no automated reviewer on this repo, do an adversarial
   self-review before merging** — read your own diff as if it were someone
   else's, specifically hunting for what it breaks, not just confirming what
   it adds.
4. **Mergeable state is `MERGEABLE`, not `CONFLICTING`**, checked fresh. A
   PR that was mergeable when opened can silently become conflicting as the
   target moves.
