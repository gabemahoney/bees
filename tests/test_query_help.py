"""Tests that the query help on every surface is enough to write a working query (b.37f, GH#28).

PURPOSE:
  A caller learns the query language from `bees execute-freeform-query -h`,
  `bees add-named-query -h`, `bees sting` or the MCP execute_freeform_query and
  add_named_query tool descriptions. Each must document the "report" key and its
  fields, and its examples must work as written, typed into a shell.

SCOPE - Tests that belong here:
  - Each surface documents "report", lists exactly VALID_REPORT_FIELDS as
    reportable and NON_REPORTABLE_FIELDS as not reportable (read with show-ticket),
    shows both example queries from query_parser, and has no literal backslash-n
  - Each surface contains the PRIORITY_TERMS_HELP reference and lists priority as reportable
  - Every query example in the rendered CLI help and sting output, tokenized as a
    shell would, is one --query-yaml argument and runs against a test hive
  - The double-quoted regex term with doubled backslashes in the CLI and MCP
    execute_freeform_query help matches literal brackets when used as written
  - The undertaker query examples (MCP tool description, module docstring) parse

SCOPE - Tests that DON'T belong here:
  - Query parsing and report validation -> test_query_parser.py
  - Query execution and report projection -> test_query_tools.py
  - Sting scope and MCP detection -> test_cli_sting.py
"""

import asyncio
import json
import re
import shlex

import pytest
import yaml

from src import mcp_undertaker
from src.mcp_server import mcp
from src.query_parser import (
    NON_REPORTABLE_FIELDS,
    PRIORITY_TERMS_HELP,
    QUERY_YAML_EXAMPLE,
    REPORT_QUERY_YAML_EXAMPLE,
    VALID_REPORT_FIELDS,
    QueryParser,
)

CLI_SURFACES = ["execute-freeform-query", "add-named-query", "sting"]
MCP_SURFACES = ["mcp:execute_freeform_query", "mcp:add_named_query"]


@pytest.fixture
def query_env(isolated_bees_env, tmp_path, monkeypatch):
    """Scoped test hive with t1 children and an empty home, so `bees sting` prints its reference."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    isolated_bees_env.create_hive("test")
    isolated_bees_env.write_config(child_tiers={"t1": ["Task", "Tasks"]})


@pytest.fixture
def pupa_tickets(cli_runner, query_env):
    """Pupa bee with one child, plus an open bee the help examples filter out; returns (bee_id, child_id)."""
    create = ["create-ticket", "--hive", "test", "--ticket-type"]
    bee_id = _run(cli_runner, create + ["bee", "--title", "Pupa Bee", "--status", "pupa"])["ticket_id"]
    child_id = _run(cli_runner, create + ["t1", "--title", "Child Task", "--parent", bee_id])["ticket_id"]
    _run(cli_runner, create + ["bee", "--title", "Open Bee"])
    return bee_id, child_id


def _run(cli_runner, argv):
    """Run a bees command; assert it succeeded and return its JSON result."""
    stdout, exit_code = cli_runner(argv)
    assert exit_code == 0, f"{argv} failed: {stdout}"
    return json.loads(stdout)


def _surface_text(cli_runner, surface):
    """Return the help text a caller sees on one surface."""
    if surface.startswith("mcp:"):
        return asyncio.run(mcp.get_tool(surface.removeprefix("mcp:"))).description
    stdout, exit_code = cli_runner(["sting"] if surface == "sting" else [surface, "--help"])
    assert exit_code == 0
    return stdout


def _listed_fields(text, label):
    """Return the set of comma-separated field names that follow `label` in text."""
    match = re.search(re.escape(label) + r"\s*([a-z_]+(?:,\s*[a-z_]+)*)", text)
    assert match, f"{label!r} not found in:\n{text}"
    return set(re.split(r",\s*", match.group(1)))


def _example_commands(text, surface):
    """Argv lists (without "bees") for every query example in the help, tokenized as a shell would."""
    lines = text.splitlines()
    commands = [shlex.split(line)[1:] for line in lines if line.strip().startswith("bees ") and "--query-yaml" in line]
    # Examples in the --query-yaml option help: from that option's line to the next option's line
    start = next((i for i, line in enumerate(lines) if line.startswith("  --query-yaml")), len(lines))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("  -")), len(lines))
    option_help = " ".join(" ".join(lines[start:end]).split())
    quoted_queries = [q for q in re.findall(r"'[^']*'|\"[^\"]*\"", option_help) if "stages:" in q]
    for n, quoted in enumerate(quoted_queries):
        (query_yaml,) = shlex.split(quoted)
        name_args = ["--query-name", f"option-example-{n}"] if surface == "add-named-query" else []
        commands.append([surface, "--query-yaml", query_yaml] + name_args)
    return commands


@pytest.mark.parametrize("surface", CLI_SURFACES + MCP_SURFACES)
def test_help_documents_report_fields_and_examples(cli_runner, query_env, surface):
    """Each surface documents report, its accepted and rejected fields, and both one-line examples."""
    raw = _surface_text(cli_runner, surface)
    text = " ".join(raw.split())

    assert re.search(r"\breport\b", text)
    assert _listed_fields(text, "Reportable fields:") == VALID_REPORT_FIELDS
    assert _listed_fields(text, "Not reportable:") == NON_REPORTABLE_FIELDS
    assert re.search(r"Not reportable:.{0,100}?show[-_]ticket", text), "not-reportable fields must point to show-ticket"
    assert QUERY_YAML_EXAMPLE in text
    assert REPORT_QUERY_YAML_EXAMPLE in text
    assert "\\n" not in raw, "a literal backslash-n is not a newline when typed into a shell"


@pytest.mark.parametrize("surface", CLI_SURFACES + MCP_SURFACES)
def test_help_documents_priority_terms_and_reportable_priority(cli_runner, query_env, surface):
    """Each surface carries the single-source priority term reference and lists priority as reportable."""
    text = " ".join(_surface_text(cli_runner, surface).split())

    assert " ".join(PRIORITY_TERMS_HELP.split()) in text
    assert "priority" in _listed_fields(text, "Reportable fields:")


@pytest.mark.parametrize("surface", CLI_SURFACES)
def test_help_examples_run_as_written(cli_runner, pupa_tickets, surface):
    """Every query example in the rendered help is one shell argument and runs as written."""
    bee_id, child_id = pupa_tickets
    commands = _example_commands(_surface_text(cli_runner, surface), surface)
    assert commands, f"no query example found in the {surface} help"

    queries = []
    for argv in commands:
        query = yaml.safe_load(argv[argv.index("--query-yaml") + 1])
        assert isinstance(query, dict) and "stages" in query, f"{argv} passes no query dict: {query!r}"
        queries.append(query)

        result = _run(cli_runner, argv)
        if argv[0] == "add-named-query":
            result = _run(cli_runner, ["execute-named-query", "--query-name", argv[argv.index("--query-name") + 1]])

        if "report" in query:
            assert [(t["ticket_id"], t["title"], t["ticket_status"]) for t in result["tickets"]] == [
                (bee_id, "Pupa Bee", "pupa")
            ]
        else:
            assert result["ticket_ids"] == [child_id]

    assert any("report" in query for query in queries), f"no report example in the {surface} help"


@pytest.mark.parametrize("surface", ["execute-freeform-query", "mcp:execute_freeform_query"])
def test_escaped_regex_example_matches_literal_brackets(cli_runner, query_env, surface):
    """The help's double-quoted term with doubled regex backslashes, used as written, matches literal brackets."""
    (stage,) = [s for s in re.findall(r'\["[^"]*"\]', _surface_text(cli_runner, surface)) if "\\" in s]
    create = ["create-ticket", "--hive", "test", "--ticket-type", "bee", "--title"]
    bug_id = _run(cli_runner, create + ["[bug] Crash on start"])["ticket_id"]
    _run(cli_runner, create + ["Plain bug"])  # matches too if the escapes are lost and [bug] is a character class

    result = _run(cli_runner, ["execute-freeform-query", "--query-yaml", f"{{stages: [{stage}]}}"])
    assert result["ticket_ids"] == [bug_id]


@pytest.mark.parametrize(
    "doc",
    [
        pytest.param(lambda: asyncio.run(mcp.get_tool("undertaker")).description, id="mcp_tool_description"),
        pytest.param(lambda: mcp_undertaker.__doc__, id="module_docstring"),
    ],
)
def test_undertaker_query_examples_parse(doc):
    """Every query_yaml example in the undertaker docs is a valid query."""
    examples = re.findall(r'query_yaml"?\s*[:=]\s*"([^"]*)"', doc())
    assert examples
    for example in examples:
        assert QueryParser().parse_and_validate(yaml.safe_load(example)).stages
