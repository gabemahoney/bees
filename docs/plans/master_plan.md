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
- **mcp_server.py** - FastMCP server registration and coordination (~420 lines after extraction)
- **mcp_relationships.py** - Bidirectional relationship synchronization (~400-500 lines)
- **mcp_ticket_ops.py** - Ticket CRUD operations (create, update, delete, show) (~800 lines)
- **mcp_hive_ops.py** - Hive lifecycle operations (colonize, list, abandon, rename, sanitize) (~1000 lines)
- **mcp_query_ops.py** - Query operations (add named query, execute named/freeform queries) (~250 lines)
- **mcp_index_ops.py** - Index generation operations with filtering (~64 lines)

**Utility Modules:**
- **mcp_hive_utils.py** - Hive path validation and scanning utilities
- **mcp_repo_utils.py** - Repository root detection
- **mcp_id_utils.py** - Ticket ID parsing utilities

**Query Subsystem (mcp_query_ops.py):**
Extracted from mcp_server.py as part of Epic features.bees-d6o to improve modularity and maintainability. The module provides:
- Named query registration with validation (`_add_named_query`)
- Named query execution with hive filtering (`_execute_query`)
- Ad-hoc freeform query execution without persistence (`_execute_freeform_query`)

Dependencies:
- **query_storage** - Query persistence to disk
- **pipeline** - PipelineEvaluator for query execution
- **mcp_repo_utils** - Repository root detection for hive resolution
- **config** - Hive configuration loading and validation

Integration: Functions are imported by mcp_server.py and registered as MCP tools for external access. The extraction maintains identical functionality while isolating the query subsystem for better code organization.

**Index Generation Subsystem (mcp_index_ops.py):**
Extracted from mcp_server.py as part of Epic features.bees-d6o (Task features.bees-zy7) to follow single responsibility principle. The module provides:
- Markdown index generation with filtering (`_generate_index`)
- Support for status, type, and hive_name filters
- Per-hive and all-hive index generation capabilities

Dependencies:
- **index_generator** - Core index generation logic

Integration: The `_generate_index` function is imported by mcp_server.py and registered as an MCP tool. This extraction isolates index generation as a discrete operation for better maintainability.

**Organization:**
- **mcp_hive_utils.py** handles validation/scanning
- **mcp_hive_ops.py** handles lifecycle (create, rename, delete)

## Quick Reference

For implementation details, see the architecture documentation linked above. Key integration points:

- MCP server provides HTTP transport for ticket operations (create, update, delete, query)
- Relationship synchronization maintains bidirectional consistency automatically
- Query system enables multi-stage filtering and graph traversal
- Hive-based architecture supports multi-team repositories with isolated namespaces








