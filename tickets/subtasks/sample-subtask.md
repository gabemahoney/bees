---
id: bees-sb1
type: subtask
title: Sample Subtask - Create database schema for products table
description: Design and implement the products table schema with indexes
parent: bees-tk1
labels:
  - database
  - migration
up_dependencies: []
down_dependencies: []
status: open
priority: 0
owner: alice@example.com
created_at: 2026-01-30T15:15:00Z
updated_at: 2026-01-30T15:15:00Z
---

# Sample Subtask - Create database schema for products table

This subtask demonstrates all the Subtask-specific fields, including the required parent reference to a Task.

## Description

Design and implement the products table schema:
- Create migration file for products table
- Define columns: id, name, description, price, category, inventory_count, created_at, updated_at
- Add indexes on name (for search), category (for filtering), and price (for sorting)
- Set up foreign key constraints if needed

## Subtask-Specific Fields

This sample demonstrates:
- **id**: Unique identifier (bees-sb1)
- **type**: Set to "subtask" for atomic actions
- **title**: Specific, actionable description
- **description**: Implementation details
- **parent**: Reference to parent task (bees-tk1) - REQUIRED for subtasks
- **labels**: Subtask-specific tags (database, migration)
- **up_dependencies**: Subtasks that block this one (empty in this example)
- **down_dependencies**: Subtasks that this blocks (empty in this example)
- **status**: Current state
- **priority**: Subtask priority (0-4, where 0 is highest)
- **owner**: Individual assigned (typically a person rather than a team)
- **created_at**: Creation timestamp
- **updated_at**: Last modification timestamp

## Parent Relationship

This subtask is a child of **bees-tk1** (Sample Task - Implement Product Catalog API). Subtasks MUST have a parent task - they cannot exist independently.

## Implementation Notes

Subtasks represent atomic, single-responsibility work items that are part of a larger task. They should be small enough to complete in a single work session.
