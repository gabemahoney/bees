---
name: publish
description: Publish bees-md to PyPI. Bumps version, builds, checks, uploads, commits, and tags the release.
---

# One-Time Setup

1. **Install publish deps**: `pipx install twine` (poetry is already available)
2. **Configure PyPI credentials** — either:
   - **~/.pypirc** (works everywhere):
     ```ini
     [pypi]
     username = __token__
     password = pypi-<your-pypi-token>
     ```
   - **macOS Keychain**:
     ```bash
     security add-generic-password -s "PyPI Token" -a pypi -w "<your-pypi-token>"
     ```
   Get a token at: pypi.org → Account Settings → API tokens

# Overview

Publishes `bees-md` to the real PyPI. Handles the full release lifecycle:
bump version → build → check → upload → commit → tag → GitHub release.

**Run `/ci` first.** This skill does not run tests — it assumes CI has already passed.

# Usage

```
/publish show             # Show local and published versions
/publish major            # 0.1.3 → 1.0.0
/publish minor            # 0.1.3 → 0.2.0
/publish patch            # 0.1.3 → 0.1.4
```

The bump type is **required** for publishing. If not provided and not `show`, stop: "Usage: `/publish show|major|minor|patch`"

# Behavior

## show

If the argument is `show`:

1. Read local version from pyproject.toml:
   ```bash
   grep -m1 '^version = ' pyproject.toml | sed 's/version = "//;s/"//'
   ```

2. Fetch latest published version from PyPI:
   ```bash
   curl -sf https://pypi.org/pypi/bees-md/json | python3 -c "import sys,json; print(json.load(sys.stdin)['info']['version'])"
   ```

3. Report:
   ```
   Local  : 0.1.3
   PyPI   : 0.1.2
   ```

   If they match, add: `(up to date)`
   If local is ahead, add: `(local is ahead — ready to publish)`

Stop after reporting. Do not proceed to preflight.

## Step 1 — Preflight

1. **Bump type provided?** Must be one of: `major`, `minor`, `patch`. If not, stop: "Usage: `/publish major|minor|patch`"

2. **On main branch?**
   ```bash
   git rev-parse --abbrev-ref HEAD
   ```
   If not `main`, stop: "Must be on main to publish. Currently on <branch>."

3. **Working tree clean?**
   ```bash
   git status --porcelain
   ```
   If dirty, stop: "Working tree is not clean. Commit or stash changes first."

4. **twine installed?**
   ```bash
   twine --version
   ```
   If not: "twine not found. Run: `pipx install twine`"

5. **PyPI credentials available?**
   ```bash
   # macOS Keychain
   security find-generic-password -s "PyPI Token" -w 2>/dev/null
   # or ~/.pypirc
   grep -q '\[pypi\]' ~/.pypirc 2>/dev/null
   ```
   If neither found, stop: "No PyPI credentials found. See One-Time Setup above."

Read the current version from pyproject.toml:
```bash
grep -m1 '^version = ' pyproject.toml | sed 's/version = "//;s/"//'
```

Compute the new version by splitting `MAJOR.MINOR.PATCH` and incrementing the appropriate part:
- `major` → increment MAJOR, reset MINOR and PATCH to 0
- `minor` → increment MINOR, reset PATCH to 0
- `patch` → increment PATCH, reset nothing

6. **Version not already published?**
   ```bash
   curl -sf https://pypi.org/pypi/bees-md/<new-version>/json > /dev/null 2>&1
   ```
   If it returns 200, stop: "Version <new-version> is already published on PyPI."

7. **Stale bee check — resolved but not marked done?**

   Query the Bugs and Ideas hives for bees that are NOT in a "done" state but have a
   `github` resolver in their `reference_materials`. For each, call `show_ticket` to
   get the GitHub URL, then check if the GitHub issue is closed:

   ```bash
   gh issue view <number> --repo gabemahoney/bees --json state --jq '.state'
   ```

   If any GitHub issues are closed but their corresponding bees are still open, warn:

   ```
   Warning: These bees have closed GitHub issues but are not marked done:
     b.xxx — GH#12: <title> (bee status: <status>, GitHub: closed)
     b.yyy — GH#34: <title> (bee status: <status>, GitHub: closed)
   
   Continue anyway? (yes to proceed)
   ```

   Wait for the user to confirm. This catches bugs that were fixed in the code but
   the bee status was never updated.

Report: "Preflight passed. Bumping <current> → <new-version>."

## Step 2 — Bump version in pyproject.toml

Read the current version:
```bash
grep -m1 '^version = ' pyproject.toml | sed 's/version = "//;s/"//'
```

Update **both** version fields in `pyproject.toml` (under `[project]` and `[tool.poetry]`):
```bash
sed -i.bak "s/^version = \"<current>\"/version = \"<new>\"/" pyproject.toml && rm pyproject.toml.bak
```

Verify both fields updated:
```bash
grep '^version = ' pyproject.toml
```

Both lines must show the new version. If not, stop and report the mismatch.

Update the lock file to match:
```bash
poetry lock --no-update
```

## Step 3 — Build

```bash
rm -rf dist/
poetry build
```

On failure, stop: "Build failed. Fix errors above before publishing."

List what was built:
```bash
ls dist/
```

## Step 4 — Check

```bash
twine check dist/bees_md-<version>*
```

On failure, stop: "Twine check failed. Fix packaging errors above."

## Step 5 — Confirm with user

Show a summary:
```
Ready to publish:
  Package : bees-md <version>
  Files   : <list from dist/>
  Target  : https://pypi.org/project/bees-md/

Proceed? (yes to continue)
```

Wait for the user to confirm. If they say anything other than yes/y, stop: "Publish cancelled."

## Step 6 — Upload to PyPI

If using macOS Keychain:
```bash
twine upload \
  --username __token__ \
  --password "${PYPI_TOKEN}" \
  --non-interactive \
  dist/bees_md-<version>*
```

If using ~/.pypirc:
```bash
twine upload \
  --repository pypi \
  --non-interactive \
  dist/bees_md-<version>*
```

On failure, stop: "Upload failed. Output above."

## Step 7 — Commit and tag

Stage and commit the version bump:
```bash
git add pyproject.toml poetry.lock
git commit -m "chore: bump version to <version>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

Create an annotated tag:
```bash
git tag -a "v<version>" -m "Release v<version>"
```

## Step 8 — Push to GitHub

```bash
git push && git push --tags
```

On failure, stop: "Push failed. Output above."

## Step 9 — Create GitHub release

Create a GitHub release with auto-generated notes from merged PRs:

```bash
gh release create "v<version>" --title "v<version>" --generate-notes
```

On failure, warn but do not stop — the package is already published. Report: "Warning: GitHub release creation failed. Create manually at https://github.com/gabemahoney/bees/releases"

## Step 10 — Close resolved GitHub issues

Query the Bugs and Ideas hives for tickets that are in a "done" state (e.g. `fixed`)
and have a `github` resolver in their `reference_materials`. For each one, extract the
GitHub issue URL and check whether the issue is still open. If it is, close it with a
comment referencing the release:

```
Resolved in v<version>: https://github.com/gabemahoney/bees/releases/tag/v<version>
```

```bash
gh issue close <number> --repo gabemahoney/bees --comment "Resolved in v<version>: https://github.com/gabemahoney/bees/releases/tag/v<version>"
```

Use the bees MCP tools. Follow this exact procedure:

1. Query for fixed bugs:
   ```yaml
   stages:
     - [hive=bees_bugs, status=fixed]
   report: [title, ticket_status]
   ```

2. For each ticket ID in the results, call `show_ticket` with a **single ID** —
   one call per ticket. **Do NOT batch multiple IDs in one call.** Bulk calls
   produce responses that exceed the MCP output limit and get truncated,
   causing you to miss tickets.

3. In each `show_ticket` response, check `reference_materials` for any entry
   with `"resolver": "github"`. Extract the GitHub issue URL from the `url` field.

4. For each GitHub URL found, check if the issue is still open:
   ```bash
   gh issue view <number> --repo gabemahoney/bees --json state --jq '.state'
   ```

5. If the issue is open, close it. If it's locked, unlock first, then close
   with comment, then re-lock:
   ```bash
   gh api repos/gabemahoney/bees/issues/<number>/lock --method DELETE
   gh issue close <number> --repo gabemahoney/bees --comment "Resolved in v<version>: https://github.com/gabemahoney/bees/releases/tag/v<version>"
   gh api repos/gabemahoney/bees/issues/<number>/lock --method PUT --field lock_reason=resolved
   ```

6. Repeat for the Ideas hive with whatever "done" status it uses.

Report each issue closed:
```
Closed GitHub issues:
  #3  — colonize-hive overwrites created_at on re-registration
  #8  — test_conftest assertion path mismatch
```

If no resolved GitHub issues are found, report: "No GitHub issues to close."

On failure to close an individual issue, warn but continue with the rest.

## Step 11 — Install locally

Reinstall the newly published version via pipx:

```bash
/opt/homebrew/bin/pipx install bees-md=={version} --force
```

On failure, stop: "Local install failed. Output above."

Report:
```
Published bees-md <version> to PyPI.
  PyPI    : https://pypi.org/project/bees-md/<version>/
  Release : https://github.com/gabemahoney/bees/releases/tag/v<version>
  Installed locally via pipx.
  GitHub issues closed: <count> (or "none")
```
