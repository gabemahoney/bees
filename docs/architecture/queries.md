# Query System Architecture

## Overview

The query system provides a powerful multi-stage pipeline for filtering and traversing tickets. Queries are composed of sequential stages, where each stage either filters tickets using search terms or traverses relationships using graph terms. Results from each stage are passed to the next, enabling complex queries through simple composition.

**Source files**: `src/query_parser.py`, `src/search_executor.py`, `src/graph_executor.py`, `src/pipeline.py`, `src/parser.py`, `src/config.py`, `src/mcp_query_ops.py`

## Query Parser Architecture

### Core Design

The Query Parser (`src/query_parser.py`) validates dict-based query structures before execution, enforcing strict rules to ensure well-formed queries and providing clear error messages.

**Responsibilities**:
- Parse dict query structure (`{"stages": [...], "report": [...]}`) into validated stages and an optional report list
- Validate search terms (type=, id=, status=, title~, tag~, parent=, guid=, hive=, hive~, priority terms)
- Validate graph terms (children, parent, up_dependencies, down_dependencies)
- Enforce stage purity (no mixing search and graph terms)
- Validate regex patterns are compilable
- Validate the optional `report` list (see Report Field Projection)

### Query Format

A query is a YAML dict with a required `stages` key (a list of stages, each a list of terms) and an optional `report` key (a list of field names). Every surface that accepts a query (`--query-yaml` on the CLI, `query_yaml` on MCP tools, `undertaker_schedule.query_yaml` in config) passes the string to `yaml.safe_load` unchanged. No escape sequences are interpreted, so a literal `\n` typed in a shell stays a backslash and an `n`, and block-style YAML written that way parses as a plain string and is rejected.

The documented way to pass a query is one line of YAML flow style, single-quoted on the shell:
- `{stages: [[type=bee, status=pupa], [children]]}`
- `{stages: [[type=bee, status=pupa]], report: [title, ticket_status]}`

A term that contains `,` `[` `]` `{` `}` `:` or `#` must be double-quoted inside the flow sequence, e.g. `["title~p[0-4]"]`. YAML double quotes treat a backslash as an escape, so each regex backslash inside them is written twice: `["title~\\[bug\\]"]` becomes the regex `\[bug\]` (literal brackets), while `["title~\[bug\]"]` is a YAML parse error.

### Query Help Surfaces

Callers learn the query language from five places: `bees execute-freeform-query -h`, `bees add-named-query -h`, `bees sting`, and the MCP `execute_freeform_query` and `add_named_query` tool descriptions. Each one documents `report`, lists the reportable and non-reportable fields, shows both example queries above, and carries the priority term reference (see Priority Terms).

`src/query_parser.py` is the single source for that content: `VALID_REPORT_FIELDS`, `NON_REPORTABLE_FIELDS`, `QUERY_YAML_EXAMPLE`, `REPORT_QUERY_YAML_EXAMPLE` and `PRIORITY_TERMS_HELP`. The priority reference is defined once, in `PRIORITY_TERMS_HELP`, and all five surfaces are built from that one constant: the CLI help and the `sting` reference include it directly, and the MCP tool descriptions are filled from it (and from `VALID_REPORT_FIELDS`) by the `_inject_query_help` decorator in `src/mcp_server.py`, which replaces placeholders in the tool docstrings at import time. The priority reference is never written out by hand on any of those five surfaces. The MCP help tool (`get_help` in `src/mcp_help.py`) is not one of the five and is not built from the constants: it writes the priority terms by hand in both of its QUERIES sections, the `get_help` docstring and the `concepts` string. The constant holds no runnable `bees ...` example line, so the example-running test is unaffected. `tests/test_query_help.py` checks all five surfaces against the constants and runs every CLI example as written. When adding or removing a reportable field, change the constants only. Changing the priority reference means changing `PRIORITY_TERMS_HELP` and also updating both QUERIES sections in `src/mcp_help.py` by hand, because nothing keeps them in step with the constant. Changing a query example also means changing the MCP docstrings, which still write the examples by hand.

**Mixed versions**: Bees 0.8.4 and earlier do not know `priority`. They drop it whenever they rewrite a ticket, their linter reports it as `disallowed_field`, and they cannot run a saved named query that uses priority terms, because their parser does not recognize the terms. A named query that uses priority terms is therefore only safe on a hive where every machine and agent runs a version that knows priority.

Two pieces of query help are not built from the constants and are checked separately by the same test file:
- The doubled-backslash regex example (`["title~\\[bug\\]"]`) is written by hand in the `execute-freeform-query` help and the MCP `execute_freeform_query` description (both raw strings, so the two backslashes reach the reader). The test runs it as written on an isolated hive and checks it matches literal brackets only.
- The undertaker `query_yaml` examples in the `src/mcp_undertaker.py` module docstring and the MCP `undertaker` description must parse with `QueryParser.parse_and_validate`.

### Pipeline Execution Model

**Design Principles**:
- Stages evaluated sequentially in order
- Results from stage N passed to stage N+1
- Terms within a stage are ANDed together
- Results deduplicated after each stage
- Empty result set short-circuits pipeline

### Search Terms vs Graph Terms

**Search Terms** (filtering):
- `type=` - Exact match on ticket type (bee, t1, t2, etc.)
- `id=` - Exact match on ticket ID (e.g., `id=b.amx` or `id=t1.amx.12`)
- `status=` - Exact match on ticket status
- `title~` - Regex match on title field
- `tag~` - Regex match on any tag
- `parent=` - Exact match on parent field
- `guid=` - Exact match on ticket GUID
- `hive=` - Exact match on the hive's normalized name
- `hive~` - Regex match on the hive's normalized name
- `priority=`, `priority!=`, `priority<`, `priority<=`, `priority>`, `priority>=` - Integer comparison on the ticket's priority, plus `priority=none` for tickets with no priority (see Priority Terms)

The executor reads a term's operator as whichever of `=` and `~` comes first, so a regex pattern may contain `=` (`title~a=b`) and an exact value may contain `~` (`hive=a~b`).

**Graph Terms** (traversal):
- `parent` - Traverse to parent ticket
- `children` - Traverse to child tickets
- `up_dependencies` - Traverse to blocking dependencies
- `down_dependencies` - Traverse to blocked dependents

**Stage Purity Rule**: A stage can contain only search terms OR only graph terms, never both. This keeps execution logic clean and query semantics clear. Priority terms are search terms, so they follow the same rule: a stage holding a priority term cannot also hold a graph term. The pipeline classifies a stage as search or graph using the parser's search-term list, which includes the priority prefixes, and the unknown-term error lists those prefixes among the valid search terms.

### Priority Terms

A priority term is `priority`, then a comparison operator, then a value. It filters on the ticket's optional integer `priority` field.

**Grammar**:
- Operators are `=`, `!=`, `<`, `<=`, `>`, `>=`. The parser reads the longest operator first, so `priority<=0` is "less than or equal to 0", never `<` followed by `=0`
- The value is an ASCII integer literal with an optional leading minus sign. Negative numbers and leading zeros are accepted (`priority>=-1`, `priority=007`)
- The value `none` (lowercase only) is valid with `=` only and selects tickets with no priority. `priority=none` is the only way to query for unset priority
- A term is recognized as a priority term by its prefix (`priority=`, `priority!=`, `priority<`, `priority>`). Recognition is separate from value validation, so a malformed priority term is reported as an invalid priority term rather than as an unknown term

**Malformed terms**: A leading plus sign (`+1`), a decimal (`1.5`), whitespace, an empty value, `None` or `NONE`, and `none` with any operator other than `=` are rejected at parse time with `Stage N: Invalid priority term ...`. `add_named_query` and `execute_freeform_query` wrap it as `Invalid query structure: ...` (`parse_error`). The undertaker returns its existing query error and archives nothing.

**Matching** (`filter_by_priority` in the Search Executor):
- A numeric term matches only tickets whose stored priority is a true integer. Booleans, floats and strings never match
- An unset priority never matches a numeric term, including `priority!=N`. A query for "not priority 1" therefore excludes unset tickets; combine with `priority=none` in a separate query to see them
- `priority=none` matches exactly the unset tickets (absent, null or empty in the file) and never a ticket whose priority is 0
- A stored value that is invalid (for example a string or float written by hand into a ticket file) matches no priority term and never causes the query to fail

**Not covered**: Priority adds no result ordering; results are still sorted by ticket ID. Priority terms read the `priority` field only, so tags of the form `priority:N` are unaffected and still matched with `tag~`.

**Pipeline load**: The pipeline's one-time ticket load carries `priority` into the in-memory ticket data, with an absent, null or empty value loaded as unset.

### Regex Features Supported

- Case-insensitive flags: `(?i)beta`
- Alternation (OR): `beta|alpha|preview`
- Negative lookahead (NOT): `^(?!.*closed).*`
- Character classes: `p[0-4]`
- Anchors: `^start`, `end$`

### AND/OR Semantics

**Within a stage** (AND logic):
- All terms must match for a ticket to pass
- Example: `[type=t1, tag~beta]` finds t1 tickets AND tagged with beta

**Across stages** (sequential filtering):
- Stage 2 operates on stage 1 results
- Each stage narrows or traverses the result set
- Example: `{stages: [[type=bee], [children]]}` finds bees, then gets their children

## Search Executor Architecture

The Search Executor (`src/search_executor.py`) implements in-memory filtering of tickets using search terms with AND semantics.

### Design Overview

**Purpose**: Execute search stages from query pipeline by filtering in-memory ticket data using exact match and regex patterns.

**Key Principle**: All search terms in a stage are ANDed together - a ticket must match ALL terms to be included in results.

**Integration**: Called by PipelineEvaluator when executing search stages (stages containing only search terms).

### Architecture

**SearchExecutor Class**:
- One filter method per search term type
- One execute method (orchestrates AND logic)
- Stateless design (no instance state)
- Pure functions (no side effects)

**Data Flow**:
- Input: `Dict[str, Dict[str, Any]]` - ticket_id → ticket data
- Output: `Set[str]` - set of matching ticket IDs
- In-memory operation (no disk I/O)

### Filter Methods

1. **filter_by_type(tickets, type_value)** - Exact match on `issue_type` field
2. **filter_by_status(tickets, status_value)** - Exact match on `status` field
3. **filter_by_id(tickets, id_value)** - Exact match on ticket ID
4. **filter_by_parent(tickets, parent_value)** - Exact match on `parent` field
5. **filter_by_guid(tickets, guid_value)** - Exact match on `guid` field
6. **filter_by_hive(tickets, hive_value)** - Exact match on `hive` field
7. **filter_by_hive_regex(tickets, regex_pattern)** - Case-insensitive regex match on `hive` field
8. **filter_by_title_regex(tickets, regex_pattern)** - Case-insensitive regex match on `title` field
9. **filter_by_tag_regex(tickets, regex_pattern)** - Case-insensitive regex match on ANY tag in `tags` array
10. **filter_by_priority(tickets, term)** - Integer comparison or unset match on the `priority` field (see Priority Terms)

### Execute Method AND Logic

**execute(tickets, search_terms)** orchestrates multi-term filtering:
- Applies each filter method for corresponding search term
- Intersects results (AND logic) across all filters
- Returns set of ticket IDs matching all terms

## Graph Executor Architecture

The Graph Executor (`src/graph_executor.py`) implements in-memory traversal of ticket relationships for the query pipeline.

### Design Overview

**Purpose**: Execute graph stages by traversing ticket relationships (parent, children, dependencies) without disk I/O.

**Key Principle**: Single-hop traversal only. Multi-hop queries use multiple graph stages in sequence.

### Relationship Traversal

**Single-value relationships**:
- `parent` - Returns the parent ticket ID (or empty if none)

**List-value relationships**:
- `children` - Returns all child ticket IDs
- `up_dependencies` - Returns all blocking dependency IDs
- `down_dependencies` - Returns all blocked dependent IDs

### Architecture Decisions

**Why single-hop only**:
- Keeps executor simple and predictable
- Multi-hop queries compose multiple graph stages
- Pipeline controls traversal depth explicitly

**Why no disk I/O**:
- All tickets pre-loaded by PipelineEvaluator
- Relationship data already parsed from YAML
- Executor just looks up fields in memory
- Orders of magnitude faster than disk reads

### Integration

**traverse(tickets, relationship_type)** method:
- Takes input ticket set from previous stage
- Looks up specified relationship field in each ticket
- Collects all relationship target IDs
- Returns set of reachable ticket IDs

**Graceful error handling**:
- Missing tickets return partial results (no failure)
- Malformed relationships logged and skipped
- Time complexity: O(n) where n is input ticket count

## Named Query System

Named queries allow storing and reusing query pipelines in `~/.bees/config.json`. Queries are stored at two levels — global (top-level `queries` key) and repo scope (within a scope's `queries` key) — following the same scoped configuration model used for child_tiers and other settings. See `docs/architecture/configuration.md` (Named Queries Configuration section) for the detailed key structure, resolution order, and conflict detection rules.

### Storage Model

Named queries are persisted in config-backed storage within `~/.bees/config.json`:
- **Global queries**: Stored under the top-level `queries` dictionary. Accessible from any repo.
- **Repo-scoped queries**: Stored under a scope's `queries` dictionary. Accessible only from repos matching that scope pattern.

Repo scope queries shadow global queries of the same name. Validated queries are persisted as dicts with a `stages` key, plus a `report` key when the query had one — `{"stages": [...], "report": [...]}`. The original YAML string is not retained.

### MCP Tools

**add_named_query** — Register a new named query for reuse.
- Parameters: `name` (str, required), `query_yaml` (str, required — YAML dict with a `stages` key and optional `report` key, e.g. `{stages: [[type=bee, status=pupa]], report: [title, ticket_status]}`), `scope` (str, "global" or "repo", default: "global")
- A `report` list is validated and stored with the stages, so `execute_named_query` returns those fields
- Returns on success: `{status: "success", query_name, scope, message}`
- Returns on error: `{status: "error", error_type, message}` (see Error Types below)

**execute_named_query** — Execute a previously registered named query.
- Parameters: `query_name` (str, required)
- Returns on success (no report): `{status: "success", query_name, result_count, ticket_ids}`
- Returns on success (with report): `{status: "success", query_name, result_count, tickets}` where `tickets` is a list of field dicts
- Report behavior is determined by the `report` key stored at `add_named_query` time
- Returns on error: `{status: "error", error_type, message}` with optional `available_queries` list for `query_not_found`
- Performs pre-flight hive integrity check before execution

**delete_named_query** — Delete a named query from config-backed storage.
- Parameters: `name` (str, required)
- Returns on success: `{status: "success", query_name, message}`
- Returns on error: `{status: "error", error_type, message}`
- Cleans up the `queries` key entirely if the last query at a scope level is removed

**list_named_queries** — List named queries from config-backed storage.
- Parameters: none
- Returns queries accessible from current repo scope: matched repo-scoped queries + global queries
- Returns: `{status: "success", queries: [{name, definition, scope, repo_root}, ...], count}`

**execute_freeform_query** — One-step ad-hoc query execution without persistence.
- Parameters: `query_yaml` (str, required — YAML dict with a `stages` key and optional `report` key, e.g. `{stages: [[type=bee, status=pupa]], report: [title, ticket_status]}`)
- Returns on success (no report): `{status: "success", result_count, ticket_ids, stages_executed}`
- Returns on success (with report): `{status: "success", result_count, tickets, stages_executed}` where `tickets` is a list of field dicts
- Performs pre-flight hive integrity check before execution

### Report Field Projection

The `report` key enables field projection on query results. When omitted, queries return a sorted list of ticket IDs. When provided, queries return a list of ticket dicts containing `ticket_id` plus the requested fields.

**The `report` key**:
- Part of the query YAML, alongside `stages`. Honored by `execute_freeform_query` and by `execute_named_query` (stored at `add_named_query` time)
- The undertaker accepts the same query format; a `report` key is validated there but has no effect on archival
- Value is a list of field name strings, e.g. `[title, ticket_status]`
- `ticket_id` is silently removed from the list. A list that is empty after that (`[]` or `[ticket_id]`) is rejected with `parse_error`: `report list cannot be empty`
- A non-list value is rejected (`"report" must be a list`)
- An entry that is not a string (a nested list, number, `null` or dict) is rejected with `each "report" entry must be a field name (a string), got <type> at index <i>`
- `body` or `reference_materials` is rejected with `report field "<name>" is not available in query results; use show_ticket to retrieve it`
- Any other field not in the table below is rejected with `report field "<name>" is not recognized`

**Response format**:
- Without `report`: response contains `ticket_ids` (list of ID strings, sorted)
- With `report`: response contains `tickets` (list of dicts, one per result ticket, sorted by `ticket_id`). Each dict holds `ticket_id` plus every listed field. Unset fields come back empty or `null`: the pipeline's ticket load defaults the list fields to `[]` and `ticket_status` / `ticket_type` to `""`; other unset fields, such as `parent` on a bee, are `null`

**Output field names**: The response always uses the external/output names, not internal model field names. The reportable fields are exactly `VALID_REPORT_FIELDS` in `src/query_parser.py`.

| Output name | Notes |
|---|---|
| `ticket_id` | Always included automatically. Silently stripped if caller supplies it in the list. |
| `ticket_type` | The ticket type (bee, t1, t2, etc.) |
| `ticket_status` | The ticket's current status |
| `title` | Ticket title |
| `tags` | List of tag strings |
| `parent` | Parent ticket ID, or null |
| `children` | List of child ticket IDs |
| `up_dependencies` | List of blocking dependency IDs |
| `down_dependencies` | List of blocked dependent IDs |
| `created_at` | ISO 8601 creation timestamp |
| `schema_version` | Internal schema version string |
| `guid` | Globally unique ticket identifier |
| `hive` | The hive's normalized name (the hive directory name) |
| `priority` | The ticket's integer priority, or null when unset. A hand-edited invalid stored value is reported as read |

**Excluded fields** (`NON_REPORTABLE_FIELDS` in `src/query_parser.py`):
- `body` / `reference_materials` — Not reportable because they can be arbitrarily large. Use `show_ticket` (`bees show-ticket`) to fetch full ticket content.

### CLI Commands

All `--query-yaml` values follow the Query Format above: one single-quoted argument in YAML flow style.

**bees add-named-query --query-name NAME --query-yaml YAML [--scope {global,repo}]** — Register a named query. Scope defaults to "global". YAML must be a dict with a `stages` key and optional `report` key, e.g. `bees add-named-query --query-name pupa-titles --query-yaml '{stages: [[type=bee, status=pupa]], report: [title, ticket_status]}'`.

**bees execute-named-query --query-name NAME** — Execute a previously registered named query. Report behavior is determined by the stored query definition.

**bees delete-named-query --query-name NAME** — Delete a named query. Searches all scopes automatically.

**bees list-named-queries** — List accessible named queries from current repo scope and global.

**bees execute-freeform-query --query-yaml YAML** — Execute an ad-hoc YAML query without persistence. YAML must be a dict with a `stages` key and optional `report` key for field projection, e.g. `bees execute-freeform-query --query-yaml '{stages: [[type=bee, status=pupa], [children]]}'`.

### Error Types

| Error Type | Condition |
|---|---|
| `query_not_found` | Query name does not exist at any accessible level (repo scope or global). Response includes `available_queries` list. |
| `query_out_of_scope` | Query exists but belongs to a different repo's scope and is not accessible from the caller's scope. |
| `query_name_conflict` | A query with the same name already exists. Returned by `add_named_query` when conflict detection finds a collision. Includes `conflict_level` and `conflict_location`. |
| `scope_not_found` | No registered scope in config matches the caller's repo root. Returned when `scope="repo"` but the repo has no scope entry. |
| `invalid_scope` | The scope parameter is not "global" or "repo". |

### Query Validation

Queries are validated at registration time to provide immediate feedback on structural errors:
- YAML syntax validation
- Query structure validation (a dict with a `stages` key)
- Stage structure validation
- Search term syntax validation
- Graph term validation
- Regex pattern compilation
- `report` list validation

`add_named_query` and `execute_freeform_query` return validation failures with `error_type: "parse_error"` and a message starting `Invalid query structure:`. Any other error raised while parsing is also returned as `parse_error`, with a message starting `Failed to parse query:`, so neither tool raises on bad input.

### Hive Filtering

The query tools take no hive filter parameter. To limit a query to certain hives, put a `hive=` or `hive~` term in a search stage, e.g. `{stages: [[type=bee, hive=backend]]}` or `{stages: [[type=bee, hive~^(backend|frontend)$]]}`.

### Named vs Freeform Queries

**Named queries**:
- Two-step process: register with `add_named_query`, execute with `execute_named_query`
- Persists to `~/.bees/config.json` (global or repo scope) for reuse
- Manageable via `delete_named_query` and `list_named_queries`
- Suitable for production queries used repeatedly

**Freeform queries**:
- One-step process: `execute_freeform_query` validates and executes immediately
- No persistence
- Suitable for ad-hoc exploration and debugging

## Pipeline Execution Flow

1. **Load tickets once** - PipelineEvaluator loads all tickets into memory at initialization
2. **Execute stages sequentially** - For each stage:
   - Detect stage type (search or graph)
   - Route to appropriate executor (SearchExecutor or GraphExecutor)
   - Pass results to next stage
   - Short-circuit if results empty
3. **Deduplicate and return** - Return final set of matching ticket IDs
4. **Shape the response** - The query tool returns the IDs sorted as `ticket_ids`, or, when the query has a `report` list, projects them into `tickets` (see Report Field Projection)

### Optimization Strategies

- **Batch loading**: Tickets loaded once and reused across all stages
- **Set-based deduplication**: Automatic via set data structure
- **Short-circuit evaluation**: Stop processing when any stage returns empty results
- **In-memory operations**: Zero disk I/O after initial load
