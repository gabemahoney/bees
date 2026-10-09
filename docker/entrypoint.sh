#!/bin/bash
# entrypoint.sh — Sets up the container environment and launches
# test_runner.sh inside tmux with auto_approve.sh alongside.
set -euo pipefail

TESTUSER_HOME=/home/testuser

# Claude CLI settings: the container's own (docker/claude-settings.json, copied into the image),
# never the host's. Only the permission rules the release-test phases need to run unattended,
# including the MCP servers registered in the container: bees, bees-stdio, bees-http and bees-prod.
mkdir -p "${TESTUSER_HOME}/.claude"
cp /usr/local/share/bees-ci/claude-settings.json "${TESTUSER_HOME}/.claude/settings.json"

# Build minimal .claude.json — skips the onboarding wizard, embeds the API key when no OAuth token
# is set. When CLAUDE_CODE_OAUTH_TOKEN is in the env the CLI reads it directly; embedding
# apiKey in .claude.json alongside would override the OAuth token.
python3 -c "
import json, os
bug_url = os.environ.get('BEES_MCP_URL', 'http://host.docker.internal:8473')
api_key = os.environ.get('ANTHROPIC_API_KEY', '')
oauth_token = os.environ.get('CLAUDE_CODE_OAUTH_TOKEN', '')
d = {
    'numStartups': 100,
    'hasCompletedOnboarding': True,
    'projects': {'/test-repo': {'hasTrustDialogAccepted': True}},
    'mcpServers': {
        'bees-prod': {'type': 'http', 'url': bug_url + '/mcp'}
    }
}
if api_key and not oauth_token:
    d['apiKey'] = api_key
json.dump(d, open('${TESTUSER_HOME}/.claude.json', 'w'), indent=2)
print('Created minimal .claude.json ({})'.format('OAuth env' if oauth_token else 'API key auth'))
"

chown -R testuser:testuser "${TESTUSER_HOME}/.claude" "${TESTUSER_HOME}/.claude.json" /test-repo/.claude 2>/dev/null || true

# Launch tmux as testuser with test runner + auto-approver.
# The session stays open after the test runner exits, so its last output (the PASSED or
# BUG FILED line /ci polls for) stays on screen. TEST RUNNER EXITED marks a runner that ended:
# without one of those lines above it, /ci treats the phase as crashed instead of waiting.
exec gosu testuser env PATH="/home/testuser/.local/bin:$PATH" bash -c '
  auto_approve.sh ci > /tmp/auto_approve.log 2>&1 &
  sleep 1
  tmux new-session -d -s ci "/usr/local/bin/test_runner.sh; echo \"TEST RUNNER EXITED (status \$?)\"; exec sleep infinity"
  tmux wait-for ci-done 2>/dev/null || while tmux has-session -t ci 2>/dev/null; do sleep 5; done
'
