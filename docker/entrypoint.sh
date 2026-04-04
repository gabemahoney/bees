#!/bin/bash
# entrypoint.sh — Sets up the container environment and launches
# test_runner.sh inside tmux with auto_approve.sh alongside.
set -euo pipefail

TESTUSER_HOME=/home/testuser

# Set up waggle for testuser
mkdir -p "${TESTUSER_HOME}/.waggle/hooks"
if [[ -d /host-waggle/hooks ]]; then
  cp -r /host-waggle/hooks/* "${TESTUSER_HOME}/.waggle/hooks/" 2>/dev/null || true
fi

# Set up Claude CLI config — skip onboarding wizard
mkdir -p "${TESTUSER_HOME}/.claude"
if [[ -f /host-claude-settings.json ]]; then
  cp /host-claude-settings.json "${TESTUSER_HOME}/.claude/settings.json"
fi

# Build minimal .claude.json — API key auth only, no host OAuth tokens
python3 -c "
import json, os
bug_url = os.environ.get('BEES_MCP_URL', 'http://host.docker.internal:8000')
api_key = os.environ.get('ANTHROPIC_API_KEY', '')
d = {
    'numStartups': 100,
    'hasCompletedOnboarding': True,
    'projects': {'/test-repo': {'hasTrustDialogAccepted': True}},
    'mcpServers': {
        'bees-prod': {'type': 'http', 'url': bug_url + '/mcp'}
    }
}
if api_key:
    d['apiKey'] = api_key
json.dump(d, open('${TESTUSER_HOME}/.claude.json', 'w'), indent=2)
print('Created minimal .claude.json (API key auth)')
"

chown -R testuser:testuser "${TESTUSER_HOME}/.claude" "${TESTUSER_HOME}/.claude.json" "${TESTUSER_HOME}/.waggle" /test-repo/.claude 2>/dev/null || true

# Launch tmux as testuser with test runner + auto-approver
exec gosu testuser env PATH="/home/testuser/.local/bin:$PATH" bash -c '
  auto_approve.sh ci > /tmp/auto_approve.log 2>&1 &
  sleep 1
  tmux new-session -d -s ci /usr/local/bin/test_runner.sh
  tmux wait-for ci-done 2>/dev/null || while tmux has-session -t ci 2>/dev/null; do sleep 5; done
'
