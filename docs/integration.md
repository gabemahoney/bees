# Integration Guide

This guide covers integrating bees into your project, testing with demo data, and
validating your ticket structure.

## Using bees in your project

To use bees in your project, create the following directory structure in your project root:

```
/your-project
  /tickets              # Ticket storage directory
    /epics              # Epic tickets go here
    /tasks              # Task tickets go here
    /subtasks           # Subtask tickets go here
```

The bees library expects this `/tickets` directory structure to exist in your current working
directory and will use it for all ticket read/write operations.

## Testing and development

Generate sample tickets for testing and development:

```bash
poetry run python scripts/generate_demo_tickets.py
```

This creates:
- 5 epics (auth system, dashboard, API core, docs, mobile app)
- 8 tasks with dependency chains
- 15 subtasks across various statuses

Use cases:
- Testing query and filter operations
- Validating dependency resolution logic
- Demonstrating ticket hierarchy and relationships
- Generating test data for linter validation

## Validation

Validate your ticket database for consistency:

```bash
poetry run python -m src.cli lint
```
