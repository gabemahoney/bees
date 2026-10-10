"""Build the bees-md 0.8.4 upgrade-compat fixture corpus (tests/fixtures/compat_0_8_4/).

Run it with the python of a throwaway venv holding the RELEASED bees-md 0.8.4 from PyPI,
never with this checkout's code or a pipx install:

    python3 -m venv <scratch>/venv084
    <scratch>/venv084/bin/pip install bees-md==0.8.4
    <scratch>/venv084/bin/python scripts/generate_compat_fixtures.py

It works in a fresh temp dir with its own HOME, so it never touches a real hive or the
real ~/.bees/config.json. Every ticket is written by the 0.8.4 CLI from synthetic
content. The few hand edits that 0.8.4 cannot make (22-character guids from pre-0.1.3
builds, a file checked out with CRLF line endings) are applied by `_post_process` and
listed in manifest.json. Then 0.8.4 itself records what it reads (expected.json):
parse_frontmatter of every ticket file, show-ticket of every live ticket, the config
reads, a query per hive, and the bytes its own read-and-save-unchanged writes.

Output (replaced on every run):
    tree/repo/       the repo: hives features, Bugs, Ideas (with Plans nested in it) and
                     shared-hive (registered in a glob scope, not the repo's own scope)
    global_config.json   ~/.bees/config.json, with the temp root as {{ROOT}}
    manifest.json    ticket roles, the inputs given to 0.8.4, and the hand edits
    expected.json    what 0.8.4 reads
"""

import argparse
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

BEES_VERSION = "0.8.4"
ROOT_PLACEHOLDER = "{{ROOT}}"
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "compat_0_8_4"

# Titles with YAML-special text. Only those 0.8.4 writes and reads back unchanged are kept.
SPECIAL_TITLES = [
    "key: value", "ends with colon:", "#not a comment", "a # hash", "'single quoted'",
    '"double quoted"', "[bracketed]", "{braced}", "&anchor", "*alias", "!tag", "|pipe",
    ">folded", "@at", "`tick`", "%percent", "?question", ",comma", "yes", "No", "null",
    "~", "true", "123", "1.5", "1e3", "0x1F", "0o17", "2026-10-10", "2026-10-10T12:00:00",
    "12:30", "- dash item", "-leading dash", "  padded  ", "tab\tinside", "quote's",
    "unicode ünïcödé 日本語 🐝", "rtl עברית", "nbsp\u00a0inside", "zero\u200bwidth",
    "back\\slash", "ends with backslash\\", "percent %s and {braces}", "...", "=", "<<",
    "!!str", "|-", "multi\nline title", "line\u2028separator", "nel\x85inside",
]
SPECIAL_TAGS = [
    "priority:1", "key: v", "#tag", "yes", "123", "日本", "🐝", "- x", "a,b", "[x]",
    "back\\slash", " spaced ", "null", "2026-10-10", "&a", "*b", "!c", "%d", "@e", "`f`",
]
SPECIAL_STATUSES = ["in review: maybe", "yes", "null", "~", "#hash", "123", "ünïcödé"]

BODIES = {
    "plain": "Plain body.",
    "trailing_nl": "Ends with one newline.\n",
    "trailing_nls": "Ends with three newlines.\n\n\n",
    "leading_spaces": "    Indented first line\nsecond line",
    "leading_nl": "\n\nStarts after blank lines",
    "trailing_spaces": "Trailing spaces   ",
    "whitespace_only": "   \n\t\n  ",
    "crlf": "Line one\r\nLine two\r\n",
    "lone_cr": "old mac\rline",
    "tabs": "col1\tcol2\n\tindented by tab",
    "backslashes": "regex \\d+\\s* and C:\\Program Files\\x and \\\\server\\share and trailing \\",
    "escapes_expanded_by_084": "0.8.4 turned these into real characters: \\n and \\t",
    "unicode": "Ünïcödé 日本語 🐝🍯 עברית\u00a0nbsp \u200bzw \u2028LS \u2029PS \x85NEL",
    "control": "bell\x07 vt\x0b ff\x0c esc\x1b",
    "markdown": "# Heading\n\n- item\n- item\n\n```python\nprint('---')\n```\n\n---\n\n> quote\n",
    "dash_lines": "---\nstarts with dashes\n---",
    "yaml_like": "key: value\n- list\n---\nid: fake\nschema_version: '9'\n",
}

# Hives with status values need a status on create; ideas is freeform
DEFAULT_STATUS = {"features": "open", "plans": "open", "shared_hive": "open", "bugs": "draft"}

REFERENCE_MATERIALS = [
    {"value": "docs/spec.md"},
    {"value": "b.abc", "resolver": "bees"},
    {"value": "notes with spaces/and: colon.md"},
    {"value": "unicode/ünï.md"},
    {"value": "C:\\Windows\\path.txt"},
    {"value": "yes"},
    {"value": "#123 'quoted'"},
]


class Generator:
    def __init__(self, bees_bin: Path, root: Path):
        self.bees_bin = bees_bin
        self.root = root
        self.home = root / "home"
        self.repo = root / "repo"
        self.shared = self.repo / "shared-hive"
        self.env = {**os.environ, "HOME": str(self.home), "USERPROFILE": str(self.home)}
        self.roles: dict[str, str] = {}
        self.inputs: dict[str, dict] = {}
        self.dropped: dict[str, list] = {"titles": [], "tags": [], "statuses": []}
        self.post_processed: list[dict] = []

    # --- 0.8.4 CLI ------------------------------------------------------------------

    def bees(self, *args: str, ok: bool = True) -> dict:
        proc = subprocess.run(
            [str(self.bees_bin), *args], cwd=self.repo, env=self.env, capture_output=True, text=True
        )
        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            result = {"status": "crash", "error": _exception_message(proc.stderr)}
        if ok and result.get("status") != "success":
            raise RuntimeError(f"bees {' '.join(args)} failed: {result}")
        return result

    def create(self, role: str | None, ticket_type: str, title: str, hive: str, *, body: str | None = None,
               parent: str | None = None, tags: list | None = None, status: str | None = None,
               refs: list | None = None, up: list | None = None, body_file: str | None = None) -> str:
        if status is None:
            status = DEFAULT_STATUS.get(hive)
        args = ["create-ticket", "--ticket-type", ticket_type, f"--title={title}", "--hive", hive]
        if body:
            args.append(f"--body={body}")
        if body_file is not None:
            path = self.root / "body_input.txt"
            path.write_bytes(body_file.encode("utf-8"))
            args += ["--body-file", str(path)]
        if parent:
            args += ["--parent", parent]
        if tags is not None:
            args += ["--tags", json.dumps(tags)]
        if status is not None:
            args.append(f"--status={status}")
        if refs is not None:
            args += ["--reference-materials", json.dumps(refs)]
        if up is not None:
            args += ["--up-deps", json.dumps(up)]
        ticket_id = self.bees(*args)["ticket_id"]
        if role:
            self.roles[role] = ticket_id
        self.inputs[ticket_id] = {
            "title": title, "body": body if body is not None else body_file, "tags": tags, "status": status,
            "reference_materials": refs,
        }
        return ticket_id

    def show(self, ticket_id: str) -> dict:
        return self.bees("show-ticket", "--ids", ticket_id, ok=False)

    # --- the corpus -------------------------------------------------------------------

    def build(self) -> None:
        for d in (self.home, self.repo / ".git"):
            d.mkdir(parents=True, exist_ok=True)
        self._config()
        self._features()
        self._bugs()
        self._ideas_and_nested_plans()
        self._shared()
        self._operations()
        self._dash_values_084_misreads()
        self._post_process()

    def _config(self) -> None:
        self.bees("colonize-hive", "--name", "Features", "--path", str(self.repo / "features"),
                  "--description", "Feature work: every tier, inherits tiers and statuses from the repo scope")
        self.bees("set-types", "--scope", "global", "--child-tiers", json.dumps({"t1": ["Task", "Tasks"]}))
        self.bees("set-status-values", "--scope", "global", "--status-values", json.dumps(["open", "done"]))
        self.bees("add-named-query", "--query-name", "global_open", "--scope", "global",
                  "--query-yaml", "stages:\n  - ['status=open']\n")
        self.bees("set-types", "--scope", "repo_scope", "--child-tiers",
                  json.dumps({"t1": ["Epic", "Epics"], "t2": ["Task", "Tasks"], "t3": ["Subtask", "Subtasks"]}))
        self.bees("set-status-values", "--scope", "repo_scope", "--status-values",
                  json.dumps(["draft", "open", "in_progress", "done"]))
        self.bees("colonize-hive", "--name", "Bugs", "--path", str(self.repo / "Bugs"), "--child-tiers", "{}",
                  "--status-values", json.dumps(["draft", "defined", "active", "done"]))
        self.bees("colonize-hive", "--name", "Ideas", "--path", str(self.repo / "Ideas"),
                  "--child-tiers", json.dumps({"t1": ["Idea Doc", "Idea Docs"]}), "--status-values", "null")
        self.bees("colonize-hive", "--name", "Plans", "--path", str(self.repo / "Ideas" / "Plans"),
                  "--child-tiers",
                  json.dumps({"t1": ["Epic", "Epics"], "t2": ["Task", "Tasks"], "t3": ["Subtask", "Subtasks"]}))
        self.bees("colonize-hive", "--name", "Shared Hive", "--path", str(self.shared),
                  "--scope", f"{self.root}/**")
        # Repo-scope queries last: colonize-hive drops a scope's named queries (b.4eb), in 0.8.4 too
        self.bees("add-named-query", "--query-name", "done_bees", "--scope", "repo",
                  "--query-yaml", "stages:\n  - ['type=bee', 'status=done']\n")
        self.bees("add-named-query", "--query-name", "bees_with_children", "--scope", "repo",
                  "--query-yaml", "stages:\n  - ['type=bee']\n  - ['children']\n")

    def _features(self) -> None:
        tree = self.create("tree_bee", "bee", "Tree bee with every tier", "features", body=BODIES["markdown"],
                           tags=["tree", "priority:1"], status="open", refs=REFERENCE_MATERIALS)
        t1a = self.create("tree_t1", "t1", "Epic A", "features", parent=tree, body=BODIES["trailing_nls"],
                          status="in_progress")
        self.create("tree_t1_b", "t1", "Epic B", "features", parent=tree, body=BODIES["crlf"], status="draft")
        t2 = self.create("tree_t2", "t2", "Task under A", "features", parent=t1a, body=BODIES["leading_spaces"],
                         status="open")
        self.create("tree_t3", "t3", "Subtask under task", "features", parent=t2, body=BODIES["unicode"])
        self.create("tree_t3_b", "t3", "Second subtask", "features", parent=t2, body=BODIES["tabs"],
                    tags=["日本", "🐝"])
        blocker = self.create("blocker_bee", "bee", "Blocker bee", "features", body=BODIES["trailing_nl"],
                              status="open")
        self.create("blocked_bee", "bee", "Blocked bee", "features", body=BODIES["leading_nl"], status="draft",
                    up=[blocker])
        # A t1 dependency between two epics of different bees
        other = self.create("dep_tree_bee", "bee", "Bee with a dependent epic", "features", status="open")
        other_t1 = self.create("dep_t1", "t1", "Epic that waits on Epic A", "features", parent=other,
                               body=BODIES["whitespace_only"])
        self.bees("update-ticket", "--ids", other_t1, "--up-deps", json.dumps([t1a]))
        for name in ("trailing_spaces", "lone_cr", "backslashes", "escapes_expanded_by_084", "control",
                     "dash_lines", "yaml_like", "plain"):
            self.create(f"body_{name}", "bee", f"Body {name}", "features", body=BODIES[name], status="open")
        self.create("body_file_bee", "bee", "Body from a file", "features", status="open",
                    body_file="From --body-file\r\nwith \\n and \\t escapes\n\n")
        self._special_titles_and_tags()
        # Bees archived by the undertaker in _operations: one with a subtree, one with an old guid
        archived = self.create("archived_bee", "bee", "Archived bee", "features", body=BODIES["plain"],
                               status="done")
        archived_t1 = self.create("archived_t1", "t1", "Archived epic", "features", parent=archived,
                                  body=BODIES["trailing_nl"], status="done")
        self.create("archived_t2", "t2", "Archived task", "features", parent=archived_t1, status="done")
        self.create("archived_guid22_bee", "bee", "Archived bee with a 22-character guid", "features",
                    status="done")
        # Old 22-character guids (pre-0.1.3 builds), on a bee and its child
        g22 = self.create("guid22_bee", "bee", "Bee with a 22-character guid", "features", status="open",
                          body=BODIES["plain"])
        self.create("guid22_t1", "t1", "Epic with a 22-character guid", "features", parent=g22, status="open")
        self.create("clone_source_bee", "bee", "Clone source", "features", status="draft", body="source body\n")
        self.create("clone_source_t1", "t1", "Clone source epic", "features", parent=self.roles["clone_source_bee"],
                    status="draft")
        self.create("appended_bee", "bee", "Body built by appends", "features", status="open",
                    body="First chunk ends with a newline\n")
        self.create("move_source_bee", "bee", "Bee moved to Bugs by 0.8.4", "features", status="draft",
                    body=BODIES["trailing_nl"])

    def _special_titles_and_tags(self) -> None:
        for i, title in enumerate(SPECIAL_TITLES):
            ticket_id = self.create(None, "bee", title, "features", status="open")
            shown = self.show(ticket_id)
            if shown.get("status") != "success" or shown["tickets"][0]["title"] != title:
                self.dropped["titles"].append({"title": title, "read_084": shown})
                self.bees("delete-ticket", "--ids", ticket_id)
                del self.inputs[ticket_id]
            else:
                self.roles[f"title_{i:02d}"] = ticket_id
        for tag in SPECIAL_TAGS:
            ticket_id = self.create(None, "bee", "Tag probe", "features", tags=[tag], status="open")
            shown = self.show(ticket_id)
            self.bees("delete-ticket", "--ids", ticket_id)
            del self.inputs[ticket_id]
            if shown.get("status") != "success" or shown["tickets"][0]["tags"] != [tag]:
                self.dropped["tags"].append({"tag": tag, "read_084": shown})
        kept = [t for t in SPECIAL_TAGS if t not in {d["tag"] for d in self.dropped["tags"]}]
        for i in range(0, len(kept), 5):
            self.create(f"tags_{i // 5}", "bee", f"Special tags {i // 5}", "features", tags=kept[i:i + 5],
                        status="open")

    def _bugs(self) -> None:
        self.create("bug_plain", "bee", "Bug with a plain body", "bugs", body=BODIES["plain"], status="draft",
                    tags=["bug", "priority:2"])
        self.create("bug_crlf_file", "bee", "Bug whose file is checked out with CRLF", "bugs",
                    body="Body line one\nBody line two\n", status="active", tags=["bug"])
        self.create("bug_guid22", "bee", "Bug with a 22-character guid", "bugs", status="defined")
        self.create("bug_cross_hive_dep", "bee", "Bug blocked by a feature", "bugs", status="draft",
                    up=[self.roles["blocker_bee"]], body=BODIES["trailing_nls"])
        self.create("bug_done", "bee", "Done bug, still live", "bugs", status="done", body=BODIES["unicode"])

    def _ideas_and_nested_plans(self) -> None:
        idea = self.create("idea_bee", "bee", "Idea with a doc", "ideas", body=BODIES["markdown"])
        self.create("idea_t1", "t1", "Idea doc", "ideas", parent=idea, body=BODIES["trailing_nl"])
        self.create("idea_plain", "bee", "Plain idea", "ideas")
        for i, status in enumerate(SPECIAL_STATUSES):
            ticket_id = self.create(None, "bee", f"Freeform status {i}", "ideas", status=status)
            shown = self.show(ticket_id)
            if shown.get("status") != "success" or shown["tickets"][0]["ticket_status"] != status:
                self.dropped["statuses"].append({"status": status, "read_084": shown})
                self.bees("delete-ticket", "--ids", ticket_id)
                del self.inputs[ticket_id]
            else:
                self.roles[f"status_{i}"] = ticket_id
        plan = self.create("plan_bee", "bee", "Plan in the nested hive", "plans", body=BODIES["leading_spaces"],
                           status="open", refs=[{"value": idea, "resolver": "bees"}])
        p1 = self.create("plan_t1", "t1", "Plan epic", "plans", parent=plan, status="open",
                         body=BODIES["trailing_nls"])
        p2 = self.create("plan_t2", "t2", "Plan task", "plans", parent=p1, status="draft", body=BODIES["crlf"])
        self.create("plan_t3", "t3", "Plan subtask", "plans", parent=p2, status="draft")
        self.create("plan_dep_bee", "bee", "Plan blocked by the idea's sibling", "plans", status="draft",
                    up=[plan])

    def _shared(self) -> None:
        bee = self.create("shared_bee", "bee", "Bee in a hive of a glob scope", "shared_hive", status="open",
                          body=BODIES["trailing_nl"])
        self.create("shared_t1", "t1", "Task in the glob-scope hive", "shared_hive", parent=bee, status="open")

    def _operations(self) -> None:
        r = self.roles
        # Old guids first, so the 0.8.4 operations below run on them
        for role in ("guid22_bee", "guid22_t1", "bug_guid22", "archived_guid22_bee"):
            self._truncate_guid(r[role])
        self.bees("update-ticket", "--ids", r["tree_bee"], "--add-tags", json.dumps(["updated-by-084"]))
        self.bees("update-ticket", "--ids", r["tree_t2"], "--status", "in_progress")
        self.bees("update-ticket", "--ids", r["blocked_bee"], "--title", "Blocked bee (renamed by 0.8.4)")
        self.bees("update-ticket", "--ids", r["guid22_bee"], "--remove-tags", json.dumps(["nothing"]),
                  "--status", "in_progress")
        for chunk in ("Second chunk, no newline", "\nThird chunk ends with two newlines\n\n",
                      "Fourth chunk with \\n escape and " + "x" * 300):
            self.bees("append-ticket-body", "--ticket-id", r["appended_bee"], f"--chunk={chunk}")
        self.bees("move-bee", "--ids", r["move_source_bee"], "--hive", "bugs")
        self.roles["moved_bee"] = self.roles.pop("move_source_bee")
        clone = self.bees("clone", "--bee-id", r["clone_source_bee"])
        self.roles["cloned_bee"] = clone["ticket_id"] if "ticket_id" in clone else clone["new_bee_id"]
        self.bees("undertaker", "--hive", "features", "--query-yaml", "stages:\n  - ['type=bee', 'status=done']\n")
        self.bees("generate-index")

    def _dash_values_084_misreads(self) -> None:
        """b.5yy: 0.8.4 writes these correctly but misreads them. Created last: a 0.8.4 write of a
        ticket it misreads would damage the file."""
        self.create("dash_ref_bee", "bee", "Reference material with three dashes", "features", status="open",
                    refs=[{"value": "http://example.com/a---b"}], body=BODIES["plain"])
        self.create("dash_tag_bee", "bee", "Tag with three dashes", "ideas", tags=["a---b"],
                    body=BODIES["trailing_nl"])

    # --- hand edits 0.8.4 cannot make ------------------------------------------------------

    def _ticket_file(self, ticket_id: str) -> Path:
        matches = [p for p in self.root.rglob(f"{ticket_id}.md") if p.parent.name == ticket_id]
        assert len(matches) == 1, (ticket_id, matches)
        return matches[0]

    def _truncate_guid(self, ticket_id: str) -> None:
        path = self._ticket_file(ticket_id)
        text = path.read_bytes().decode("utf-8")
        lines = text.split("\n")
        idx = next(i for i, line in enumerate(lines) if line.startswith("guid: "))
        lines[idx] = lines[idx][: len("guid: ") + 22]
        path.write_bytes("\n".join(lines).encode("utf-8"))
        self.post_processed.append({"ticket_id": ticket_id, "edit": "guid cut to 22 characters (pre-0.1.3 build)"})

    def _post_process(self) -> None:
        path = self._ticket_file(self.roles["bug_crlf_file"])
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        self.post_processed.append({"ticket_id": self.roles["bug_crlf_file"],
                                    "edit": "whole file converted to CRLF (git core.autocrlf checkout)"})

    # --- what 0.8.4 reads ----------------------------------------------------------------

    def ticket_files(self) -> list[Path]:
        """Every ticket file: <dir>/<dir>.md, live or in a cemetery."""
        files = [p for p in self.root.rglob("*.md") if p.stem == p.parent.name]
        return sorted(files, key=lambda p: self.rel(p))

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def record(self) -> dict:
        from src.parser import parse_frontmatter

        expected: dict = {"parse": {}, "show": {}, "rewrite": {}, "config": {}, "queries": {}}
        for path in self.ticket_files():
            rel = self.rel(path)
            try:
                frontmatter, body = parse_frontmatter(path)
                expected["parse"][rel] = {"frontmatter": _jsonable(frontmatter), "body": body}
            except Exception as e:  # noqa: BLE001 - record any 0.8.4 read failure as data
                expected["parse"][rel] = {"error": type(e).__name__}
            expected["rewrite"][rel] = self._rewrite_084(path)
            if "/cemetery/" not in f"/{rel}":
                shown = self.show(path.stem)
                expected["show"][path.stem] = shown["tickets"][0] if shown["status"] == "success" else {
                    "error": shown["status"]}
        expected["config"] = {
            "list_hives": self.bees("list-hives"),
            "get_types": self.bees("get-types"),
            "get_status_values": self.bees("get-status-values"),
            "list_named_queries": self.bees("list-named-queries"),
        }
        for hive in ("features", "bugs", "ideas", "plans", "shared_hive"):
            expected["queries"][hive] = self.bees(
                "execute-freeform-query", "--query-yaml", query_yaml_for_hive(hive), ok=False)
        return expected

    def _rewrite_084(self, path: Path) -> dict:
        """0.8.4's own read-then-save-unchanged of a copy of the file: None when byte-identical."""
        from src import cache
        from src.parser import parse_frontmatter
        from src.reader import read_ticket
        from src.writer import write_ticket_file

        copy = self.root / "rewrite" / path.parent.name / path.name
        copy.parent.mkdir(parents=True)
        shutil.copyfile(path, copy)
        try:
            cache.clear()
            ticket_id = parse_frontmatter(copy)[0]["id"]
            ticket = read_ticket(ticket_id, file_path=copy)
            data = asdict(ticket)
            body = data.pop("body")
            write_ticket_file(ticket_id, ticket.type, data, body, file_path=copy)
            new = copy.read_bytes()
            return {"bytes": None if new == path.read_bytes() else new.decode("utf-8")}
        except Exception as e:  # noqa: BLE001 - record any 0.8.4 failure as data
            return {"error": type(e).__name__}
        finally:
            shutil.rmtree(copy.parent.parent)


def _exception_message(stderr: str) -> str:
    """The exception line(s) that end a traceback, without the file paths of the traceback above them."""
    lines = stderr.rstrip("\n").split("\n")
    start = max((i for i, line in enumerate(lines) if re.match(r"[\w.]+(Error|Exception)\b", line)), default=0)
    return "\n".join(lines[start:])


def query_yaml_for_hive(hive: str) -> str:
    """Every ticket of a hive (tests/test_upgrade_compat.py runs the same query)."""
    return f"stages:\n  - ['hive={hive}']\n"


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return {"datetime": value.isoformat()}
    return value


def _check_environment() -> None:
    version = importlib.metadata.version("bees-md")
    if version != BEES_VERSION:
        sys.exit(f"bees-md {version} is installed here; run this with the python of a venv holding {BEES_VERSION}")
    import src

    checkout = Path(__file__).resolve().parent.parent
    if Path(src.__file__).resolve().is_relative_to(checkout):
        sys.exit("src was imported from this checkout, not from the installed bees-md 0.8.4")


def _write_output(gen: Generator, expected: dict, out: Path) -> None:
    def placeholder(text: str) -> str:
        return text.replace(str(gen.root), ROOT_PLACEHOLDER)

    empty = [p for p in gen.root.rglob("*") if p.is_dir() and not any(p.iterdir()) and p.name != ".git"]
    if empty:
        sys.exit(f"git cannot store empty directories: {empty}")
    if out.exists():
        for name in ("tree", "global_config.json", "manifest.json", "expected.json"):
            target = out / name
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(gen.repo, out / "tree" / "repo", ignore=shutil.ignore_patterns(".git"))
    config = (gen.home / ".bees" / "config.json").read_text(encoding="utf-8")
    (out / "global_config.json").write_text(placeholder(config), encoding="utf-8")
    manifest = {
        "bees_version": BEES_VERSION,
        "roles": gen.roles,
        "inputs": gen.inputs,
        "post_processed": gen.post_processed,
        "dropped_by_084_read_check": gen.dropped,
    }
    for name, data in (("manifest.json", manifest), ("expected.json", expected)):
        text = json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
        (out / name).write_text(placeholder(text), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    _check_environment()
    bees_bin = Path(sys.executable).parent / "bees"
    with tempfile.TemporaryDirectory(prefix="bees_compat_") as tmp:
        root = Path(tmp) / "root"
        root.mkdir()
        os.environ["HOME"] = str(root / "home")  # before 0.8.4 code is imported
        gen = Generator(bees_bin, root)
        gen.build()
        expected = gen.record()
        _write_output(gen, expected, args.out)
    print(json.dumps({"out": str(args.out), "dropped_by_084_read_check": gen.dropped}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
