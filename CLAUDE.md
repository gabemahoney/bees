# Purpose of this repo

You are building the bees ticket management system but also using the bees ticket system.
Bear this in mind when talking with the user. Sometimes they will be asking you to just use bees.
Other times they will be asking you to build or debug bees.

## Bees MCP Server

The MCP server runs automatically via stdio — Claude Code manages the lifecycle.
The globally installed `bees` binary (via pipx) is used: `bees serve --stdio`.

For CI/Docker testing, the HTTP server can still be started manually:
```bash
poetry run bees serve --http > /tmp/bees_server.log 2>&1 &
```

## Documentation locations
If asked to review best practices for this project use the following documents:

### Engineering Best Practices
Architecture docs available at:  [architecture](docs%2Farchitecture)
Engineering best practices at: [engineering-best-practices.md](docs%2Fguides%2Fengineering-best-practices.md)

### Testing Best Practices
Unit test best practices at: [testing.md](docs%2Farchitecture%2Ftesting.md)
Unit Test review guide at: [test_review_guide.md](docs%2Fguides%2Ftest_review_guide.md)

### Documentation Best Practices
Doc writing and review guide at: [docs_guide.md](docs%2Fguides%2Fdocs_guide.md)

