---
name: file-bug-http
description: File a bug ticket against the production bees server via HTTP. Used inside Docker CI when the local bees CLI is configured for test use.
---

# File Bug via HTTP

Files a bug bee in the host's bugs hive for this repo by calling the host's bees MCP server over HTTP.

## Usage

```
/file-bug-http <test_name> <test_number> <error_details>
```

## Behavior

Run the following command, filling in the actual test name, number, and error output:

```bash
python /usr/local/bin/file_bug.py \
  --title "[ci] <TEST_NAME>" \
  --description "Test <N>: <EXPECTED>. Got: <ACTUAL>"
```

The script reads its target from the container environment. Do not pass a hive or a path yourself:
- `$BUG_SERVER_URL`: the host's bees server (set by `test_runner.sh`)
- `$BEES_BUGS_HIVE`: the hive to file into (set by `run_test.sh` from the host's hives)
- `$BEES_REPO_ROOT`: the host repo root the server picks the hives by (set by `run_test.sh`)

On success it prints `BUG FILED: b.XXXX`. Report that ticket ID to the caller.

On failure it prints `BUG FILING FAILED: <reason>`. Report that line to the caller as is. Do not
retry with another hive or path.

## Bug filing best practices

Follow the guide at `docs/guides/bug-writing.md`. Key points:
- Title: what is broken, not what you were doing — e.g. `[ci] colonize-hive fails with KeyError on trailing slash`
- Description: steps to reproduce (exact commands), environment (phase, bees version, transport), expected result, actual result (full error verbatim), and why it's a bug.
