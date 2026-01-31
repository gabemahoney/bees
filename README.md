# Bees

A markdown-based ticket management system designed for LLMs.

## Overview

Bees is a markdown-based ticket management system designed specifically for LLM agents. It provides a simple, git-friendly way to track work through epics, tasks, and subtasks, making project management transparent and easily accessible to both humans and AI assistants.

## Installation

Install dependencies using Poetry:

```bash
poetry install
```

Run the test suite to verify installation:

```bash
poetry run pytest
```

## Usage

### Creating Tickets

Create epics, tasks, and subtasks using the MCP server:

```python
# Use the bees_create_ticket tool from your MCP client
bees_create_ticket(
    title="Add user authentication",
    type="epic",
    description="Implement OAuth2 login flow"
)
```

### Running Queries

Search and filter tickets by status, type, or labels:

```python
# Use the bees_query_tickets tool to find open tasks
bees_query_tickets(status="open", type="task")
```

### Running the Linter

Validate your ticket database for consistency:

```bash
poetry run python -m src.cli lint
```

## Demo Dataset

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

## Setting Up Your Project for Bees

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

## Examples

[PLACEHOLDER: This section will contain practical usage examples and common workflows. Content
to be added in subsequent tasks.]
