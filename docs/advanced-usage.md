# Advanced Usage

Tickets are stored as simple markdown files with yaml front-matter for metadata.
Suggested usage is for LLMs to create tickets (to keep metadata integrity) while humans view and modify the markdown.

## Hives

Bees supports grouping tickets into hives which are simply folders where a group of related tickets are stored.
Each ticket is stored in its own directory within the hive, with child tickets nested as subdirectories.

When you create new tickets you should tell the LLM which Hive to create them in.
Modifying or deleting tickets does not require you to specify the Hive.

> [!TIP]
> Its a good idea to disallow your LLM agents from reading or writing to your hive directories. Otherwise, LLMs may route around bees and potentially write malformed tickets.



## Ticket Hierarchy

Tickets can have any levels of descendants. The default is one top level ticket type which is always called a
`bee`.
Tell your LLM if you want to set up more levels of hierarchy. They can be per repo or global for all repos.

## Directory Structure

The hierarchy is expressed on disk in the hive folder:

```
hive_root/
  b.amx/
    b.amx.md
    t1.amx.12/
      t1.amx.12.md
      t2.amx.12.49/
        t2.amx.12.49.md
```

- Each ticket is a directory containing its `.md` ticket file.
- Directory name matches ticket ID
- Child tickets are subdirectories of their parent
- Bees (top-level tickets) are directories at hive root (e.g b.amx)

## Index

Each Hive can have an `index.md` file which a human can use to navigate and view that Hive's tickets. Generate it on demand via `bees generate-index` or the MCP `generate_index` tool. If you have an undertaker schedule configured in HTTP mode, the index is regenerated automatically after each archival run.

## Dependencies

Tickets can depend on other tickets of the same type only (Bees depend on Bees, t1 on t1, t2 on t2, etc.).
Dependencies work across any hive.

## Tags

Tickets support a `tags` field — a list of string tags for categorizing and filtering work. Tags can be set on creation, replaced entirely, or updated incrementally by adding and removing individual values.

## Ticket Status

Any string is valid as a status.

You can lock down allowed values per-hive or per-scope with `status_values` in `~/.bees/config.json`. When configured, updates with invalid statuses are rejected. See [Configuration](#configuration).

## Eggs

Each ticket has an optional `egg` field for arbitrary structured data — any JSON value (object, array, string, number, boolean, or null). A common use case is storing a list of file paths relevant to the ticket.

### Egg Resolvers

A custom script can be configured to resolve egg values at read time. Tell your LLM to set an egg resolver when creating a hive or by updating the configuration. See [Configuration](#configuration) and [Custom Resolvers](custom-resolvers.md).

## Undertaker

The undertaker archives completed bee tickets by moving them out of the active hive into a `/cemetery` directory, where they are excluded from all normal operations and queries. You can run it manually by telling your LLM to run the undertaker on a hive with a query that matches the tickets to archive.

When running bees as an HTTP server, the undertaker can also be scheduled to run automatically. Tell your LLM to configure an undertaker schedule on a hive with an interval and a query. See [Configuration](#configuration).

## Named Queries

Queries can be saved by name and reused across sessions. Tell your LLM to create a named query with a name and a YAML query pipeline. Once registered, you can ask your LLM to run it by name, optionally scoped to specific hives.

## Configuration

All configuration can be done by the LLM through bees commands. The following is for reference if you want to inspect it yourself.

Bees uses a single global config file at `~/.bees/config.json`, auto-created when you create your first hive.

### Scopes

Scopes map repository paths to their settings. When you run a bees command, bees finds the first scope whose path pattern matches your current repo.

Path patterns support glob wildcards:
- Exact path: matches one specific repo
- `*` matches within a single directory segment
- `**` matches recursively

First matching scope wins. `colonize_hive` creates exact-path entries automatically.
To share config _across_ worktrees or related repos, ask your LLM to update the scope key in `~/.bees/config.json` to a wildcard pattern.

```json
{
  "scopes": {
    "/Users/username/projects/myrepo": { ... },
    "/Users/username/projects/**": { ... }
  }
}
```

### Hives

Each scope contains a `hives` map — the ticket folders registered for that repo.

```json
{
  "scopes": {
    "/Users/username/projects/myrepo": {
      "hives": {
        "features": {
          "path": "/Users/username/projects/myrepo/tickets/features",
          "display_name": "Features",
          "created_at": "2026-02-03T04:15:00.000000"
        },
        "bugs": {
          "path": "/Users/username/projects/myrepo/tickets/bugs",
          "display_name": "Bugs",
          "created_at": "2026-02-03T04:15:00.000000"
        }
      }
    }
  }
}
```

### Ticket Hierarchy (child_tiers)

By default only top-level tickets (bees) exist. You can configure child tiers to add hierarchy — e.g. `Bee → Epic → Task`.

`child_tiers` can be set at three levels. For a given hive, the first defined level wins:

1. **Hive-level** — applies only to that hive
2. **Scope-level** — default for all hives in the scope
3. **Global-level** (top-level in config.json) — default for all scopes

If `child_tiers` is absent at a level, resolution falls through to the next. An empty `{}` stops the chain (bees-only for that hive).

Use `bees set-types` (or the `set_types` MCP tool) to modify `child_tiers` at any level without manually editing `~/.bees/config.json`.

Say you have a repo with three hives: a **bugs** hive where simple bug reports don't need hierarchy, a **features** hive where each bug is grouped under an Epic, and a **refactor** hive where Epics are broken into Tasks. Each hive gets its own `child_tiers` config, overriding the global default (bees-only):

- **bugs** — bees only (explicit `{}` stops fallthrough)
- **features** — bees + epics
- **refactor** — bees + epics + tasks

```json
{
  "scopes": {
    "/Users/username/projects/myrepo": {
      "hives": {
        "bugs": {
          "path": "...",
          "child_tiers": {}
        },
        "features": {
          "path": "...",
          "child_tiers": {
            "t1": ["Epic", "Epics"]
          }
        },
        "refactor": {
          "path": "...",
          "child_tiers": {
            "t1": ["Epic", "Epics"],
            "t2": ["Task", "Tasks"]
          }
        }
      }
    }
  },
  "child_tiers": {}
}
```

### Status Values

Lock down allowed status values per-scope or per-hive:

```json
{
  "scopes": {
    "/path/to/repo": {
      "status_values": ["pupa", "larva", "worker", "finished"]
    }
  }
}
```

Set allowed values at global, repo scope, or hive level:

```bash
bees set-status-values --scope=global --values '["pupa","larva","worker","finished"]'
bees set-status-values --scope=repo_scope --values '["todo","in_progress","done"]'
bees set-status-values --scope=hive --hive backend --values '["open","closed"]'
bees set-status-values --scope=global --unset
```

View raw status_values at all configuration levels:

```bash
bees get-status-values
```

### Egg Resolver

Configure a custom script to resolve egg values at read time. Resolution falls through the same hierarchy as `child_tiers`: hive → scope → global.

```json
{
  "scopes": {
    "/path/to/repo": {
      "egg_resolver": "/path/to/resolve_eggs.sh",
      "egg_resolver_timeout": 5
    }
  }
}
```

### Undertaker Schedule

HTTP mode supports scheduled auto-archival. Add an `undertaker_schedule` block to any hive:

```json
{
  "scopes": {
    "/path/to/repo": {
      "hives": {
        "backend": {
          "path": "...",
          "undertaker_schedule": {
            "interval_seconds": 3600,
            "query_yaml": "- ['status=finished']"
          }
        }
      }
    }
  }
}
```

The scheduler starts automatically when `bees serve --http` starts. Use `query_name` instead of `query_yaml` to reference a named query.

### delete_with_dependencies

Boolean flag (default `false`) that controls dependency cleanup when tickets are deleted. When `true`, deleting a ticket automatically removes its ID from any surviving tickets' `up_dependencies` and `down_dependencies` fields before deletion. When `false` (default), dangling references are left in place and can be detected by the linter.

This is a **global-only** setting — it cannot be set at scope or hive level.

```json
{
  "delete_with_dependencies": true,
  "scopes": { ... }
}
```

### auto_fix_dangling_refs

Boolean flag (default `false`) that controls whether `sanitize-hive` automatically removes dangling dependency and parent references. When `true`, `sanitize-hive` rewrites ticket files to remove references to non-existent tickets and records each fix in the response. When `false` (default), dangling references are only reported as errors.

This is a **global-only** setting — it cannot be set at scope or hive level.

Each fix is recorded in `fixes_applied` in the `sanitize-hive` response:
- `remove_dangling_dependency`: A non-existent ID was removed from `up_dependencies` or `down_dependencies`
- `clear_dangling_parent`: A non-existent parent ID was cleared (set to null)

```json
{
  "auto_fix_dangling_refs": true,
  "scopes": { ... }
}
```

## Ticket ID Format

All tickets use type-prefixed format: `{type_prefix}.{shortID}`

**Format by tier:**
- Bee (t0): `b.XXX` (3-char) — Examples: `b.amx`, `b.x4f`
- t1: `t1.XXX.XX` — Example: `t1.amx.12`
- t2: `t2.XXX.XX.XX` — Example: `t2.amx.12.49`
- Tier N: segments separated by periods, 2 chars per child tier

**Character set:** Modified Crockford Base32 — 34 lowercase characters: `1–9, a–k, m–z` (excludes `0`, `O`, `I`, `l`, and all uppercase)

Child IDs embed the parent's short ID as a prefix (hierarchical): bee `b.amx` → T1 `t1.amx.12` → T2 `t2.amx.12.49`.

## Capacity Limits

- **Maximum bees**: 39,304 across all hives. When exhausted, attempting to create a new bee returns the error "Too many bees."
- **Maximum children per parent**: 1,156 per parent ticket. When exhausted, ticket creation fails with an error identifying the parent at capacity.


## Ticket Operations

```bash
bees create-ticket --type bee --title "Bug fix" --hive backend
bees show-ticket b.amx t1.amx.12
bees update-ticket b.amx --status worker --tags '["urgent"]'
bees update-ticket b.amx --add-tags '["reviewed"]' --remove-tags '["urgent"]'
bees delete-ticket b.amx
bees get-types
bees set-types --scope global --tiers '{"t1":["Epic","Epics"]}'
bees set-types --scope repo_scope --tiers '{"t1":["Task","Tasks"]}'
bees set-types --scope hive --hive backend --tiers '{}'
bees set-types --scope global --unset
bees get-status-values
bees set-status-values --scope=global --values '["pupa","worker","finished"]'
bees set-status-values --scope=hive --hive features --values '["pupa","worker"]'
bees set-status-values --scope=global --unset
```

`show-ticket` and `delete-ticket` accept multiple IDs. `update-ticket` accepts multiple IDs when using `--status`, `--add-tags`, or `--remove-tags` (batch updates do not support `--title`, `--description`, or `--egg`).

## Query Operations

```bash
bees add-named-query open-bees --yaml "- ['type=bee', 'status=open']" [--scope {global,repo}]
bees execute-named-query open-bees [--hives backend,frontend]
bees delete-named-query open-bees --scope global
bees list-named-queries [--all]
bees execute-freeform-query --yaml "- ['type=bee']" [--hives backend]
```

## Hive Management

```bash
bees colonize-hive --name Backend --path /abs/path [--child-tiers '{"t1":["Task","Tasks"]}']
bees list-hives
bees abandon-hive backend
bees rename-hive old_name new_name
bees sanitize-hive backend
```

## Utilities

```bash
bees generate-index [--status open] [--type bee] [--hive backend]
bees clone b.amx
bees clone b.amx --hive other-hive
bees clone b.amx --hive other-hive --force
bees move-bee b.amx b.x4f --destination backlog
bees move-bee b.amx b.x4f --destination backlog --force
bees undertaker --hive backend --yaml "- ['status=finished']"
```

### Move Bee

`bees move-bee <bee-ids> --destination <hive>` moves one or more bee tickets to a different hive within the same scope. Bee IDs are preserved — only the directory location changes.

Cross-hive moves check that the source tree's status values and tier types are compatible with the destination hive's configuration. If incompatibilities are found, the move is rejected with a `compatibility_error` and no bees are moved. Pass `--force` to skip the compatibility check and move regardless.

### Clone

`bees clone <bee-id>` creates a deep copy of a bee and its full child-tier subtree, assigning fresh IDs, GUIDs, and timestamps. Internal cross-references are remapped to the new IDs; external references are preserved.

By default the clone lands in the source bee's own hive. Use `--hive <hive-name>` to clone into a different hive — source and destination must be in the same scope. Before writing, bees checks that the source tree's status values and tier types are compatible with the destination hive's configuration. If incompatibilities are found, the clone is rejected with a `compatibility_error` listing the offending values. Pass `--force` to skip that check and clone regardless.

### Cemetery

The undertaker archives bee tickets by moving them into a `/cemetery` directory inside the hive, renaming them by GUID for stable long-term identity. The cemetery is excluded from all normal ticket operations and queries — archived tickets are effectively read-only from bees' perspective.

## YAML Query Syntax

Queries are pipelines of filter stages. Each stage narrows the result set from the previous stage. Terms within a stage are ANDed. A stage can contain only search terms OR only graph terms, never both.

### Search Terms

| Term | Match |
|------|-------|
| `type=VALUE` | Exact match on ticket type (`bee`, `t1`, `t2`, etc.) |
| `id=VALUE` | Exact match on ticket ID |
| `status=VALUE` | Exact match on status |
| `parent=VALUE` | Exact match on parent ticket ID |
| `title~REGEX` | Regex match on title |
| `tag~REGEX` | Regex match on any tag |

### Graph Terms

| Term | Traversal |
|------|-----------|
| `children` | Traverse to child tickets |
| `parent` | Traverse to parent ticket |
| `up_dependencies` | Traverse to blocking tickets |
| `down_dependencies` | Traverse to blocked tickets |

### Examples

Filter by type and status:
```yaml
- ['type=bee', 'status=larva']
```

AND logic — multiple filters in one stage:
```yaml
- ['type=bee', 'status=larva', 'tag~urgent']
```

Get children of a specific ticket:
```yaml
- ['id=b.amx']
- ['children']
```

Find open bees then get their children:
```yaml
- ['type=bee', 'status=larva']
- ['children']
```

Find siblings (go up then down):
```yaml
- ['id=t1.amx.12']
- ['parent']
- ['children']
```

Two-hop dependency chain:
```yaml
- ['id=b.amx']
- ['up_dependencies']
- ['up_dependencies']
```

### Named Queries

Named queries are stored in `~/.bees/config.json` alongside other bees configuration. Queries can be registered at two levels: **global** (accessible from any repo) or **repo scope** (accessible only from repos matching that scope). Repo-scoped queries shadow global queries of the same name.

### Mermaid Charts

The hive index can include Mermaid dependency graphs. To enable them globally:

```json
{
  "mermaid_charts": true
}
```

Set at the top level of `~/.bees/config.json`. Defaults to `false` when absent.
