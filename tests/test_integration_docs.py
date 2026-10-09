"""
Static checks that the developer docs give the real integration test entry point, and the CI prerequisites
a new machine needs (b.6yu).

PURPOSE:
tests/integration.sh runs only inside a CI phase container: it stops outside the container's /test-repo, and it
overwrites ~/.bees/config.json. On a host, integration tests run through /ci, which runs docker/run_test.sh <phase>
per phase. docs/architecture/testing.md told developers to run `PHASE=<phase> bash tests/integration.sh` on their
host. A new machine also needs the credentials the CI scripts read (Claude auth for the containers, a TestPyPI
token for the publish step) and the tools they run, which no doc listed. These tests read the docs and the CI
scripts as text and never run a script.

SCOPE - Tests that belong here:
- no developer doc gives a shell command that runs integration.sh: README.md, CONTRIBUTING.md, CLAUDE.md,
  docs/**/*.md, tests/TESTING.md and the /ci skill, in fenced code blocks (continued lines joined) and inline code
  spans. Prose, an inline span that only names the script, or `bash -n` (parse only) is fine. docker/testplans/** is
  not scanned: its tests are executed inside the container, from /test-repo.
- the `## CI prerequisites` section of docs/architecture/testing.md: it names every home file and credential env var
  docker/run_test.sh and docker/publish_test_pypi.sh read (found by parsing the scripts), how to get the tokens, and
  in its Tools table the tools CI runs, and no machine-specific path; CONTRIBUTING.md links to it

SCOPE - Tests that DON'T belong here:
- bees CLI commands in the docs -> test_docs_cli_examples.py
- the phases and sections integration.sh runs, and which runner runs each phase -> test_integration_phases.py
- what /ci and the CI scripts do -> test_ci_skill.py, test_check_bees_server.py
"""

import re
import shlex
from pathlib import Path, PurePosixPath

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTING_DOC = REPO_ROOT / "docs" / "architecture" / "testing.md"
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"
CI_SCRIPTS = [REPO_ROOT / "docker" / "run_test.sh", REPO_ROOT / "docker" / "publish_test_pypi.sh"]
# No existence filter: a doc that moves must fail the scan, not drop out of it
DEV_DOCS = [
    REPO_ROOT / "README.md",
    CONTRIBUTING,
    REPO_ROOT / "CLAUDE.md",
    *sorted((REPO_ROOT / "docs").rglob("*.md")),
    REPO_ROOT / "tests" / "TESTING.md",
    REPO_ROOT / ".claude" / "skills" / "ci" / "SKILL.md",
]

PREREQUISITES_HEADING = "## CI prerequisites"
PREREQUISITES_ANCHOR = "ci-prerequisites"  # GitHub's anchor for the heading
TOOLS_HEADING = "### Tools"

FENCE = re.compile(r"\s*(```|~~~)")
INLINE_CODE = re.compile(r"`([^`\n]+)`")
PROMPT = re.compile(r"\s*\$\s+")
PLACEHOLDER = re.compile(r"<[A-Za-z][^<>\n]*>")
HEADING = re.compile(r"#{1,2} ")
SUBHEADING = re.compile(r"#{1,3} ")

# Words before the command that still run it: assignments, and wrappers with their options, option values and
# durations: `PHASE=2 bash x`, `sudo -u me env PHASE=2 x`, `timeout 600 nice -n 10 bash x`. Not `docker` or `exec`: a
# doc may quote a `docker exec`, or docker/test_runner.sh's `exec bash .../integration.sh`, which run in a container.
_ASSIGNMENT = re.compile(r"[A-Za-z_]\w*=")
_WRAPPERS = {"env", "sudo", "time", "nohup", "command", "timeout", "nice"}
_NUMBER = re.compile(r"\d+(?:\.\d+)?[smhd]?")
_SHELLS = {"bash", "sh", "zsh", "dash", "source", "."}
# A shell option cluster with n only parses the script: test_integration_phases.py runs `bash -n` on it
_PARSE_ONLY = re.compile(r"-[A-Za-z]*n[A-Za-z]*")

# Home files: ~/x or $HOME/x
_HOME_FILE = re.compile(r"(?:~|\$HOME\b|\$\{HOME\})/([\w.-]+(?:/[\w.-]+)*)")
_VAR_READ = re.compile(r"\$\{?([A-Z][A-Z0-9_]*)")
# NAME=... as a shell assignment, not inside a word or string ("-e NAME=$x" passes a value on, it sets nothing)
_ASSIGNED = re.compile(r"(?:^|[\s;&|(!])(?:export\s+|local\s+|readonly\s+)?([A-Za-z_]\w*)=")
_CREDENTIAL_NAME = re.compile(r"TOKEN|API_KEY|SECRET|PASSWORD")
# The b.6yu addendum asks for the section to stay generic: the repo is public and used on many kinds of machines
_MACHINE_PATH = re.compile(r"/home/|/Users/")

# How a new machine gets the credentials, and the tools CI needs (b.6yu addendum)
SETUP_NAMES = ["claude setup-token", "[testpypi]", "BEES_CI_PORT"]
CI_TOOLS = ["docker", "rsync", "tmux", "twine", "poetry"]


# ---------------------------------------------------------------------------
# Running integration.sh
# ---------------------------------------------------------------------------


def _simple_commands(text):
    """The simple commands (word lists) of a shell line, as a shell splits them; none if it does not lex as shell."""
    lexer = shlex.shlex(PLACEHOLDER.sub("X", PROMPT.sub("", text, count=1)), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:  # an unclosed quote: prose or another language
        return []
    commands, words, redirect_target = [], [], False
    for token in tokens:
        if redirect_target:
            redirect_target = False
        elif set(token) <= set("();<>|&"):
            redirect_target = "<" in token or ">" in token
            if not redirect_target and words:
                commands.append(words)
                words = []
        else:
            words.append(token)
    return [*commands, words] if words else commands


def _is_script(word):
    return PurePosixPath(word).name == "integration.sh"


def _command_start(words):
    """Index of the shell or script a simple command runs, past the assignments and wrappers before it; None if the
    command is another one."""
    after_option = False
    for index, word in enumerate(words):
        if word in _SHELLS or _is_script(word):
            return index
        if not (
            after_option
            or _ASSIGNMENT.match(word)
            or word in _WRAPPERS
            or word.startswith("-")
            or _NUMBER.fullmatch(word)
        ):
            return None
        after_option = word.startswith("-")
    return None


def _runs_script(text, fenced):
    """Whether a shell line runs integration.sh. An inline span of the bare path only names the script, while in a
    code block a path with a slash runs it."""
    for words in _simple_commands(text):
        start = _command_start(words)
        if start is None:
            continue
        command, args = words[start], words[start + 1 :]
        if command in _SHELLS:
            # The script may follow an option value (`bash -o pipefail x`); `bash -n x` only parses it
            scripts = [index for index, word in enumerate(args) if _is_script(word)]
            if scripts and not any(_PARSE_ONLY.fullmatch(word) for word in args[: scripts[0]]):
                return True
        elif start > 0 or args or command.startswith("./") or (fenced and "/" in command):
            return True
    return False


def _script_runs(path, root=REPO_ROOT):
    """`file:line: text` of each fenced line or inline code span in a doc that runs integration.sh, at the line a
    continued command starts on."""
    rel = path.relative_to(root).as_posix()
    found, in_fence, held, held_from = [], False, "", None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if FENCE.match(line):
            in_fence, held, held_from = not in_fence, "", None
            continue
        if in_fence and line.rstrip().endswith("\\"):
            held, held_from = held + line.rstrip()[:-1] + " ", held_from or number
            continue
        candidates = [(held + line, True)] if in_fence else []
        candidates += [(span, False) for span in INLINE_CODE.findall(line)]
        if any(_runs_script(text, fenced) for text, fenced in candidates):
            found.append(f"{rel}:{held_from or number}: {(held + line).strip()}")
        held, held_from = "", None
    return found


@pytest.mark.parametrize(
    "text, fenced, runs",
    [
        pytest.param("PHASE=<phase> bash tests/integration.sh", True, True, id="phase_and_bash"),
        pytest.param("PHASE=<phase> bash tests/integration.sh <test_number>", False, True, id="inline_command"),
        pytest.param("$ ./tests/integration.sh", True, True, id="prompt_and_dot_slash"),
        pytest.param("mv a b && sudo -E env PHASE=2 sh -x tests/integration.sh 5", True, True, id="wrapped_after_and"),
        pytest.param("timeout 600 bash tests/integration.sh", True, True, id="timeout_duration"),
        pytest.param("sudo -u someone bash tests/integration.sh", False, True, id="sudo_user"),
        pytest.param("nice -n 10 bash tests/integration.sh", True, True, id="wrapper_n_is_not_the_shells"),
        pytest.param("bash -o pipefail tests/integration.sh", True, True, id="shell_option_value"),
        pytest.param("PHASE=2 \\\n  bash tests/integration.sh 5", True, True, id="continued_line"),
        pytest.param("tests/integration.sh", True, True, id="path_alone_in_code_block"),
        pytest.param("tests/integration.sh", False, False, id="inline_name_only"),
        pytest.param("bash -n tests/integration.sh", True, False, id="parse_only"),
        pytest.param("# never run bash tests/integration.sh on a host", True, False, id="shell_comment"),
        pytest.param("docker exec bees-ci-2 bash tests/integration.sh", True, False, id="inside_the_container"),
    ],
)
def test_script_run_detection_tells_commands_from_names(tmp_path, text, fenced, runs):
    """The scan below finds nothing once the docs are fixed, so it is checked on a doc of its own here, with the
    text in a code block or an inline span. A run is reported at the line its command starts on."""
    doc = tmp_path / "doc.md"
    doc.write_text(f"```bash\n{text}\n```\n" if fenced else f"Intro.\nRun `{text}` here.\n", encoding="utf-8")

    found = _script_runs(doc, root=tmp_path)

    assert [run.split(": ")[0] for run in found] == (["doc.md:2"] if runs else []), found


def test_no_doc_runs_integration_sh():
    """Regression b.6yu: testing.md told developers to run `PHASE=<phase> bash tests/integration.sh` locally."""
    runs = [run for path in DEV_DOCS for run in _script_runs(path)]

    assert runs == [], (
        "doc commands that run tests/integration.sh, which runs only in the CI container (it stops outside "
        "/test-repo and overwrites ~/.bees/config.json). Point at /ci (docker/run_test.sh <phase>) instead, and name "
        "the script only in prose:\n" + "\n".join(runs)
    )


# ---------------------------------------------------------------------------
# CI prerequisites
# ---------------------------------------------------------------------------


def _code_lines(script):
    return [line for line in script.read_text().splitlines() if not line.lstrip().startswith("#")]


def _ci_credentials():
    """The home files the CI scripts read, and the credential env vars they read before setting them, if ever."""
    files, env_vars = set(), set()
    for script in CI_SCRIPTS:
        assigned = set()
        for line in _code_lines(script):
            files |= {f"~/{path}" for path in _HOME_FILE.findall(line)}
            # Not an input: a var the script sets before it reads it, like TEST_PYPI_TOKEN from its own lookup
            reads = set(_VAR_READ.findall(line)) - assigned
            env_vars |= {name for name in reads if _CREDENTIAL_NAME.search(name)}
            assigned |= set(_ASSIGNED.findall(line))
    return files, env_vars


def _prerequisites():
    """The text of testing.md's CI prerequisites section, to the next heading of level 1 or 2 outside a code block."""
    section, in_fence = None, False
    for line in TESTING_DOC.read_text(encoding="utf-8").splitlines():
        in_fence ^= bool(FENCE.match(line))
        heading = not in_fence and HEADING.match(line)
        if heading and section is not None:
            break
        if section is not None:
            section.append(line)
        elif heading and line.rstrip() == PREREQUISITES_HEADING:
            section = []
    assert section is not None, f"{TESTING_DOC.name} has no `{PREREQUISITES_HEADING}` section"
    return "\n".join(section)


def _listed_tools():
    """The first-column cells of the table under `### Tools` in the CI prerequisites section, header row left out."""
    lines = _prerequisites().splitlines()
    assert TOOLS_HEADING in lines, f"`{PREREQUISITES_HEADING}` has no `{TOOLS_HEADING}` subsection"
    rows = []
    for line in lines[lines.index(TOOLS_HEADING) + 1 :]:
        if SUBHEADING.match(line):
            break
        if line.startswith("|"):
            rows.append(line.split("|")[1].strip())
    assert len(rows) > 2, f"`{TOOLS_HEADING}` has no table with a row per tool"
    return rows[2:]  # past the header and its |---| line


def test_ci_prerequisites_name_every_credential_the_ci_scripts_read():
    """b.6yu addendum: a new machine needs the credential files and env vars CI reads, which no doc listed."""
    files, env_vars = _ci_credentials()
    # So a parsing fault cannot leave nothing to check: what the scripts read now
    assert {"~/.secrets/claude_oauth_token", "~/.secrets/anthropic_api_key", "~/.pypirc"} <= files, files
    assert {"CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"} <= env_vars, env_vars

    section = _prerequisites()

    missing = sorted(name for name in files | env_vars if name not in section)
    assert missing == [], f"`{PREREQUISITES_HEADING}` does not name what the CI scripts read: {missing}"


def test_ci_prerequisites_say_how_to_get_the_tokens_and_the_tools():
    code = "\n".join(line for script in CI_SCRIPTS for line in _code_lines(script))
    # The tools checked are ones the CI scripts run
    assert [tool for tool in CI_TOOLS if not re.search(rf"\b{tool}\b", code)] == []

    section = _prerequisites()
    tools = _listed_tools()

    missing = [name for name in SETUP_NAMES if name not in section]
    assert missing == [], f"`{PREREQUISITES_HEADING}` does not name: {missing}"
    unlisted = [tool for tool in CI_TOOLS if not any(re.search(rf"\b{tool}\b", cell, re.I) for cell in tools)]
    assert unlisted == [], f"the `{TOOLS_HEADING}` table of `{PREREQUISITES_HEADING}` does not list: {unlisted}"


def test_ci_prerequisites_name_no_machine_specific_paths():
    found = sorted(set(_MACHINE_PATH.findall(_prerequisites())))

    assert found == [], f"`{PREREQUISITES_HEADING}` names machine-specific paths: {found}"


def test_contributing_links_to_ci_prerequisites():
    text = CONTRIBUTING.read_text(encoding="utf-8")
    # Inline [text](path#anchor) and reference [label]: path#anchor links
    links = re.findall(r"(?:\]\(<?|^\[[^\]\n]+\]:\s*<?)([^)#\s>]*)#([\w-]+)", text, re.M)

    assert (TESTING_DOC, PREREQUISITES_ANCHOR) in {
        ((CONTRIBUTING.parent / path).resolve(), anchor) for path, anchor in links
    }, f"{CONTRIBUTING.name} must link to docs/architecture/testing.md#{PREREQUISITES_ANCHOR}"
