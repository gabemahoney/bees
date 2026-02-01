---
id: bees-tk1
type: task
title: Sample Task - Implement Product Catalog API
description: Build RESTful API endpoints for product catalog with search and filtering
parent: bees-ep1
labels:
  - backend
  - api
  - database
up_dependencies: []
down_dependencies:
  - bees-dp1
children:
  - bees-sb1
status: in progress
priority: 1
owner: backend-team
created_at: 2026-01-30T15:10:00Z
updated_at: 2026-01-30T15:30:00Z
---

# Sample Task - Implement Product Catalog API

This task demonstrates all the Task-specific fields, including parent reference to an Epic and dependency relationships.

## Description

Build RESTful API endpoints for the product catalog:
- GET /api/products - List all products with pagination
- GET /api/products/{id} - Get single product details
- POST /api/products/search - Search with filters (category, price range, etc.)
- Database schema for products table

## Task-Specific Fields

This sample demonstrates:
- **id**: Unique identifier (bees-tk1)
- **type**: Set to "task" for implementation work
- **title**: Clear description of the work
- **description**: Detailed requirements and scope
- **parent**: Reference to parent epic (bees-ep1)
- **labels**: Task-specific tags (backend, api, database)
- **up_dependencies**: Tasks that block this one (empty in this example)
- **down_dependencies**: Tasks that this blocks (task-dep1)
- **children**: Subtasks that implement this task (will be populated when subtasks reference this as parent)
- **status**: Current progress state
- **priority**: Task priority (0-4)
- **owner**: Team or individual assigned
- **created_at**: Creation timestamp
- **updated_at**: Last modification timestamp

## Dependency Example

This task has a **down_dependency** on bees-dp1, meaning bees-dp1 is blocked by this task and cannot start until this task is completed.

## Parent-Child Relationship

This task is a child of **bees-ep1** (Sample Epic - E-commerce Platform). The parent epic's children list will include this task ID when the bidirectional relationship is established.
