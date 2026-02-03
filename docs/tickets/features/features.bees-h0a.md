---
id: features.bees-h0a
type: epic
title: Need to support MCP clients that dont use roots
description: "We uses Roots https://modelcontextprotocol.io/specification/2025-06-18/client/roots\
  \ to get \nthe repo root from calling clients. We need this for any call that modifies\
  \ the repo,\nlike how colonize_creates a hive directory in the calling repo.\n\n\
  Not all MCP clients support this.\n\nWe need to provide support for those that dont.\n\
  \n- Modify the docstring for any method that needs this to explain this fallback\
  \ for clients that dont support roots\n- Provide an optional param for each method\
  \ that needs it which allows the calling client to just provide their repo root\
  \ as a string\n- Update the Readme to explain this"
children:
- features.bees-lmo
- features.bees-61r
- features.bees-uen
created_at: '2026-02-03T06:28:56.432468'
updated_at: '2026-02-03T06:41:00.530536'
status: open
bees_version: '1.1'
---

We uses Roots https://modelcontextprotocol.io/specification/2025-06-18/client/roots to get 
the repo root from calling clients. We need this for any call that modifies the repo,
like how colonize_creates a hive directory in the calling repo.

Not all MCP clients support this.

We need to provide support for those that dont.

- Modify the docstring for any method that needs this to explain this fallback for clients that dont support roots
- Provide an optional param for each method that needs it which allows the calling client to just provide their repo root as a string
- Update the Readme to explain this
