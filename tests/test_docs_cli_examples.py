"""Tests that the CLI examples and MCP parameters in the docs match the real CLI and MCP tools (b.e77).

PURPOSE:
  Users and LLMs copy examples from the docs. Every `bees <subcommand> ...` command in
  README.md and docs/**/*.md (docs/PYPI_README.md included), in fenced code blocks and
  inline code spans, must run as written against the parser src/cli.py builds, and every
  parameter that PRD Appendix E lists for an MCP tool must be a parameter of that tool.

SCOPE - Tests that belong here:
  - Doc CLI commands: the subcommand exists, each flag exists for it, and the whole
    command parses (required flags present, no stray positionals, no abbreviated flags,
    valid JSON and choice values). `<placeholder>` and METAVAR words stand for any value,
    and `[optional]` synopsis groups count as given (first alternative of `[a | b]`).
    An inline span that only names a command (`bees show-ticket`) need not parse.
  - Doc CLI references, which omit metavars and so are not parsed: the subcommand and
    each flag named exist. These are the rows of a markdown table with a command or CLI
    column (its code span, plus the code spans of any argument/flag/option column),
    `usage: bees ...` lines (wrapped lines joined) and bold `**bees ...**` synopses.
  - The CLI parser rejects the wrong commands and references the docs had (b.e77) and
    accepts their fixes
  - PRD Appendix E: each tool exists, each listed parameter is one of its MCP
    parameters, and each required parameter is listed
  - The undertaker(...) calls in the src/mcp_undertaker.py module docstring pass only
    real undertaker MCP parameters

SCOPE - Tests that DON'T belong here:
  - What the commands do -> test_cli_commands.py and the per-command test files
  - Query examples in CLI help, sting and MCP descriptions -> test_query_help.py
  - MCP tool schemas -> test_mcp_server.py
"""

import argparse
import itertools
import re
import shlex
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import pytest

from src import mcp_undertaker
from src.cli import build_parser
from src.mcp_server import mcp

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_FILES = [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").rglob("*.md"))]
PRD = REPO_ROOT / "docs" / "PRD.md"

FENCE = re.compile(r"\s*(```|~~~)")
INLINE_CODE = re.compile(r"`([^`\n]+)`")
PROMPT = re.compile(r"\s*\$\s+")
PLACEHOLDER = re.compile(r"<[A-Za-z][^<>\n]*>")
METAVAR = re.compile(r"[A-Z][A-Z0-9_]*")
FLAG = re.compile(r"--?[A-Za-z]")
# Besides a real subcommand, a word after `bees` meant as a subcommand or flag, not prose ("bees only")
SUBCOMMAND_LIKE = re.compile(r"-|[a-z]+(-[a-z]+)+$")
# CLI references: `usage: bees` lines, bold synopses, and command tables
USAGE = re.compile(r"(\s*)usage:\s+(bees\b.*)")
BOLD = re.compile(r"\*\*`?(bees\s+[^\s*`][^*\n]*?)`?\*\*")
TABLE_SEPARATOR = re.compile(r"\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
CELL_BORDER = re.compile(r"(?<!\\)\|")
COMMAND_COLUMN = re.compile(r"\bcommand|\bcli\b", re.IGNORECASE)
ARGUMENTS_COLUMN = re.compile(r"\bargument|\bflag|\boption", re.IGNORECASE)
# A word in subcommand position: not a flag, nor a synopsis bracket or choice group
REFERENCE_WORD = re.compile(r"\s+([^\s\[\](){}|-][^\s\[\](){}|]*)")
REFERENCE_FLAG = re.compile(r"(?<![\w-])--?[A-Za-z][\w-]*")
# A `{a,b}` group: a flag's choices if a flag precedes it, else subcommand names (`usage: bees [-h] {...}`)
CHOICE_GROUP = re.compile(r"(--?[A-Za-z][\w-]*\s+)?\{([^{}]*)\}")


@dataclass(frozen=True)
class DocCommand:
    source: str  # file:line
    text: str  # the line or span as written
    argv: tuple  # the words after `bees`
    inline: bool


def _simple_commands(text):
    """Split a shell line into simple commands (word lists), as a shell would.

    Handles quotes, backslash escapes, `#` comments, `|` `&&` `;` `&` separators and
    redirects (dropped with their target). Reads synopsis notation too: `<placeholder>`
    is one word, and `[optional]` groups are kept without brackets, with only the first
    alternative of an `[a | b]` group.
    """
    commands, words, word = [], [], None
    drop_target, depth, i, n = False, 0, 0, len(text)

    def finish_word():
        nonlocal word, drop_target
        if word is not None:
            if drop_target:
                drop_target = False
            else:
                words.append(word)
            word = None

    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n:
            word, i = (word or "") + text[i + 1], i + 2
        elif c == "'":
            end = text.find("'", i + 1)
            end = n if end < 0 else end
            word, i = (word or "") + text[i + 1:end], end + 1
        elif c == '"':
            i, chars = i + 1, []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n and text[i + 1] in '"\\$`':
                    i += 1
                chars.append(text[i])
                i += 1
            word, i = (word or "") + "".join(chars), i + 1
        elif c.isspace():
            finish_word()
            i += 1
        elif c == "#" and word is None:
            break
        elif c == "<" and (placeholder := PLACEHOLDER.match(text, i)):
            word, i = (word or "") + placeholder.group(), placeholder.end()
        elif c == "[" and word is None:
            depth, i = depth + 1, i + 1
        elif c == "]" and depth:
            finish_word()
            depth, i = depth - 1, i + 1
        elif c == "|" and depth:
            finish_word()
            group = depth
            while i < n and depth >= group:
                depth += {"[": 1, "]": -1}.get(text[i], 0)
                i += 1
        elif c in "<>" or text.startswith("&>", i):
            if word is not None and word.isdigit():
                word = None
            finish_word()
            while i < n and text[i] in "<>&":
                i += 1
            drop_target = True
        elif c in "|&;":
            finish_word()
            if words:
                commands.append(words)
            words = []
            while i < n and text[i] in "|&;":
                i += 1
        else:
            word, i = (word or "") + c, i + 1
    finish_word()
    if words:
        commands.append(words)
    return commands


def _bees_argv(words):
    """The words after `bees` if this simple command runs bees (also after a `--` marker), else None."""
    if words[0] == "bees":
        return words[1:]
    if "--" in words and words[words.index("--") + 1:][:1] == ["bees"]:
        return words[words.index("--") + 2:]
    return None


def _names_subcommand(word):
    """Whether `bees <word>` names a subcommand (real or not), not prose ("bees only")."""
    return word in SUBCOMMANDS or bool(SUBCOMMAND_LIKE.match(word))


def _bees_commands(text, source, inline):
    """The bees commands in one line or inline code span."""
    found = []
    for words in _simple_commands(PROMPT.sub("", text, count=1)):
        argv = _bees_argv(words)
        if argv and _names_subcommand(argv[0]):
            found.append(DocCommand(source, text.strip(), tuple(argv), inline))
    return found


def _doc_commands():
    """Every bees command in the docs' fenced code blocks (continued lines joined) and inline code spans."""
    commands = []
    for path in DOC_FILES:
        rel = path.relative_to(REPO_ROOT).as_posix()
        in_fence, held, held_from = False, "", None
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FENCE.match(line):
                in_fence, held, held_from = not in_fence, "", None
            elif in_fence:
                held_from = held_from or lineno
                if line.rstrip().endswith("\\"):
                    held += line.rstrip()[:-1] + " "
                    continue
                # A fenced markdown template can hold its commands in code spans
                commands += _bees_commands(held + line, f"{rel}:{held_from}", inline=False) or [
                    c for span in INLINE_CODE.findall(line)
                    for c in _bees_commands(span, f"{rel}:{lineno}", inline=True)
                ]
                held, held_from = "", None
            else:
                for span in INLINE_CODE.findall(line):
                    commands += _bees_commands(span, f"{rel}:{lineno}", inline=True)
    return commands


@dataclass(frozen=True)
class DocReference:
    source: str  # file:line
    kind: str  # "table", "usage" or "bold"
    text: str  # `bees` and the words the doc gives after it


def _cells(row):
    cells = CELL_BORDER.split(row.strip().removeprefix("|").removesuffix("|"))
    return [cell.strip().replace("\\|", "|") for cell in cells]


def _table_references(rel, lines, separator):
    """The command references in the markdown table whose separator row is lines[separator].

    A column whose header names commands or the CLI holds bees commands if one of its code
    spans names a real subcommand. Each row's first span there is a reference, followed by
    the spans of the row's argument/flag/option columns.
    """
    header = _cells(lines[separator - 1])
    rows = [_cells(row) for row in itertools.takewhile(lambda line: "|" in line, lines[separator + 1:])]
    argument_columns = [i for i, name in enumerate(header) if ARGUMENTS_COLUMN.search(name)]
    references = []
    for column in (i for i, name in enumerate(header) if COMMAND_COLUMN.search(name)):
        found = []
        for offset, cells in enumerate(rows):
            spans = INLINE_CODE.findall(cells[column]) if column < len(cells) else []
            if spans and spans[0].strip():
                arguments = [span for i in argument_columns if i < len(cells) for span in INLINE_CODE.findall(cells[i])]
                text = " ".join(["bees", spans[0].removeprefix("bees "), *arguments])
                found.append(DocReference(f"{rel}:{separator + 2 + offset}", "table", text))
        if any(ref.text.split()[1] in SUBCOMMANDS for ref in found):
            references += found
    return references


def _doc_references():
    """Every reference to a bees command in the docs' command tables, `usage: bees` lines and bold synopses."""
    references = []
    for path in DOC_FILES:
        rel = path.relative_to(REPO_ROOT).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        in_fence = False
        for i, line in enumerate(lines):
            if FENCE.match(line):
                in_fence = not in_fence
            elif usage := USAGE.match(line):
                text, indent = usage.group(2), len(usage.group(1)) + len("usage: ")
                for wrapped in lines[i + 1:]:  # argparse indents wrapped usage lines past "usage: "
                    if not (wrapped.strip() and wrapped[:indent].isspace()):
                        break
                    text += " " + wrapped.strip()
                references.append(DocReference(f"{rel}:{i + 1}", "usage", text))
            elif not in_fence:
                references += [
                    DocReference(f"{rel}:{i + 1}", "bold", bold.group(1).replace("`", ""))
                    for bold in BOLD.finditer(line) if _names_subcommand(bold.group(1).split()[1])
                ]
                if i and "|" in line and "|" in lines[i - 1] and TABLE_SEPARATOR.match(line):
                    references += _table_references(rel, lines, i)
    return references


class _UsageError(Exception):
    """The CLI parser rejected the command."""


class _HelpShown(Exception):
    """The command asked for help."""


def _raise_usage_error(message):
    raise _UsageError(message)


def _raise_help_shown(status=0, message=None):
    raise _HelpShown()


def _is_placeholder(value):
    return isinstance(value, str) and bool(PLACEHOLDER.fullmatch(value) or METAVAR.fullmatch(value))


def _convert_unless_placeholder(convert, value):
    return value if _is_placeholder(value) else convert(value)


def _check_unless_placeholder(check, action, value):
    if not _is_placeholder(value):
        check(action, value)


def _subparsers(parser):
    return next((a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None)


def _all_parsers(parser):
    yield parser
    if subparsers := _subparsers(parser):
        for sub in subparsers.choices.values():
            yield from _all_parsers(sub)


SUBCOMMANDS = frozenset(_subparsers(build_parser()).choices)


@pytest.fixture(scope="module")
def cli_parser():
    """The real CLI parser, raising instead of exiting, with no flag abbreviations, taking placeholders as any value."""
    parser = build_parser()
    for p in _all_parsers(parser):
        p.allow_abbrev = False
        p.error = _raise_usage_error
        p.exit = _raise_help_shown
        p.print_help = lambda file=None: None
        p._check_value = partial(_check_unless_placeholder, p._check_value)
        for action in p._actions:
            if callable(action.type):
                action.type = partial(_convert_unless_placeholder, action.type)
                action.type.__name__ = getattr(action.type.args[0], "__name__", "value")
    return parser


def _problems(parser, argv, inline=False):
    """What is wrong with `bees <argv>`, as messages; empty if it runs as written."""
    leaf, depth = parser, 0
    while (subparsers := _subparsers(leaf)) and depth < len(argv) and not argv[depth].startswith("-"):
        if argv[depth] not in subparsers.choices:
            return [f"no subcommand 'bees {' '.join(argv[:depth + 1])}'"]
        leaf, depth = subparsers.choices[argv[depth]], depth + 1
    if inline and depth == len(argv):
        return []  # an inline span that only names a command
    command = " ".join(["bees", *argv[:depth]])
    problems = [
        f"'{command}' has no flag {flag}"
        for flag in (word.split("=", 1)[0] for word in argv[depth:] if FLAG.match(word))
        if flag not in leaf._option_string_actions
    ]
    try:
        args = parser.parse_args(list(argv))
    except _HelpShown:
        return problems
    except _UsageError as exc:
        return problems + [f"CLI parser: {exc}"]
    if not hasattr(args, "func"):
        problems.append(f"'{command}' is not a complete command")
    return problems


def _reference_problems(parser, text):
    """What subcommand or flag that `text` (`bees ...`) names does not exist; not a full parse."""
    rest, leaf, path = text.removeprefix("bees"), parser, ["bees"]
    while (subparsers := _subparsers(leaf)) and (word := REFERENCE_WORD.match(rest)):
        path.append(word.group(1))
        if word.group(1) not in subparsers.choices:
            return [f"no subcommand '{' '.join(path)}'"]
        leaf, rest = subparsers.choices[word.group(1)], rest[word.end():]
    command = " ".join(path)
    problems = [
        f"'{command}' has no flag {flag}"
        for flag in REFERENCE_FLAG.findall(rest)
        if flag not in leaf._option_string_actions
    ]
    if subparsers := _subparsers(leaf):
        problems += [
            f"no subcommand '{command} {name}'"
            for group in CHOICE_GROUP.finditer(rest) if not group.group(1)
            for name in map(str.strip, group.group(2).split(","))
            if name not in subparsers.choices
        ]
    return problems


def test_doc_cli_commands_run_as_written(cli_parser):
    """Every bees command in the docs names a real subcommand and flags, and parses as written."""
    commands = _doc_commands()
    assert {"README.md", "docs/advanced-usage.md"} <= {c.source.split(":")[0] for c in commands}
    assert any(not c.inline and c.source.startswith("docs/advanced-usage.md:") for c in commands)

    failures = []
    for command in commands:
        problems = _problems(cli_parser, command.argv, command.inline)
        if problems:
            failures.append(f"{command.source}: {command.text}\n" + "".join(f"    - {p}\n" for p in problems))
    assert not failures, f"{len(failures)} doc CLI example(s) do not run as written:\n" + "".join(failures)


@pytest.mark.parametrize(
    "wrong, fixed",
    [
        pytest.param("show-ticket b.amx t1.amx.12", "show-ticket --ids b.amx t1.amx.12", id="show_ticket_needs_ids"),
        pytest.param("delete-ticket b.amx", "delete-ticket --ids b.amx", id="delete_ticket_needs_ids"),
        pytest.param("abandon-hive backend", "abandon-hive --hive backend", id="abandon_hive_needs_hive"),
        pytest.param("sanitize-hive backend", "sanitize-hive --hive backend", id="sanitize_hive_needs_hive"),
        pytest.param("rename-hive old new", "rename-hive --old-name old --new-name new", id="rename_hive_needs_names"),
        pytest.param("clone b.amx --hive other", "clone --bee-id b.amx --hive other", id="clone_needs_bee_id"),
        pytest.param("move-bee b.amx b.x4f --destination backlog", "move-bee --ids b.amx b.x4f --hive backlog", id="move_bee_has_no_destination"),  # noqa: E501
        pytest.param("generate-index --status open --type bee", "generate-index --hive backend", id="generate_index_hive_only"),  # noqa: E501
    ],
)
def test_cli_rejects_wrong_doc_forms_and_accepts_fixes(cli_parser, wrong, fixed):
    """The wrong forms the docs showed (b.e77) are rejected; the corrected forms run as written."""
    assert _problems(cli_parser, shlex.split(wrong))
    assert _problems(cli_parser, shlex.split(fixed)) == []


def test_doc_cli_references_name_real_subcommands_and_flags(cli_parser):
    """Each command table row, `usage: bees` line and bold `**bees ...**` synopsis names a real subcommand and flags."""
    references = _doc_references()
    assert {"table", "usage", "bold"} <= {r.kind for r in references}
    assert any(r.kind == "table" and REFERENCE_FLAG.search(r.text) for r in references)

    failures = []
    for reference in references:
        problems = _reference_problems(cli_parser, reference.text)
        if problems:
            failures.append(f"{reference.source}: {reference.text}\n" + "".join(f"    - {p}\n" for p in problems))
    assert not failures, f"{len(failures)} doc CLI reference(s) name no real command or flag:\n" + "".join(failures)


@pytest.mark.parametrize(
    "wrong, fixed",
    [
        pytest.param("bees clone-bee ID [--hive DEST]", "bees clone --bee-id ID [--hive DEST]", id="clone_bee_is_clone"),  # noqa: E501
        pytest.param("bees set-status-values --scope [--values JSON]", "bees set-status-values --scope [--status-values JSON]", id="status_values_flag"),  # noqa: E501
        pytest.param("bees serve [--stdio | --http] [--watch]", "bees serve [--stdio | --http]", id="serve_has_no_watch"),  # noqa: E501
        pytest.param("bees generate-index [--status STATUS]", "bees generate-index [--hive HIVE]", id="generate_index_hive_only"),  # noqa: E501
        pytest.param("bees [-h] {create-ticket,clone-bee} ...", "bees [-h] {create-ticket,clone} ...", id="usage_subcommand_list"),  # noqa: E501
    ],
)
def test_cli_reference_check_rejects_wrong_doc_references_and_accepts_fixes(cli_parser, wrong, fixed):
    """References to a missing subcommand or flag, as the PRD had (b.e77), are rejected; their fixes are accepted."""
    assert _reference_problems(cli_parser, wrong)
    assert _reference_problems(cli_parser, fixed) == []


def _appendix_e_tools():
    """{tool: (heading line, {param: line})} for each `### `tool`` and its `- `param`:` bullets in PRD Appendix E."""
    tools, tool, in_appendix = {}, None, False
    for lineno, line in enumerate(PRD.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("## "):
            in_appendix = line.startswith("## Appendix E")
        elif in_appendix and (heading := re.match(r"### `(\w+)`", line)):
            tool = heading.group(1)
            tools[tool] = (lineno, {})
        elif in_appendix and tool and (bullet := re.match(r"- `(\w+)`:", line)):
            tools[tool][1][bullet.group(1)] = lineno
    return tools


async def test_prd_appendix_e_lists_real_mcp_parameters():
    """Each PRD Appendix E tool exists, lists only its real MCP parameters, and lists every required one."""
    tools = _appendix_e_tools()
    assert tools

    failures = []
    for name, (heading_line, params) in tools.items():
        tool = await mcp.get_tool(name)
        if tool is None:
            failures.append(f"docs/PRD.md:{heading_line}: no MCP tool {name!r}")
            continue
        real = tool.parameters.get("properties", {})
        failures += [
            f"docs/PRD.md:{line}: {name} has no parameter {param!r} (its parameters: {', '.join(real)})"
            for param, line in params.items()
            if param not in real
        ]
        failures += [
            f"docs/PRD.md:{heading_line}: {name} required parameter {param!r} is not listed"
            for param in tool.parameters.get("required", [])
            if param not in params
        ]
    assert not failures, f"{len(failures)} PRD Appendix E MCP parameter problem(s):\n" + "\n".join(failures)


async def test_undertaker_docstring_calls_use_real_parameters():
    """The undertaker(...) calls in the src/mcp_undertaker.py module docstring pass only real MCP parameters."""
    real = (await mcp.get_tool("undertaker")).parameters["properties"]
    calls = re.findall(r"\bundertaker\(([^)]*)\)", mcp_undertaker.__doc__)
    assert calls

    for call in calls:
        keywords = re.findall(r"(\w+)\s*=", re.sub(r"\"[^\"]*\"|'[^']*'", "''", call))
        assert keywords and set(keywords) <= set(real), f"undertaker({call}): parameters are {', '.join(real)}"
