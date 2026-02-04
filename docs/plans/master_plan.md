# Bees Master Plan

## System Overview

Bees is a markdown-based ticket management system designed for simplicity and human readability. All tickets are stored as markdown files with YAML frontmatter, organized into hives (isolated directories), and managed through an MCP server interface.

The system operates without databases, daemons, or caches, making it lightweight and easy to understand. Design constraints include: no external dependencies for storage, no background processes, and a practical limit of tens of directories and thousands of tickets. This constraint-driven architecture enables git-based workflows and direct file editing while maintaining referential integrity through bidirectional relationship synchronization.

Core capabilities include multi-stage query pipelines for filtering and traversing ticket relationships, hive-based namespacing for multi-team repositories, and automatic index generation for navigation. The architecture prioritizes explicit operations, fail-fast validation, and clear error messages over automatic recovery.

## Architecture Documentation

Detailed technical documentation is organized into focused architecture documents:

- [**Design Principles**](../architecture/design_principles.md) - Core design philosophy and constraints
- [**Configuration**](../architecture/configuration.md) - Config system, hive registry, and normalization
- [**Storage**](../architecture/storage.md) - Hive structure, flat storage, and schema versioning
- [**Relationships**](../architecture/relationships.md) - Bidirectional sync and dependency management
- [**Queries**](../architecture/queries.md) - Multi-stage pipeline and query execution
- [**MCP Server**](../architecture/mcp_server.md) - HTTP transport and tool interfaces
- [**Validation**](../architecture/validation.md) - Linter architecture and corruption detection
- [**Testing**](../architecture/testing.md) - Test organization and coverage strategy

## Module Organization

The codebase is organized into focused modules following separation of concerns:

**Core Infrastructure Modules:**
- **mcp_server.py** - FastMCP server registration and coordination (~700 lines after extraction)
- **mcp_relationships.py** - Bidirectional relationship synchronization (~400-500 lines)
- **mcp_ticket_ops.py** - Ticket CRUD operations (create, update, delete, show) (~800 lines)
- **mcp_hive_ops.py** - Hive lifecycle operations (colonize, list, abandon, rename, sanitize) (~1000 lines)

**Utility Modules:**
- **mcp_hive_utils.py** - Hive path validation and scanning utilities
- **mcp_repo_utils.py** - Repository root detection
- **mcp_id_utils.py** - Ticket ID parsing utilities

**Organization:**
- **mcp_hive_utils.py** handles validation/scanning
- **mcp_hive_ops.py** handles lifecycle (create, rename, delete)

## Quick Reference

For implementation details, see the architecture documentation linked above. Key integration points:

- MCP server provides HTTP transport for ticket operations (create, update, delete, query)
- Relationship synchronization maintains bidirectional consistency automatically
- Query system enables multi-stage filtering and graph traversal
- Hive-based architecture supports multi-team repositories with isolated namespaces








