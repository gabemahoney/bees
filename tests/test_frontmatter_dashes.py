"""Regression tests for b.5yy: three dashes inside a frontmatter value never close the frontmatter.

parse_frontmatter takes the first line after the opening one that starts with ``---`` as the
closing delimiter, and the writer never starts a frontmatter line with ``---``. So a title,
status, tag or reference material value holding ``---`` (inside a line, as the whole value, as a
line of a multi-line value, inside a single-quoted YAML scalar, after a CR) works end to end,
over the CLI and the MCP tool functions (``src/mcp_server.py``): create and update store it, show
returns it with the ticket's real guid and its body unchanged, a later update of another field
keeps it, and a freeform query still returns the ticket.

The same end-to-end check covers b.gg4's cases: title, status and tag values the writer once wrote
plain or as a bad block scalar (a lone dash, dash and space, a first line starting with a space,
trailing newlines, a control character, a tab before ``#`` or after ``:``, ``<<``, ``1:20``),
which were unreadable or read back changed.

Covered elsewhere: the writer-and-parser round trip of every ``DASH_VALUES`` value in title, tags
and reference materials (``test_value_with_dashes_round_trips_through_writer``; status takes
title's path) and the ParseError for a file whose only later ``---`` is inside a value
(``test_parse_errors``) in test_reader.py; in test_writer.py, that the writer's yaml.dump fallback
never starts a frontmatter line with ``---`` (``test_no_frontmatter_line_starts_with_dashes``) and,
for both writer paths, that every ``QUOTING_VALUES`` and ``DASH_VALUES`` value and seeded random
strings read back exactly as a middle key, the last key, a list item and the last item of the last
key's list, with no line starting with ``---`` (``test_generated_strings_round_trip_through_parser``);
ci_plan.py's frontmatter reader in test_ci_skill.py; show-ticket on a malformed file in
test_corruption_handling.py.
"""

import json
import re

import pytest

from src.mcp_server import create_ticket, execute_freeform_query, show_ticket, update_ticket
from src.paths import compute_ticket_path
from tests.helpers import cli_success, mcp_success
from tests.test_constants import DASH_VALUES, HIVE_BACKEND, QUOTING_VALUES

_HIVE = HIVE_BACKEND  # the hive conftest's hive_env registers
_BODY = "Body\n---\nend"
_FIELDS = ["title", "status", "tags", "reference_materials"]
# show_ticket's key for a field, where it differs from the field name
_SHOWN_AS = {"status": "ticket_status"}
# One value of each kind; test_reader.py round-trips all of DASH_VALUES through writer and parser
_E2E_VALUES = ["dashes_inside", "only_dashes", "line_of_dashes", "single_quoted", "cr_then_dashes"]
# (field, QUOTING_VALUES key) pairs; test_writer.py round-trips all of QUOTING_VALUES through writer and parser
_QUOTING_E2E = [
    ("title", "lone_dash"), ("title", "dash_space"), ("status", "dash_space"), ("tags", "dash_space"),
    ("title", "space_first_line"), ("title", "trailing_newlines"), ("title", "bell"), ("title", "colon_tab"),
    ("title", "tab_hash"), ("tags", "tab_hash"), ("status", "merge_key"), ("tags", "sexagesimal"),
]


def _flags(fields):
    """CLI flags in --flag=value form, so a value starting with "-" is not taken for a flag."""
    return [
        f"--{name.replace('_', '-')}={value if isinstance(value, str) else json.dumps(value)}"
        for name, value in fields.items()
    ]


def _create(via, cli_runner, **fields):
    fields = {"title": "Dashes", **fields}
    if via == "mcp":
        return mcp_success(create_ticket(ticket_type="bee", hive=_HIVE, body=_BODY, **fields))["ticket_id"]
    argv = ["create-ticket", "--ticket-type=bee", f"--hive={_HIVE}", f"--body={_BODY}", *_flags(fields)]
    return cli_success(cli_runner, *argv)["ticket_id"]


def _update(via, cli_runner, ticket_id, **fields):
    if via == "mcp":
        mcp_success(update_ticket(ticket_ids=ticket_id, **fields))
    else:
        cli_success(cli_runner, "update-ticket", f"--ids={ticket_id}", *_flags(fields))


def _shown(via, cli_runner, ticket_id, *fields):
    """The values of ``fields`` that show-ticket / show_ticket returns for the ticket."""
    if via == "mcp":
        result = mcp_success(show_ticket(ticket_ids=[ticket_id]))
    else:
        result = cli_success(cli_runner, "show-ticket", f"--ids={ticket_id}")
    (ticket,) = result["tickets"]
    # show adds each reference material's "resolved" result to what the ticket stores
    for material in ticket["reference_materials"] or []:
        material.pop("resolved", None)
    return tuple(ticket[_SHOWN_AS.get(field, field)] for field in fields)


def _query_bees(via, cli_runner):
    query = "{stages: [[type=bee]]}"
    if via == "mcp":
        return mcp_success(execute_freeform_query(query_yaml=query))["ticket_ids"]
    return cli_success(cli_runner, "execute-freeform-query", f"--query-yaml={query}")["ticket_ids"]


@pytest.mark.parametrize("field,value", [
    *[pytest.param(field, DASH_VALUES[key], id=f"{field}-{key}") for key in _E2E_VALUES for field in _FIELDS],
    # b.gg4: the cases of the bug report (each unreadable, or read back changed, before the fix)
    *[pytest.param(field, QUOTING_VALUES[key], id=f"{field}-{key}") for field, key in _QUOTING_E2E],
])
@pytest.mark.parametrize("op", ["create", "update"])
@pytest.mark.parametrize("via", ["cli", "mcp"])
def test_value_survives_show_update_and_query(hive_env, cli_runner, via, op, field, value):
    """A value holding --- or YAML syntax shows with its real guid and body, survives another update, is queryable."""
    _, hive_dir, _ = hive_env
    arg = {"tags": [value], "reference_materials": [{"value": value}]}.get(field, value)
    ticket_id = _create(via, cli_runner, **({field: arg} if op == "create" else {}))
    # The file the create wrote is correct, also before the fix: its guid is the real one
    guid = re.search(r"^guid: (\S+)$", compute_ticket_path(ticket_id, hive_dir).read_text(), re.MULTILINE)[1]
    if op == "update":
        _update(via, cli_runner, ticket_id, **{field: arg})

    assert _shown(via, cli_runner, ticket_id, field, "guid", "body") == (arg, guid, _BODY)

    other = "title" if field == "status" else "status"
    _update(via, cli_runner, ticket_id, **{other: "next"})

    assert _shown(via, cli_runner, ticket_id, field, other, "guid", "body") == (arg, "next", guid, _BODY)
    assert ticket_id in _query_bees(via, cli_runner)
