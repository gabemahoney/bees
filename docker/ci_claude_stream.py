#!/usr/bin/env python3
"""Show a headless Claude run in the CI pane, and tell whether it printed a result line.

docker/test_runner.sh runs the Claude phases headless, with
``claude -p "/release-test" --output-format stream-json --verbose``, so Claude exits once its run is over
(an interactive session would sit at its prompt until /ci's phase deadline). It pipes that stream through
this script, which prints the run as it happens to the tmux pane /ci reads: Claude's text, each tool call,
and the first lines of each tool result. Prompts, such as the skill text, are never printed.

A result line is one /ci acts on: ``RELEASE TEST PHASE <phase> PASSED``, ``BUG FILED:`` or
``BUG FILING FAILED:``. It counts in Claude's text anywhere in a line, as /ci reads the pane, and in a
tool result only at the start of a line, where file_bug.py prints it: a tool result that merely quotes
one (a file Claude read, say) does not count.

When the stream ends, the script prints the result lines it saw once more, as the last lines of the pane
/ci captures, and exits 0. With none, it exits 1, and test_runner.sh prints the crash line. Either way it
writes how the run ended, one line, to --outcome-file if given. If the pane goes away, it reads on to the
end of the stream, so Claude keeps its output pipe, and exits the same way. test_runner.sh takes any other
exit status for a crash of this script.

Stdlib only.

Usage:
    claude -p "/release-test" --output-format stream-json --verbose \\
        | python3 ci_claude_stream.py --phase 4 [--outcome-file /tmp/outcome.txt]

Exit codes:
    0  a result line was seen
    1  no result line was seen
    2  usage error
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from typing import TextIO

# Lines shown of each tool result, and characters of each shown line (a result line is shown in full)
TOOL_RESULT_LINES = 8
MAX_LINE_CHARS = 300
# Characters shown of each tool call's input, and of Claude's last message in the outcome
TOOL_INPUT_CHARS = 200
LAST_MESSAGE_CHARS = 200

TOOL_CALL_PREFIX = "> "
TOOL_RESULT_PREFIX = "  | "
TOOL_ERROR_PREFIX = "  ! "
RESULT_HEADER = "=== Result lines of this run ==="


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _blocks(message: object) -> list:
    """The content blocks of a stream-json message (a plain string content is one text block)."""
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [block for block in content if isinstance(block, dict)] if isinstance(content, list) else []


def _tool_result_text(content: object) -> str:
    """The text of a tool_result block's content: a string, or a list of text (and other) blocks."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
        elif isinstance(block, dict):
            parts.append(f"[{block.get('type', 'content')}]")
    return "\n".join(parts)


def _tool_input_summary(name: object, tool_input: object) -> str:
    """One line describing a tool call: a Bash call's command, otherwise its input as JSON."""
    if name == "Bash" and isinstance(tool_input, dict) and isinstance(tool_input.get("command"), str):
        summary = tool_input["command"]
    else:
        summary = json.dumps(tool_input, ensure_ascii=False)
    return _clip(_one_line(summary), TOOL_INPUT_CHARS)


class StreamView:
    """Prints stream-json events as readable lines and collects the result lines among them."""

    def __init__(self, phase: str, out: TextIO):
        self.out = out
        passed = re.escape(f"RELEASE TEST PHASE {phase} PASSED")
        # In Claude's text: anywhere in a line. In a tool result: at the start of a line.
        self._in_text = re.compile(rf"\b{passed}\b|BUG FILED:|BUG FILING FAILED:")
        self._at_start = re.compile(rf"\s*(?:{passed}\b|BUG FILED:|BUG FILING FAILED:)")
        self.results: list[str] = []
        self.final: dict | None = None
        self.last_text = ""
        self._out_closed = False

    def emit(self, text: str) -> None:
        if self._out_closed:
            return
        try:
            print(text, file=self.out, flush=True)
        except OSError:
            # The pane is gone: keep reading, so the end of Claude's output pipe does not end its run
            self._out_closed = True
            self._discard_output()

    def _discard_output(self) -> None:
        """Point the output's file descriptor at the null device.

        The text that failed to print stays in the output's buffer, and Python flushes stdout at exit:
        on the gone pane that flush fails, and the script exits 120 whatever result lines it saw.
        """
        try:
            null = os.open(os.devnull, os.O_WRONLY)
        except OSError:
            return
        try:
            os.dup2(null, self.out.fileno())
        except (OSError, ValueError):
            # No file descriptor (e.g. an in-memory stream), or a closed one: nothing flushes to a pane
            pass
        finally:
            os.close(null)

    def _record(self, line: str) -> None:
        line = line.strip()
        if line not in self.results:
            self.results.append(line)

    def _scan_text(self, text: str) -> None:
        for line in text.splitlines():
            if self._in_text.search(line):
                self._record(line)

    def handle_line(self, raw: str) -> None:
        raw = raw.rstrip("\r\n")
        if not raw.strip():
            return
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            event = None
        if not isinstance(event, dict):
            # Not a stream-json event: e.g. an error Claude printed as plain text. Show it as it is.
            self.emit(raw)
            self._scan_text(raw)
            return
        handler = {
            "assistant": self._assistant,
            "user": self._user,
            "system": self._system,
            "result": self._result,
        }.get(event.get("type"))
        if handler:
            handler(event)

    def _assistant(self, event: dict) -> None:
        for block in _blocks(event.get("message")):
            if block.get("type") == "text":
                text = str(block.get("text") or "")
                if text.strip():
                    self.emit(text)
                    self._scan_text(text)
                    self.last_text = text
            elif block.get("type") == "tool_use":
                name = block.get("name")
                self.emit(f"{TOOL_CALL_PREFIX}{name}: {_tool_input_summary(name, block.get('input'))}")
        if event.get("error"):
            self.emit(f"[Claude error: {event['error']}]")

    def _user(self, event: dict) -> None:
        # Only tool results: a user message's text is a prompt (e.g. the skill), which quotes the result lines
        for block in _blocks(event.get("message")):
            if block.get("type") == "tool_result":
                self._tool_result(block)

    def _tool_result(self, block: dict) -> None:
        prefix = TOOL_ERROR_PREFIX if block.get("is_error") else TOOL_RESULT_PREFIX
        lines = _tool_result_text(block.get("content")).splitlines()
        for number, line in enumerate(lines):
            is_result = bool(self._at_start.match(line))
            if is_result:
                self._record(line)
            if number < TOOL_RESULT_LINES:
                self.emit(prefix + (line if is_result else _clip(line, MAX_LINE_CHARS)))
            elif is_result:
                self.emit(prefix + line)
        if len(lines) > TOOL_RESULT_LINES:
            self.emit(f"{prefix}... ({len(lines) - TOOL_RESULT_LINES} more lines)")

    def _system(self, event: dict) -> None:
        subtype = event.get("subtype")
        if subtype == "init":
            servers = [
                f"{server.get('name')} ({server.get('status')})"
                for server in event.get("mcp_servers") or []
                if isinstance(server, dict)
            ]
            listed = ", ".join(servers) or "none"
            self.emit(f"--- Claude started: model {event.get('model')}, MCP servers: {listed} ---")
        elif subtype == "api_retry":
            self.emit(
                f"[API retry {event.get('attempt')}/{event.get('max_retries')}: {event.get('error')}, "
                f"HTTP status {event.get('error_status')}]"
            )
        elif subtype == "permission_denied":
            self.emit(f"[permission denied: {event.get('tool_name') or 'a tool call'}]")

    def _result(self, event: dict) -> None:
        self.final = event
        text = event.get("result")
        if isinstance(text, str) and text.strip():
            self._scan_text(text)
            # The text of a run that finished is Claude's last message, printed already; an error's is not
            if event.get("is_error"):
                self.emit(text)
            self.last_text = text
        self.emit(f"--- Claude run ended: {self.outcome()} ---")

    def outcome(self) -> str:
        """One line on how the run ended."""
        if self.final is None:
            return "Claude's output ended with no final result: the run stopped early (its last output is above)"
        final = self.final
        state = "failed" if final.get("is_error") else "finished"
        parts = [f"the run {state} ({final.get('subtype') or 'no subtype'})"]
        if isinstance(final.get("num_turns"), int):
            parts.append(f"after {final['num_turns']} turns")
        if isinstance(final.get("duration_ms"), (int, float)):
            parts.append(f"in {final['duration_ms'] / 1000:.0f} s")
        denials = final.get("permission_denials")
        if isinstance(denials, list) and denials:
            parts.append(f"{len(denials)} tool calls denied")
        if self.last_text.strip():
            parts.append(f'last message: "{_clip(_one_line(self.last_text), LAST_MESSAGE_CHARS)}"')
        return ", ".join(parts)

    def finish(self, outcome_file: str | None) -> int:
        """Print the result lines again as the last lines, write the outcome, and return the exit code."""
        if self.results:
            self.emit("")
            self.emit(RESULT_HEADER)
            for line in self.results:
                self.emit(line)
        if outcome_file:
            try:
                with open(outcome_file, "w", encoding="utf-8") as handle:
                    handle.write(self.outcome() + "\n")
            except OSError as exc:
                self.emit(f"[ci_claude_stream: cannot write {outcome_file}: {exc}]")
        return 0 if self.results else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show a headless Claude run (stream-json on stdin) in the CI pane.")
    parser.add_argument("--phase", required=True, help="the phase number, as in RELEASE TEST PHASE <phase> PASSED")
    parser.add_argument("--outcome-file", help="file to write one line on how the run ended")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[1-9][0-9]*", args.phase):
        parser.error(f"--phase must be a phase number, got {args.phase!r}")

    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="replace")
    view = StreamView(args.phase, sys.stdout)
    stream = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    for raw in stream:
        try:
            view.handle_line(raw)
        except Exception as exc:  # an event it cannot show must not end it: Claude would lose its output pipe
            view.emit(f"[ci_claude_stream: cannot show an event: {exc!r}]")
    return view.finish(args.outcome_file)


if __name__ == "__main__":
    sys.exit(main())
