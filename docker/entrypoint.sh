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

# Copy .claude.json — rewrite MCP server paths for container, skip onboarding
if [[ -f /host-claude.json ]]; then
  python3 -c "
import json
d = json.load(open('/host-claude.json'))
servers = d.get('mcpServers', {})
if 'waggle' in servers:
    servers['waggle'] = {'type': 'stdio', 'command': 'waggle', 'args': []}
servers.pop('bees', None)
servers.pop('bees-stdio', None)
servers.pop('bees-http', None)
# Add prod bees server for bug filing (waggle-spawned agents will inherit this)
import os
bug_url = os.environ.get('BEES_MCP_URL', 'http://host.docker.internal:8000')
servers['bees-prod'] = {'type': 'http', 'url': bug_url + '/mcp'}
d['mcpServers'] = servers
d['hasCompletedOnboarding'] = True
d.setdefault('projects', {})
d['projects']['/test-repo'] = {'hasTrustDialogAccepted': True}
json.dump(d, open('${TESTUSER_HOME}/.claude.json', 'w'), indent=2)
"
else
  echo '{"numStartups":100,"hasCompletedOnboarding":true,"mcpServers":{},"projects":{"/test-repo":{"hasTrustDialogAccepted":true}}}' > "${TESTUSER_HOME}/.claude.json"
fi

chown -R testuser:testuser "${TESTUSER_HOME}/.claude" "${TESTUSER_HOME}/.claude.json" "${TESTUSER_HOME}/.waggle" /test-repo/.claude 2>/dev/null || true

# Launch tmux as testuser with test runner + auto-approver
exec gosu testuser env PATH="/home/testuser/.local/bin:$PATH" bash -c '
  auto_approve.sh ci > /tmp/auto_approve.log 2>&1 &
  sleep 1
  tmux new-session -d -s ci /usr/local/bin/test_runner.sh
  tmux wait-for ci-done 2>/dev/null || while tmux has-session -t ci 2>/dev/null; do sleep 5; done
'
