# Removing the exposed database credential from git history

**Status: procedure only. Nothing here has been run, and it must not be run (or anything pushed) without a separate review and explicit approval.** A history rewrite changes every commit SHA after the
first affected commit and requires a force-push, so it is done by the repository owner, once, deliberately.

## What was exposed

| Item | Where | Commits |
|---|---|---|
| RDS endpoint, admin username and password | `backend/backend/DATABASE.py` | added with the secret in `dedab48`; emptied in `a3797fd`, so `HEAD` looks clean but history still holds it |
| SQLite databases (user rows, password hashes) | `backend/database-1`, `database-1` | `60a3412`, `fd976a6` |
| A third-party PDF | `backend/local_storage/uploads/Unit 5_Testability - Charles H. Roth.pdf` | an early commit |
| Personal AI prompt notes | `backend/up`, `ideal_frontend.md` | `a709b34` and others (not secret, but not meant to be public) |

The password is **not** repeated in this document on purpose.

## Step 0 — Rotate or revoke first (required; confirm before continuing)

1. Change the RDS master password in AWS (or delete the instance if it is disposable).
2. Check for misuse: RDS event/log history and CloudTrail for logins from addresses you do not recognise;
   confirm the security group no longer allows `0.0.0.0/0` on port 3306.
3. Treat the old password as permanently public. Rewriting history does not un-leak it from forks,
   clones, GitHub's cached views, or search indexes. **Rotation is the fix; the rewrite is hygiene.**
4. If the same password was reused anywhere else, change it there too.

## Step 1 — Back up everything, including local-only work

`origin/main` and local `main` are identical (`b265a16`), but `upgrade/tier1` holds **11 commits that exist
only on this machine**, plus uncommitted files (README rewrite, AUDIT.md, CLAUDE.md, docs/). A fresh clone of
GitHub contains none of that, so the rewrite must start from the local repository.

```bash
# 1. Uncommitted work: commit or copy it out first (git stash does not survive a re-clone).
cd D:/Arishem/Arishem && git status --short          # expect: README.md, AUDIT.md, CLAUDE.md, LICENSE, docs/
cp -r D:/Arishem/Arishem D:/Arishem-folder-backup    # full copy incl. .git and ignored local files

# 2. A bundle with every local ref (restores both main and upgrade/tier1 on its own).
git bundle create ../Arishem-all-refs.bundle --all
git bundle verify ../Arishem-all-refs.bundle

# 3. A mirror of what GitHub has right now (rollback target).
git clone --mirror https://github.com/abhishekkamble12/Arishem.git ../Arishem-github-backup.git
```

Keep these outside any repo and private (they contain the secret).

## Step 2 — Rewrite a clone of the LOCAL repository

Install [git-filter-repo](https://github.com/newren/git-filter-repo) (`pip install git-filter-repo`).

```bash
# --bare copies branches as branches (main, upgrade/tier1) and tags; --no-local forces a real copy.
git clone --bare --no-local D:/Arishem/Arishem ../Arishem-clean.git
cd ../Arishem-clean.git
git branch -a                      # must list main AND upgrade/tier1

git filter-repo --invert-paths   --path backend/backend/DATABASE.py   --path backend/database-1   --path database-1   --path backend/local_storage   --path backend/up   --path ideal_frontend.md
```

The 11 `upgrade/tier1` commits are rewritten along with `main`, so they stay descendants of the cleaned `main`.
`filter-repo` removes the `origin` remote on purpose so nothing can be pushed by accident.

Optionally also scrub the literal password from any file or message: put `literal:THE_OLD_PASSWORD==>REMOVED`
in a `replacements.txt` stored outside the repo and add `--replace-text replacements.txt`.

## Step 3 — Verify before pushing

Run all of these in `Arishem-clean.git`; every one must come back empty / as stated.

```bash
# 1. The paths are gone from all history
git log --all --oneline -- backend/backend/DATABASE.py backend/database-1 database-1 backend/local_storage backend/up

# 2. The secret string is gone (substitute the real old password; do not paste it into shared logs)
git log --all -p -S'THE_OLD_PASSWORD' --oneline | head

# 3. Pattern scan over the full history
pip install gitleaks 2>/dev/null || true            # or download the gitleaks binary
gitleaks detect --source . --log-opts="--all" --redact

# 4. Content is otherwise intact: tree at the tip should differ only by the removed paths
git --git-dir=D:/Arishem/Arishem/.git rev-parse upgrade/tier1
git rev-parse upgrade/tier1                           # SHA will differ; that is expected
git --git-dir=D:/Arishem/Arishem/.git ls-tree -r --name-only upgrade/tier1 | sort > /tmp/before.txt
git ls-tree -r --name-only upgrade/tier1 | sort > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt                  # expect no output (those paths were already untracked on upgrade/tier1)
git log --oneline main..upgrade/tier1 | wc -l         # expect 11 (or more, if you add commits)
```

## Step 4 — Push (the destructive step)

Only after Step 3 is clean and the password is rotated.

```bash
git remote add origin https://github.com/abhishekkamble12/Arishem.git
git push --force origin main upgrade/tier1          # name branches explicitly; never --mirror from this repo
```

If `main` is branch-protected on GitHub, temporarily allow force-pushes, then re-enable protection.
Delete or recreate any stale branches (`upgrade/tier1`, PR heads) — they still point at old commits.

Then on GitHub:
- Contact GitHub Support to purge cached views/PR refs (`refs/pull/*` keep old commits until they are
  garbage-collected): <https://support.github.com> → "Remove sensitive data".
- Close PR #1's stale refs if it still exposes the old commits.
- Re-enable secret scanning / push protection under Settings → Code security.

## Step 5 — Everyone re-syncs (collaborators, other machines, CI)

The password must be treated as compromised and rotated (Step 0) regardless. Old clones still hold the secret and, if pushed, would reintroduce it. Do not `git pull`/merge.

```bash
# Safest: re-clone
mv Arishem Arishem-old && git clone https://github.com/abhishekkamble12/Arishem.git
# Move any unpushed work over by hand (cherry-pick patches from Arishem-old), then delete Arishem-old.
```

Forks: ask owners to delete and re-fork; GitHub cannot rewrite forks for you.
Local working copy at `D:\Arishem\Arishem`: its history still contains the secret. After the push, re-clone from
GitHub (which now has the rewritten `main` and `upgrade/tier1`), copy over the uncommitted files from
`D:/Arishem-folder-backup` (README.md, AUDIT.md, CLAUDE.md, docs/, `.venv`, `frontend/node_modules`, ignored notes),
then delete the old folder and the backups (they hold the secret) once you are satisfied.

## Step 6 — Prevent recurrence

- `gitleaks` in pre-commit and CI (Phase 2 follow-up).
- GitHub secret scanning + push protection.
- Secrets only in the host's environment / secret manager; `.env.example` holds names, never values.

## Rollback

GitHub refs: `cd Arishem-github-backup.git && git push --force --mirror https://github.com/abhishekkamble12/Arishem.git`
(this restores the leaked history, so only use it if the rewrite broke something and the password is already rotated).
Local-only work: `git clone Arishem-all-refs.bundle restored` recreates `main` and `upgrade/tier1` exactly.
