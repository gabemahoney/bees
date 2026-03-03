# Engineering Best Practices

A practical checklist for writing and reviewing code. Prioritize substance over style — focus on things that break, leak, or rot.

## 1. Dead & Obsolete Code

Remove it. Don't comment it out, don't leave it "just in case."

- Commented-out code blocks
- Unused functions, variables, or imports
- Old implementations left behind after a refactor
- Debugging artifacts: `print()`, `console.log()`, stray `TODO` comments

Version control is your safety net — delete with confidence.

## 2. Architecture & Design

Code should be consistent with its neighbors and no more complex than necessary.

- **Match existing patterns.** If the codebase uses a convention, follow it. Don't introduce a second way of doing the same thing.
- **Separate concerns.** Business logic, API handling, and data access belong in different layers. Don't mix them.
- **YAGNI.** Don't build abstractions for hypothetical future requirements. Three similar lines of code are better than a premature helper function.
- **Keep interfaces consistent.** If similar modules expose similar APIs, a new module should too.

## 3. Security & Correctness

These are non-negotiable. A security bug is not a "nice to have" fix.

- **Input validation:** Validate all user input at system boundaries (Pydantic models, type checks, schema validation).
- **SQL queries:** Always parameterized (`?`, `:param`). Never f-strings or string concatenation.
- **File paths:** Use `Path()`, validate against expected workspace. Never trust user-supplied paths directly.
- **Secrets:** Load from environment or config. Never hardcode API keys, passwords, or tokens.
- **Authentication:** Verify auth on every protected endpoint. Don't assume middleware handled it.
- **Error responses:** Never expose stack traces, internal paths, or sensitive data to end users.

## 4. Code Quality

Write code that the next person can read without a decoder ring.

- **Function length:** If it's over 50 lines or nests more than 3 levels deep, extract helpers.
- **DRY violations:** If you're copying a block of code, it's time for a shared function.
- **Magic values:** Named constants over mystery numbers and strings.
- **Naming:** A function's name should tell you what it does. A variable's name should tell you what it holds.
- **Comments:** Only where the logic isn't self-evident. Don't narrate the obvious.
- **Bare except clauses:** Always catch specific exceptions. `except:` hides bugs.

## 5. Error Handling

Errors are a first-class concern, not an afterthought.

- **Specific exceptions.** Catch what you expect. Let unexpected errors propagate.
- **Resource cleanup.** Files, connections, and locks should use context managers (`with` statements, try/finally).
- **Critical paths.** Any I/O, network call, or external dependency needs error handling.
- **Actionable messages.** Error messages should help the user (or the next developer) understand what went wrong and what to do about it.

## 6. Testing

Tests prove the code works. Missing tests mean you're guessing.

- **New functions need tests.** No exceptions.
- **Cover edge cases.** Empty inputs, null values, boundary conditions.
- **Test error paths.** Don't just test the happy path — verify expected exceptions are raised.
- **Keep tests accurate.** When code changes, update the tests. Stale tests are worse than no tests.
- **Test the right thing.** Each test should verify one behavior. If a test name needs "and" in it, split it.

## 7. Performance

Don't optimize prematurely, but don't create obvious bottlenecks either.

- **N+1 queries.** Database calls inside loops are almost always wrong. Batch them.
- **Memory.** Don't load entire files into memory when you can stream.
- **Connection pooling.** Reuse database connections instead of creating one per request.
- **Async discipline.** Don't use synchronous I/O inside async functions — it blocks the event loop.
- **Cache invalidation.** If you cache something, define when and how it expires.

## 8. Ticket Reads and the Cache

The ticket cache is an internal optimization inside `read_ticket()`. All code that reads ticket data must route through it.

- **Always use `read_ticket()`.** It is the only sanctioned way to load ticket data. Direct file reads that bypass `read_ticket()` are prohibited — they skip the mtime cache and will serve stale data to callers.
- **Never open ticket markdown files directly.** Constructing a `Path` to a ticket file and parsing it inline is a cache bypass. Use `read_ticket()` regardless of context (MCP handlers, pipeline loading, linting, relationship sync).
- **Cache reads and population are internal to `read_ticket()`.** Do not call `cache.get()` or `cache.put()` from production `src/` code outside `src/reader.py`. Cache population and mtime checking are managed exclusively by `read_ticket()`. Presence checks via `cache.contains()` are allowed from any module — they reveal only whether an ID is cached, not the cached data itself. Write paths may import `src.cache` solely to call `cache.evict()` after a filesystem write. Tests may import `src.cache` directly to inspect or reset cache state between test cases.

### Write-Path Rules

- **Always evict after writes.** After any `write_ticket_file()` call, evict the written ticket via `cache.evict(hive_name, ticket_id)`. Skipping eviction leaves stale data in the cache for the remainder of the server process.
- **Never populate the cache on the write path.** Write operations must not call `cache.put()`. The cache is populated lazily by `read_ticket()` on the next read. Populating on write bypasses mtime validation and can serve data that is already stale.
- **Evict related tickets during relationship sync.** Any operation that rewrites a related ticket's frontmatter (parent/child sync, dependency sync) must evict that related ticket after writing. The eviction target is the ticket whose file was written, not the ticket that triggered the sync.

## 9. Project Conventions

Every project has its own norms. Respect them.

- Check `CLAUDE.md`, `CONTRIBUTING.md`, or equivalent for documented standards.
- Follow the project's file organization and naming conventions.
- Use the project's designated linters and formatters (ruff, black, eslint, prettier, etc.).
- Match the commit message format the team uses.
- When in doubt, look at how existing code handles the same situation.

## 10. Prioritization

Not all issues are equal. When reviewing or writing code, focus in this order:

1. **Security vulnerabilities** — fix immediately
2. **Logic errors** — fix immediately
3. **Missing tests** — add before merging
4. **Architecture problems** — address in current work if feasible
5. **Code quality** — address if touched, don't go hunting
6. **Style nits** — let the linter handle it
