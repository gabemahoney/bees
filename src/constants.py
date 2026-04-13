"""Constants used throughout the Bees ticket system."""

SCHEMA_VERSION = "0.1"

# Lowercase-only charset (34 chars)
# Excluded for visual ambiguity: 0 (zero), O, I, l
# Excluded entirely: all uppercase letters
# Allowed: 1-9, a-k, m-z
ID_CHARSET = "123456789abcdefghijkmnopqrstuvwxyz"

GUID_LENGTH = 32

# ── Per-call body size cap ────────────────────────────────────────────────────
#
# BODY_MAX_LENGTH is the maximum length (measured in Unicode codepoints, not
# bytes and not lines) of a single `body` or `chunk` argument accepted by the
# MCP write surface (`create_ticket.body`, `update_ticket.body`,
# `append_ticket_body.chunk`) and by the equivalent CLI subcommands.
#
# This cap is deliberately measured in characters because JSON Schema
# `maxLength` counts codepoints natively — the MCP schema constraint and any
# handler-side length check therefore measure the same quantity with no
# conversion.
#
# This constant is the single source of truth for enforcement: every call
# site that rejects or validates an oversized body must import it (MCP schema
# `maxLength`, CLI argparse-time checks, tests). Prose sites (docstrings, CLI
# help text, error messages) may hardcode the literal `10000` since the value
# is locked and not intended to be tuned further.
#
# Rationale (SR-1.3): target roughly 60 seconds of streaming time per chunk.
# Sonnet sustains about 50 output tokens per second, so 60 seconds buys about
# 3000 tokens. At roughly 3.5 characters per token that is about 10500
# characters, rounded down to 10000. This sits at roughly 2.5x margin under
# Claude Code's observed ~150 second streaming-stall watchdog and keeps a
# single tool-call emission well clear of the cliff that bug `b.tpe`
# characterized.
BODY_MAX_LENGTH = 10000
