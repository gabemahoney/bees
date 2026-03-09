# Bug Writing Guide

A good bug report lets someone reproduce and fix the issue without asking follow-up questions.

## Required Fields

**Title**: Short, specific, and descriptive. State what is broken, not what you were doing.
- Bad: "colonize-hive broke"
- Good: "colonize-hive fails with KeyError when path contains a trailing slash"

**Description**: Use this structure:

### Steps to Reproduce
Numbered steps, exact commands included. Be specific — every flag, every argument.

```
1. Start bees HTTP server: `bees serve --http`
2. Create a hive: `bees colonize-hive --name bugs --path /tmp/myproject/bugs/`
3. Note the trailing slash on the path
```

### Environment
Where and how this happened:
- bees version (`bees --version`)
- Transport: CLI / stdio / HTTP
- OS and Python version if relevant
- Any relevant prior state (existing hives, config, ticket counts)

### Expected Result
What should have happened.

### Actual Result
What actually happened. Include the full error message or unexpected output verbatim.

### Why This Is a Bug
If it's not obvious, explain why the actual result is wrong — what contract or documented behavior it violates.

## Tips

- One bug per ticket. If you found two issues, file two tickets.
- If you can't reproduce it reliably, say so and describe what you tried.
- Attach the relevant ticket ID if the bug only surfaces with a specific ticket.
- For CI failures: include the phase number, test number, and the exact command that failed.
