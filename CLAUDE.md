# Purpose of this repo

You are building the bees ticket management system but also using the bees ticket system.
Bear this in mind when talking with the user. Sometimes they will be asking you to just use bees.
Other times they will be asking you to build or debug bees.

## Bees MCP Server

The MCP server runs automatically via stdio — Claude Code manages the lifecycle.
The globally installed `bees` binary (via pipx) is used: `bees serve --stdio`.

For CI/Docker testing, `/ci` checks for the host bees HTTP server on `BEES_CI_PORT` (default 8473) and starts it itself if nothing is listening there.

## Documentation Locations

- **Engineering best practices**: docs/guides/engineering-best-practices.md
- **Internal architecture docs**: docs/architecture/ (start with docs/architecture/design_principles.md)
- **Customer-facing docs**: README.md (PyPI copy: docs/PYPI_README.md)
- **Test writing guide**: docs/architecture/testing.md (pytest fixture reference: tests/TESTING.md)
- **Test review guide**: docs/guides/test_review_guide.md
- **Doc writing guide**: docs/guides/docs_guide.md

## Test Commands

- **Unit test command**: `poetry run pytest tests/`
- **Integration test command**: `/ci` (Claude Code skill in .claude/skills/ci). It publishes the current code to test.pypi, then runs `docker/run_test.sh <phase>` per phase in Docker, where `docker/test_runner.sh` runs each phase with either `tests/integration.sh` or Claude + `/release-test`. Do NOT run `tests/integration.sh` directly on the host: it refuses to run outside the container's `/test-repo` and it overwrites `~/.bees/config.json`.

