# Purpose of this repo

You are building the bees ticket management system but also using the bees ticket system.
Bear this in mind when talking with the user. Sometimes they will be asking you to just use bees.
Other times they will be asking you to build or debug bees.

## Bees MCP Server Management (for dev and debugging)

**First-time / after dependency changes:**
```bash
poetry install -E serve
```

**Start server:**
```bash
poetry run bees serve --http > /tmp/bees_server.log 2>&1 &
```

**Stop server:**
```bash
kill $(ps aux | grep "[b]ees serve" | awk '{print $2}')
```

**Restart server (clean):**
```bash
kill $(ps aux | grep "[b]ees serve" | awk '{print $2}') 2>/dev/null; find src -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; sleep 2 && poetry run bees serve --http > /tmp/bees_server.log 2>&1 &
```

**Check for duplicate servers:**
```bash
ps aux | grep "[b]ees serve"
```
Shows PID and start time. If multiple processes exist, kill old ones before restarting.

**Check server health:**
```bash
curl http://127.0.0.1:8000/health
```

**View logs:**
```bash
tail -f ~/.bees/mcp.log
```

**Clear pycache:**
```bash
find src -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```


## Best practices reference documentation
If asked to review best practices for this project use the following documents:

### Engineering Best Practices
Architecture docs available at:  [architecture](docs%2Farchitecture)
Engineering best practices at: [engineering-best-practices.md](docs%2Fguides%2Fengineering-best-practices.md)

### Testing Best Practices
Unit test best practices at: [testing.md](docs%2Farchitecture%2Ftesting.md)
Unit Test review guide at: [test_review_guide.md](docs%2Fguides%2Ftest_review_guide.md)

### Documentation Best Practices
Doc writing and review guide at: [docs_guide.md](docs%2Fguides%2Fdocs_guide.md)