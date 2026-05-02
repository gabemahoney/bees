# Custom Resolvers

## Overview

Resolvers transform `reference_materials` entry values from Bee tickets into resolved resource information. Resolution happens automatically when tickets are read via `show_ticket`. The system:

1. Reads each entry in the Bee's `reference_materials` list
2. Determines which resolver to use based on the entry's `resolver` key (defaults to `"default"`)
3. Invokes the resolver with the entry's `value`
4. Returns the original entry augmented with a `resolved` key containing the resolution result

This allows you to implement custom resolution logic for your project's needs — for example, resolving GUIDs to file paths, expanding ticket references, or validating resource existence.

## Resolver Contract

A custom resolver is an executable that implements this interface:

### Input (CLI Arguments)

- `--repo-root <path>` — The repository root directory path
- `--value <value>` — The entry's `value` field. Strings are passed as raw values; non-string types (objects, arrays, numbers, booleans) are JSON-encoded; `null` is never passed (null values short-circuit without invoking the resolver).

String values arrive as plain text (e.g., `abc-123-def-456`). Non-string types arrive as JSON (e.g., `{"key": "value"}`).

### Output (stdout)

Your resolver must write valid JSON to stdout. The output can be any JSON-compatible value:

- **Success**: Any JSON value — typically a dict with resolution results
  - Example: `{"status": "success", "resolved_path": "/absolute/path/to/file.txt"}`
  - Error case: `{"status": "error", "raw_value": "missing.txt", "error": "path does not exist"}`
- **Null case**: `null`

### Errors (stderr)

Write human-readable error messages to stderr when resolution fails.

### Exit Codes

- **0** — Success (stdout contains valid JSON)
- **Non-zero** — Failure (stderr contains error message)

The system reads stdout on success (exit 0) and stderr on failure (exit non-zero).

## Example Resolver

Here's a complete resolver that validates file paths exist:

```python
#!/usr/bin/env python3
"""File existence resolver for Bees MCP Server.

Validates that the value is a file path that exists in the repository.
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Resolve file path values")
    parser.add_argument("--repo-root", required=True, help="Repository root path")
    parser.add_argument("--value", required=True, help="Entry value (raw string)")

    args = parser.parse_args()

    value = args.value

    # Resolve the file path
    repo_root = Path(args.repo_root)
    file_path = repo_root / value

    # Check if file exists
    if not file_path.exists():
        print(f"Error: File does not exist: {value}", file=sys.stderr)
        sys.exit(1)

    if not file_path.is_file():
        print(f"Error: Path is not a file: {value}", file=sys.stderr)
        sys.exit(1)

    # Return the absolute path
    print(json.dumps({"status": "success", "resolved_path": str(file_path.resolve())}))
    sys.exit(0)


if __name__ == "__main__":
    main()
```

Save this as `file_resolver.py`, make it executable (`chmod +x file_resolver.py`), and register it with `bees set-resolver`.

## Real-World Example: GitHub Issues Resolver

The repository includes a GitHub Issues resolver at `resolvers/github_resolver.py`. It demonstrates a pattern where the resolver delegates all external data fetching to a CLI tool rather than making API calls directly.

The `value` field stores a GitHub issue or pull request URL. When resolved, the resolver invokes `gh api` to fetch the issue or PR data from the GitHub API and returns the raw JSON response.

This pattern — delegating to an external CLI tool — is useful when the tool handles authentication, host configuration, and API details on your behalf.

**PATH requirement and fail-fast behavior**: The resolver checks for `gh` on PATH before making any network calls and exits immediately with a clear error if it is not found. If you adopt this pattern, perform the tool availability check early so failures are obvious and actionable.

## Resolver Registry

The resolver registry is a named catalog of resolver scripts stored in `~/.bees/config.json` under the top-level `resolvers` key. Registering resolvers by name lets you reference them by name in `reference_materials` entries and restrict which resolvers a hive may use.

### Registering and Updating Resolvers

```
bees set-resolver --name <name> --path <absolute-path-to-script> [--timeout <seconds>]
```

- `--name`: Resolver name. Cannot be `default` (reserved).
- `--path`: Absolute path to the resolver script. Must exist on disk.
- `--timeout`: Optional execution timeout in seconds.

When registered, bees reads the script's module docstring and extracts the `## RESOLVER CONVENTION` block automatically, storing it alongside the path.

**Example**:
```
bees set-resolver --name guid_resolver --path /projects/myrepo/resolvers/guid_resolver.py --timeout 10
```

### Removing Resolvers

```
bees set-resolver --name <name> --unset
```

Fails with `resolver_in_use` if any hive's `allowed_resolvers` still references the name. Remove it from those hives first.

### Listing Resolvers

```
bees get-resolvers
```

Returns all registered resolvers plus the built-in `default` entry (always listed first). Each entry includes `name`, `path`, `timeout`, `convention`, and `built_in`.

### Built-in Default Resolver

The `default` resolver is always present in the registry. It cannot be registered or removed via `set-resolver`.

- **`built_in`**: `true`
- **`path`**: `null` (inline — no subprocess is invoked)
- **Convention**: Accepts a string file path (absolute or relative). Absolute paths are normalized with `Path.resolve()` and checked for existence. Relative paths are resolved against `repo_root` before the existence check.

When no `resolver` key is specified in a `reference_materials` entry, bees uses the default resolver.

## Per-Hive Resolver Restrictions

The `--allowed-resolvers` flag on `colonize-hive` restricts which resolvers may be used with a given hive. Each name must already exist in the resolver registry or be `"default"`.

```
bees colonize-hive --name "My Hive" --path /path/to/hive \
  --allowed-resolvers '["guid_resolver", "default"]'
```

When `allowed_resolvers` is set:
- Only the listed resolver names are valid for that hive.
- Attempting to unset a resolver that is still listed in any hive's `allowed_resolvers` returns an error — remove it from the hive first.

Omit `--allowed-resolvers` to leave the hive unrestricted.

## Using Resolvers in Tickets

Set the `resolver` key on a `reference_materials` entry when creating or updating a ticket:

```bash
# Create a bee with a GUID-resolved reference
bees create-ticket --ticket-type bee --title "My Feature" --hive backend \
  --reference-materials '[{"value": "abc-guid-123", "resolver": "guid_resolver"}]'

# Create a bee with a default (file-path) reference
bees create-ticket --ticket-type bee --title "My Feature" --hive backend \
  --reference-materials '[{"value": "src/feature.py"}]'
```

When `show-ticket` is called, each entry is resolved using its specified resolver (or `default`) and the result appears in the `resolved` key of each entry in the `reference_materials` field.

## Testing Your Resolver

Test your resolver directly from the command line before configuring it:

```bash
# Test with a valid file path
python file_resolver.py --repo-root /path/to/repo --value 'src/main.py'

# Expected output:
# {"status": "success", "resolved_path": "/path/to/repo/src/main.py"}

# Test with a non-existent file
python file_resolver.py --repo-root /path/to/repo --value 'missing.txt'

# Expected output (stderr):
# Error: File does not exist: missing.txt
# Exit code: 1
```

**Note**: String values are passed as plain text.

## Best Practices

### Validate Early

Check input types at the start of your resolver:

```python
if not isinstance(value, str):
    print(f"Error: Expected string, got {type(value).__name__}", file=sys.stderr)
    sys.exit(1)
```

### Use Absolute Paths

Always return absolute paths in your output to avoid ambiguity:

```python
print(json.dumps({"status": "success", "resolved_path": str(file_path.resolve())}))
```

### Fail Fast with Clear Errors

Write descriptive error messages to stderr and exit immediately on failure:

```python
if not file_path.exists():
    print(f"Error: File not found: {value}", file=sys.stderr)
    sys.exit(1)
```

### No Side Effects

Resolvers should be read-only operations. Don't create, modify, or delete files during resolution.

### Keep Resolvers Focused

Each resolver should handle one type of resolution logic. If you need multiple resolution strategies, create separate resolvers and reference them by name in each `reference_materials` entry.

## Resolver Convention Comments

Resolver scripts should document the **bee creation convention** they expect — that is, what value a skill should store in each `reference_materials` entry's `value` field when creating a Bee. Embed this as a `## RESOLVER CONVENTION` block in the script's module docstring.

This makes the resolver self-documenting: any skill that creates Bees can locate the configured resolver script, read its convention block, and know exactly what to put in the `value` field.

### Standard Format

```python
#!/usr/bin/env python3
"""My custom resolver.

## RESOLVER CONVENTION

When creating a Bee from source documents, set the `value` field of each
reference_materials entry as follows:
- If the docs folder contains a `.guid` file: use the GUID string inside it
- Otherwise: use the absolute file path of the docs folder
"""
```

### Writing a Skill That Follows Resolver Conventions

When writing a skill that creates Bees (e.g., a `hatch-feature` skill that reads PRD/SRD documents), the skill should:

1. **Call `get-resolvers`** (MCP) or `bees get-resolvers` (CLI) to list all registered resolvers and their conventions.

2. **Find the relevant resolver** for the current hive. Check the hive's `allowed_resolvers` field (or check what resolver names are in use on similar tickets) to determine which resolver to use.

3. **Read its convention** from the `convention` field returned by `get-resolvers` and apply it when setting the `value` field in `reference_materials` entries on new Bee tickets.

If no resolver is needed, omit the `resolver` key — the `default` resolver applies, which validates file paths.

**Example skill instruction:**

```
When creating the Bee, determine the reference_materials value:
1. Call get-resolvers to list available resolvers and their conventions.
2. Find the resolver relevant for this hive and read its convention field.
3. Follow the convention to set the value field in each reference_materials entry.
4. If no custom resolver is configured, set value to the file path of the source docs.
```
