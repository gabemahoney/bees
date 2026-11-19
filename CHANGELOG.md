# Changelog

## Unreleased

- `show-ticket` (MCP `show_ticket`) now reports each invalid-format ID in `errors`
  with `id`, `reason: "Invalid ticket ID format"` and `error_type: "invalid_ticket_id"`,
  while still returning valid tickets in the same call. A call containing only
  invalid IDs now returns `status: success` and CLI exit 0 instead of exit 1;
  callers should inspect `errors` for per-ID failures.
