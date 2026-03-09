---
name: file-bug-http
description: File a bug ticket against the production bees server via HTTP. Used inside Docker CI when the local bees CLI is configured for test use.
---

# File Bug via HTTP

Files a bug bee in the production `bugs` hive by calling the host's bees MCP server over HTTP.

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

The script uses `$BUG_SERVER_URL` (set by the Docker entrypoint) to reach the host's bees server.

On success it prints `BUG FILED: b.XXXX`. Report that ticket ID to the caller.

## Bug filing best practices

Follow the guide at `docs/guides/bug-writing.md`. Key points:
- Title: what is broken, not what you were doing — e.g. `[ci] colonize-hive fails with KeyError on trailing slash`
- Description: steps to reproduce (exact commands), environment (phase, bees version, transport), expected result, actual result (full error verbatim), and why it's a bug.
