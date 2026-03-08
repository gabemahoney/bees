#!/bin/bash

# Auto-approve permission requests in tmux session (pane 0 only)
SESSION="${1:?Usage: $0 <tmux-session-name>}"
PANE="${SESSION}:0.0"

echo "Starting auto-approval for session: $SESSION (pane: $PANE)"
echo "Press Ctrl+C to stop"

# Wait for the tmux session to appear (up to 30s)
for i in $(seq 1 30); do
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "Session $SESSION found after ${i}s"
        break
    fi
    if [[ $i -eq 30 ]]; then
        echo "Session $SESSION never appeared, exiting..."
        exit 1
    fi
    sleep 1
done

while true; do
    if ! tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "Session $SESSION ended, exiting..."
        exit 0
    fi

    content=$(tmux capture-pane -t "$PANE" -p 2>/dev/null)

    # Check for permission prompt - must have numbered options to avoid matching conversational text
    if echo "$content" | grep -q "Do you want to" && echo "$content" | grep -qE "^\s*[12][.)]\s"; then
        # First check for Tool/Action-based permissions
        tool=$(echo "$content" | grep "Tool:" | tail -1 | sed 's/.*Tool:[[:space:]]*//')
        action=$(echo "$content" | grep "Action:" | tail -1 | sed 's/.*Action:[[:space:]]*//')

        # Auto-approve safe tool/action combinations
        if [[ -n "$tool" && -n "$action" ]]; then
            if [[ "$tool" == "Bash" && "$action" =~ ^Run\ (full\ )?test\ suite ]]; then
                tmux send-keys -t "$PANE" "1"
                sleep 0.2
                tmux send-keys -t "$PANE" "Enter"
                echo "[$SESSION] $(date +%H:%M:%S) APPROVED TOOL: $tool - $action"
            else
                # Deny other tool/action combinations by default
                tmux send-keys -t "$PANE" "2"
                sleep 0.2
                tmux send-keys -t "$PANE" "Enter"
                echo "[$SESSION] $(date +%H:%M:%S) DENIED TOOL: $tool - $action"
            fi
        else
            # Fallback to bash command parsing for non-tool permissions
            cmd=$(echo "$content" | grep -E "^\s+(poetry|git|curl|npm|bash)" | head -1 | sed 's/^[[:space:]]*//')
            [ -z "$cmd" ] && cmd="tool"

            if echo "$cmd" | grep -Eq "^git branch --show(-current)?$"; then
                tmux send-keys -t "$PANE" "1"
                sleep 0.2
                tmux send-keys -t "$PANE" "Enter"
                echo "[$SESSION] $(date +%H:%M:%S) APPROVED: $cmd"
            elif echo "$cmd" | grep -Eq "^git (merge|rebase|reset|branch|push|pull|fetch|checkout|switch|restore|clean)"; then
                tmux send-keys -t "$PANE" "2"
                sleep 0.2
                tmux send-keys -t "$PANE" "Enter"
                echo "[$SESSION] $(date +%H:%M:%S) DENIED: $(echo "$cmd" | head -c 100)"
            else
                tmux send-keys -t "$PANE" "1"
                sleep 0.2
                tmux send-keys -t "$PANE" "Enter"
                echo "[$SESSION] $(date +%H:%M:%S) APPROVED: $cmd"
            fi
        fi
    fi

    # Check for "Do you want to make this edit" prompts (text may wrap across lines)
    if echo "$content" | grep -q "Do you want to make"; then
        file=$(echo "$content" | grep "Do you want to make this edit" | grep -o '[^ ]*\.[a-zA-Z0-9]*' | tail -1)
        [ -z "$file" ] && file="file"
        tmux send-keys -t "$PANE" "1"
        sleep 0.2
        tmux send-keys -t "$PANE" "Enter"
        echo "[$SESSION] $(date +%H:%M:%S) EDIT: $file"
    fi

    # Check for "Do you want to create" file prompts
    if echo "$content" | grep -q "Do you want to create"; then
        file=$(echo "$content" | grep "Do you want to create" | grep -o '[^ ]*\.[a-zA-Z0-9]*' | tail -1)
        [ -z "$file" ] && file="file"
        tmux send-keys -t "$PANE" "1"
        sleep 0.2
        tmux send-keys -t "$PANE" "Enter"
        echo "[$SESSION] $(date +%H:%M:%S) CREATE: $file"
    fi

    sleep 3
done
