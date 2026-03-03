# Custom Egg Resolvers

## Overview

Egg resolvers transform the `egg` field value from Bee tickets into lists of resource paths. Resolution happens automatically when tickets are read via `show_ticket`. The system:

1. Reads the Bee's `egg` field value
2. Determines which resolver to use based on your configuration
3. Invokes the resolver with the egg value
4. Returns a list of resource paths (files, directories, etc.)

This allows you to implement custom resolution logic for your project's needs — for example, resolving GUIDs to file paths, expanding ticket references, or validating resource existence.

## Resolver Contract

A custom resolver is an executable that implements this interface:

### Input (CLI Arguments)

- `--repo-root <path>` — The repository root directory path
- `--egg-value <value>` — The egg field value. Strings are passed as raw values; non-string types (objects, arrays, numbers, booleans) are JSON-encoded; `null` is passed as the string `null`.

String egg values arrive as plain text (e.g., `abc-123-def-456`). Non-string types arrive as JSON (e.g., `{"key": "value"}`).

### Output (stdout)

Your resolver must write valid JSON to stdout:

- **Success**: JSON array of strings (resource paths) or `null`
  - Example: `["path/to/file1.txt", "path/to/file2.txt"]`
  - Empty match: `[]`
  - Null case: `null`

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

Validates that the egg value is a file path that exists in the repository.
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Resolve file path egg values")
    parser.add_argument("--repo-root", required=True, help="Repository root path")
    parser.add_argument("--egg-value", required=True, help="Egg field value (raw string, or 'null')")

    args = parser.parse_args()

    egg_value = args.egg_value

    # Handle null case
    if egg_value == "null":
        print("null")
        sys.exit(0)

    # Resolve the file path
    repo_root = Path(args.repo_root)
    file_path = repo_root / egg_value

    # Check if file exists
    if not file_path.exists():
        print(f"Error: File does not exist: {egg_value}", file=sys.stderr)
        sys.exit(1)

    if not file_path.is_file():
        print(f"Error: Path is not a file: {egg_value}", file=sys.stderr)
        sys.exit(1)

    # Return the absolute path
    print(json.dumps([str(file_path.resolve())]))
    sys.exit(0)


if __name__ == "__main__":
    main()
```

Save this as `file_resolver.py`, make it executable (`chmod +x file_resolver.py`), and configure it in your bees config.

## Testing Your Resolver

Test your resolver directly from the command line before configuring it:

```bash
# Test with a valid file path
python file_resolver.py --repo-root /path/to/repo --egg-value 'src/main.py'

# Expected output:
# ["/path/to/repo/src/main.py"]

# Test with null
python file_resolver.py --repo-root /path/to/repo --egg-value 'null'

# Expected output:
# null

# Test with a non-existent file
python file_resolver.py --repo-root /path/to/repo --egg-value 'missing.txt'

# Expected output (stderr):
# Error: File does not exist: missing.txt
# Exit code: 1
```

**Note**: String egg values are passed as plain text. Use `'null'` to represent a null egg value.

## Configuration

Configure custom resolvers in `~/.bees/config.json` at three levels:

### Hive Level

Set `egg_resolver` on a specific hive to use it only for that hive:

```json
{
  "scopes": {
    "/path/to/repo": {
      "hives": {
        "my_hive": {
          "path": "/path/to/repo/.bees/hives/my_hive",
          "display_name": "My Hive",
          "created_at": "2024-01-01T00:00:00Z",
          "egg_resolver": "python /path/to/file_resolver.py",
          "egg_resolver_timeout": 10
        }
      }
    }
  }
}
```

### Scope Level

Set `egg_resolver` at the scope level to apply it to all hives in that scope:

```json
{
  "scopes": {
    "/path/to/repo": {
      "hives": {
        "hive1": { ... },
        "hive2": { ... }
      },
      "egg_resolver": "python /path/to/file_resolver.py",
      "egg_resolver_timeout": 10
    }
  }
}
```

### Global Level

Set `egg_resolver` at the top level to apply it to all scopes and hives:

```json
{
  "egg_resolver": "python /path/to/file_resolver.py",
  "egg_resolver_timeout": 10,
  "scopes": {
    "/path/to/repo1": { ... },
    "/path/to/repo2": { ... }
  }
}
```

### Timeout Configuration

`egg_resolver_timeout` (optional) specifies the maximum execution time in seconds:

- **Positive number** — Timeout in seconds (e.g., `10`, `2.5`)
- **`null`** or **omitted** — No timeout

## Resolution Order

The system uses a 4-level fallback chain to determine which resolver to use:

1. **Hive level** — Check the hive's `egg_resolver`
2. **Scope level** — Check the scope's `egg_resolver`
3. **Global level** — Check the top-level `egg_resolver`
4. **Default** — Use the built-in default resolver

### Special Value: `"default"`

Setting `egg_resolver` to `"default"` at any level **stops the fallback chain** and uses the built-in default resolver.

**Example**: Use a custom resolver globally, but override a specific hive to use the default:

```json
{
  "egg_resolver": "python /path/to/custom_resolver.py",
  "scopes": {
    "/path/to/repo": {
      "hives": {
        "special_hive": {
          "path": "...",
          "egg_resolver": "default"
        },
        "normal_hive": {
          "path": "..."
        }
      }
    }
  }
}
```

In this example:
- `normal_hive` uses the global custom resolver
- `special_hive` uses the built-in default resolver

### Default Resolver Behavior

The built-in default resolver handles egg values inline without invoking a subprocess:

- **`null`** → `null`
- **String** → `["string"]`
- **Other types** → `[json.dumps(value)]`

## Resolver Convention Comments

Resolver scripts should document the **bee creation convention** they expect — that is, what value a skill should store in the `egg` field when creating a Bee. Embed this as a `## RESOLVER CONVENTION` block in the script's module docstring.

This makes the resolver self-documenting: any skill that creates Bees can locate the configured resolver script, read its convention block, and know exactly what to put in the `egg` field.

### Standard Format

```python
#!/usr/bin/env python3
"""My custom resolver.

## RESOLVER CONVENTION

When creating a Bee from source documents, set the `egg` field as follows:
- If the docs folder contains a `.guid` file: use the GUID string inside it
- Otherwise: use the absolute file path of the docs folder
"""
```

### Writing a Skill That Follows Resolver Conventions

When writing a skill that creates Bees (e.g., a `hatch-feature` skill that reads PRD/SRD documents), the skill should:

1. **Check if an `egg_resolver` is configured** for the current scope by reading `~/.bees/config.json` and finding the matching scope's `egg_resolver` value.

2. **Read the resolver script** at that path and locate the `## RESOLVER CONVENTION` block in its docstring.

3. **Apply the documented convention** when setting the `egg` field on new Bee tickets.

If no resolver is configured, fall back to storing the raw file path.

**Example skill instruction:**

```
When creating the Bee, determine the egg value:
1. Read ~/.bees/config.json and find the egg_resolver for this scope.
2. If configured, read that script file and locate its ## RESOLVER CONVENTION block.
3. Follow the convention to set the egg field.
4. If no resolver is configured, set egg to the absolute path of the source docs.
```

## Best Practices

### Validate Early

Check input types and handle the null case explicitly at the start of your resolver:

```python
if egg_value is None:
    print("null")
    sys.exit(0)

if not isinstance(egg_value, str):
    print(f"Error: Expected string, got {type(egg_value).__name__}", file=sys.stderr)
    sys.exit(1)
```

### Use Absolute Paths

Always return absolute paths in your output to avoid ambiguity:

```python
print(json.dumps([str(file_path.resolve())]))
```

### Fail Fast with Clear Errors

Write descriptive error messages to stderr and exit immediately on failure:

```python
if not file_path.exists():
    print(f"Error: File not found: {egg_value}", file=sys.stderr)
    sys.exit(1)
```

### No Side Effects

Resolvers should be read-only operations. Don't create, modify, or delete files during resolution.

### Keep Resolvers Focused

Each resolver should handle one type of resolution logic. If you need multiple resolution strategies, create separate resolvers and configure them per-hive.

### Handle Null Explicitly

The null case is not an error — it represents "no egg value". Return `null` on stdout and exit 0:

```python
if egg_value is None:
    print("null")
    sys.exit(0)
```
