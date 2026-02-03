# Configuration Architecture

This document describes the configuration system architecture for the Bees ticket management system, covering the hive registry, name normalization rules, API design, and consistency guarantees.

## Configuration File Schema

The Bees configuration system uses `.bees/config.json` in the repository root to track hive registrations and system settings.

**Schema Structure**:
```json
{
  "schema_version": "1.0",
  "hives": {
    "normalized_name": {
      "display_name": "Display Name",
      "path": "/absolute/path/to/hive",
      "created_at": "2026-02-03T10:30:45.123456"
    }
  },
  "allow_cross_hive_dependencies": false
}
```

**Fields**:
- `schema_version`: Config format version, currently "1.0"
- `hives`: Dictionary mapping normalized hive names to HiveConfig objects
  - Key: Normalized hive name (lowercase, underscores, alphanumeric)
  - Value: HiveConfig with display_name, path, and created_at timestamp
- `allow_cross_hive_dependencies`: Boolean controlling whether dependencies can cross hive boundaries

**Implementation**: See `src/config.py` for BeesConfig and HiveConfig dataclasses, load/save functions, and validation logic.

## Hive Registry

The hive registry tracks all registered hives in the repository, mapping normalized names to their filesystem locations and metadata.

**Structure**: The `hives` dictionary in `.bees/config.json` serves as the authoritative registry:
- Keys: Normalized hive names (see Name Normalization section)
- Values: HiveConfig objects with display_name, path, and created_at fields

**Lookup Strategy**:
1. Primary: Check `.bees/config.json` hives dictionary using normalized name
2. Fallback: Scan filesystem for `.hive/identity.json` markers if config lookup fails

**Identity Markers**: Each hive directory contains `.hive/identity.json` with:
```json
{
  "normalized_name": "back_end",
  "display_name": "Back End",
  "created_at": "2026-02-03T10:30:45.123456"
}
```

**Purpose**: Identity markers provide redundancy for hive discovery and enable validation that filesystem state matches config registry.

**Operations**:
- `colonize_hive(name, path)`: Register new hive, create identity marker, write to config
- `abandon_hive(name)`: Remove from config registry, leave filesystem intact for re-colonization
- `rename_hive(old_name, new_name)`: Update config registry, regenerate ticket IDs, update identity marker

## Name Normalization

Hive names are normalized to ensure consistent identification across the system while preserving user-friendly display names.

**Normalization Rules** (`normalize_hive_name()` in `src/id_utils.py`):
1. Convert to lowercase
2. Replace spaces and hyphens with underscores
3. Remove all special characters (keep only letters, numbers, underscores)
4. Ensure name starts with letter or underscore (prefix with underscore if starts with digit)

**Examples**:
- "Back End" → "back_end"
- "front-end" → "front_end"
- "Multi Word Name" → "multi_word_name"
- "2024-project" → "_2024_project"

**Rationale**:
- **Filesystem safety**: Prevents issues with special characters in paths across platforms
- **Consistent identifiers**: Enables reliable lookups regardless of spacing/casing variations
- **Ticket ID prefixes**: Normalized names serve as ticket ID prefixes (e.g., `back_end.bees-abc`)
- **Config keys**: Normalized names are dictionary keys in `config.json`

**Collision Prevention**:
- `validate_unique_hive_name()` checks for duplicate normalized names before registration
- Display names are preserved in `HiveConfig.display_name` for UI/reports
- Users can rename display names freely as long as normalized form doesn't conflict

**Design Pattern**: Store normalized name as lookup key, display name for presentation. This allows case-insensitive, whitespace-normalized operations while preserving user intent.

## API Architecture (Dict vs Dataclass)

The config module provides two parallel APIs for different use cases: a type-safe dataclass API for strict validation, and a flexible dictionary API for graceful degradation.

### Dataclass API (Primary, Type-Safe)

**Functions**:
- `load_bees_config() -> BeesConfig | None`: Returns typed BeesConfig object with attribute access
- `save_bees_config(config: BeesConfig)`: Persists BeesConfig to disk with validation
- `init_bees_config_if_needed() -> BeesConfig`: Creates config on first call, returns existing on subsequent calls

**Use Cases**:
- Application startup and initialization
- Strict validation requirements
- IDE autocomplete and type checking
- Code that needs compile-time safety

**Error Behavior**: Raises `ValueError` on malformed JSON or schema violations for fail-fast validation.

### Dictionary API (Flexible, Graceful)

**Functions**:
- `load_hive_config_dict() -> dict`: Returns plain dict with default structure on errors
- `write_hive_config_dict(config: dict)`: Writes dict to disk with atomic guarantees

**Use Cases**:
- Scripts and automation that need robustness
- MCP layer operations requiring graceful degradation
- Dynamic configuration access where structure may vary
- Serialization/deserialization pipelines

**Error Behavior**: Returns default structure instead of raising exceptions, logs warnings for visibility.

### Design Trade-offs

**Dataclass API**:
- **Pros**: Type safety, IDE support, attribute access (`config.hives`), validation enforced
- **Cons**: Less flexible for dynamic operations, requires schema changes for new fields

**Dictionary API**:
- **Pros**: Flexible, graceful error handling, easier serialization, no schema dependency
- **Cons**: No type safety, no IDE autocomplete, runtime errors for typos

**Rationale**: Maintaining parallel APIs adds some code duplication but provides the best tool for each context. Application code uses dataclass API for safety, while MCP and scripting layers use dictionary API for resilience.

**Implementation**: See `src/config.py` for both API implementations.

## Atomic Write Strategy

Configuration writes use an atomic write-to-temp-then-rename pattern to prevent corruption from crashes or interrupted operations.

### Write Pattern

1. **Create temp file**: `tempfile.mkstemp()` in `.bees/` directory with prefix `.config.json.`
2. **Write JSON**: `json.dump()` with `indent=2` formatting and trailing newline
3. **Atomic rename**: `os.replace()` atomically moves temp file to `config.json`
4. **Cleanup on error**: Delete temp file in except block if write fails

### Consistency Guarantees

**POSIX Atomicity**: `os.replace()` uses the rename syscall, which is atomic on POSIX systems. This ensures:
- No partial file states visible to readers
- Either old config remains intact or new config is complete
- No race conditions between concurrent readers/writers

**Crash Safety**: If process crashes during write:
- Before rename: Old config remains unchanged, temp file orphaned
- After rename: New config is complete and consistent

### Rationale

Configuration corruption could render the entire system unusable. Atomic writes guarantee that config.json is always in a valid state, even during power loss or process termination.

**Error Handling**: Raises `IOError` with descriptive messages for disk space, permissions, or filesystem issues. Cleanup ensures no temp file accumulation.

**Implementation**: See `save_bees_config()` and `write_hive_config_dict()` in `src/config.py` for atomic write implementation.
