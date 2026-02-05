---
id: features.bees-raw
type: task
title: Standardize assertion messages to f-strings in test_conftest.py
description: 'Inconsistent Patterns: test_conftest.py uses two different assertion
  messages - some use format strings (e.g., line 157), others use f-strings (e.g.,
  "Epic file {epic_file} should exist") - standardize to f-strings throughout'
labels:
- style
up_dependencies:
- features.bees-nkt
parent: features.bees-5va
children:
- features.bees-1ev
- features.bees-csa
- features.bees-par
created_at: '2026-02-05T09:42:55.092770'
updated_at: '2026-02-05T10:06:39.694841'
priority: 3
status: completed
bees_version: '1.1'
---

Inconsistent Patterns: test_conftest.py uses two different assertion messages - some use format strings (e.g., line 157), others use f-strings (e.g., "Epic file {epic_file} should exist") - standardize to f-strings throughout
