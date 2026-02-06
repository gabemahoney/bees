---
id: features.bees-krd
type: subtask
title: Categorize lifecycle tests (server startup/shutdown/tool registration)
description: "Context: Target file test_mcp_server_lifecycle.py should contain ~400\
  \ lines of lifecycle-related tests.\n\nWhat to Categorize:\n- Tests in TestMCPServerInitialization\n\
  - Tests in TestServerLifecycle  \n- Tests in TestHealthCheck\n- Tests in TestToolRegistration\n\
  - Tests in TestErrorHandling (if server lifecycle related)\n- Tests in TestServerConfiguration\n\
  - Tests in TestModuleIntegration\n\nReview each test and determine if it tests server\
  \ initialization, startup, shutdown, health checks, or tool registration.\n\nWhy:\
  \ These tests belong in the new test_mcp_server_lifecycle.py file.\n\nAcceptance\
  \ Criteria:\n- List shows all lifecycle tests with line numbers\n- Estimate total\
  \ lines ~400 (verify against target)\n- Each test has clear rationale for categorization\n\
  \nReference: Task features.bees-4i1\nFiles: tests/test_mcp_server.py"
up_dependencies:
- features.bees-ysm
down_dependencies:
- features.bees-p2j
- features.bees-kgk
parent: features.bees-4i1
created_at: '2026-02-05T16:13:56.360113'
updated_at: '2026-02-05T16:20:38.300964'
status: completed
bees_version: '1.1'
---

Context: Target file test_mcp_server_lifecycle.py should contain ~400 lines of lifecycle-related tests.

What to Categorize:
- Tests in TestMCPServerInitialization
- Tests in TestServerLifecycle  
- Tests in TestHealthCheck
- Tests in TestToolRegistration
- Tests in TestErrorHandling (if server lifecycle related)
- Tests in TestServerConfiguration
- Tests in TestModuleIntegration

Review each test and determine if it tests server initialization, startup, shutdown, health checks, or tool registration.

Why: These tests belong in the new test_mcp_server_lifecycle.py file.

Acceptance Criteria:
- List shows all lifecycle tests with line numbers
- Estimate total lines ~400 (verify against target)
- Each test has clear rationale for categorization

Reference: Task features.bees-4i1
Files: tests/test_mcp_server.py
