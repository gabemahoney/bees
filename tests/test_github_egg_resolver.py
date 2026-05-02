"""Unit tests for the GitHub Issues/PR reference_materials resolver."""

import json
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from tests.test_constants import (
    GITHUB_API_COMMENTS,
    GITHUB_API_ISSUE,
    GITHUB_API_RESPONSE,
    GITHUB_ENTERPRISE_URL,
    GITHUB_ISSUE_URL,
    GITHUB_PR_URL,
)

# Import the resolver module under test
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "resolvers"))
from github_resolver import main, parse_github_url  # noqa: E402


# ---------------------------------------------------------------------------
# URL parsing tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    pytest.param(
        GITHUB_ISSUE_URL,
        ("github.com", "cli", "cli", 1),
        id="github_com_issue",
    ),
    pytest.param(
        GITHUB_ENTERPRISE_URL,
        ("github.example.com", "org", "repo", 42),
        id="enterprise_issue",
    ),
    pytest.param(
        GITHUB_PR_URL,
        ("github.com", "cli", "cli", 1),
        id="github_com_pr",
    ),
])
def test_parse_github_url_valid(url, expected):
    assert parse_github_url(url) == expected


# ---------------------------------------------------------------------------
# Malformed URL
# ---------------------------------------------------------------------------

def test_parse_github_url_malformed():
    with pytest.raises(ValueError, match="Not a valid GitHub"):
        parse_github_url("https://github.com/no-issue-path")


# ---------------------------------------------------------------------------
# Invalid issue number (zero)
# ---------------------------------------------------------------------------

def test_parse_github_url_zero_number():
    with pytest.raises(ValueError, match="must be positive"):
        parse_github_url("https://github.com/owner/repo/issues/0")


# ---------------------------------------------------------------------------
# main() integration via subprocess (drives the full argparse + logic path)
# ---------------------------------------------------------------------------

def _run_main(value, extra_env=None):
    """Helper: run github_resolver.py as a subprocess and return CompletedProcess."""
    resolver_path = str(
        __import__("pathlib").Path(__file__).parent.parent / "resolvers" / "github_resolver.py"
    )
    import os
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, resolver_path, "--repo-root", "/tmp", "--value", value],
        capture_output=True,
        text=True,
        env=env,
    )


def test_null_egg_passthrough():
    """null egg → 'null' on stdout, exit 0."""
    result = _run_main("null")
    assert result.returncode == 0
    assert result.stdout.strip() == "null"
    assert result.stderr == ""


def test_empty_string_rejected():
    """Empty string → non-zero exit with error on stderr."""
    result = _run_main("")
    assert result.returncode != 0
    assert result.stderr.strip() != ""


def test_malformed_url_error():
    """Malformed URL → non-zero exit with error on stderr."""
    result = _run_main("not-a-url")
    assert result.returncode != 0
    assert result.stderr.strip() != ""


# ---------------------------------------------------------------------------
# Tests using mocks (import main directly)
# ---------------------------------------------------------------------------

def _invoke_main(value):
    """Invoke main() with sys.argv patched; return exit code."""
    with patch("sys.argv", ["github_resolver.py", "--repo-root", "/tmp", "--value", value]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    return exc_info.value.code


def test_gh_not_found(capsys):
    """gh absent from PATH → non-zero exit, error on stderr."""
    with patch("github_resolver.shutil.which", return_value=None):
        code = _invoke_main(GITHUB_ISSUE_URL)
    assert code != 0
    captured = capsys.readouterr()
    assert "gh" in captured.err.lower() or "not" in captured.err.lower()


def _make_gh_mock(returncode=0, stdout="", stderr=""):
    """Create a mock subprocess result."""
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


def _success_side_effect(*args, **kwargs):
    """Mock subprocess.run for two calls: issue then comments, both succeed."""
    cmd = args[0]
    api_path = cmd[cmd.index("api") + 1]
    if "/comments" in api_path:
        return _make_gh_mock(stdout=json.dumps(GITHUB_API_COMMENTS))
    return _make_gh_mock(stdout=json.dumps(GITHUB_API_ISSUE))


def test_gh_auth_failure(capsys):
    """gh returns non-zero (auth failure) → non-zero exit, error on stderr."""
    mock_result = _make_gh_mock(returncode=1, stderr="error connecting to github.com: authentication required")
    with patch("github_resolver.shutil.which", return_value="/usr/bin/gh"):
        with patch("github_resolver.subprocess.run", return_value=mock_result):
            code = _invoke_main(GITHUB_ISSUE_URL)
    assert code != 0
    captured = capsys.readouterr()
    assert "auth" in captured.err.lower() or captured.err.strip() != ""


@pytest.mark.parametrize("status_code,stderr_snippet,check_owner_repo_num", [
    pytest.param(1, "HTTP 404: Not Found", True, id="404_not_found"),
    pytest.param(1, "HTTP 403: Forbidden", False, id="403_forbidden"),
    pytest.param(1, "HTTP 429: Too Many Requests", False, id="429_rate_limit"),
])
def test_api_errors(capsys, status_code, stderr_snippet, check_owner_repo_num):
    """API errors on issue fetch → non-zero exit, appropriate error on stderr."""
    mock_result = _make_gh_mock(returncode=status_code, stderr=stderr_snippet)
    with patch("github_resolver.shutil.which", return_value="/usr/bin/gh"):
        with patch("github_resolver.subprocess.run", return_value=mock_result):
            code = _invoke_main(GITHUB_ISSUE_URL)
    assert code != 0
    captured = capsys.readouterr()
    assert captured.err.strip() != ""
    if check_owner_repo_num:
        assert "cli" in captured.err
        assert "1" in captured.err


def test_comments_fetch_failure(capsys):
    """Issue succeeds but comments fetch fails → non-zero exit, error on stderr."""
    def side_effect(*args, **kwargs):
        cmd = args[0]
        api_path = cmd[cmd.index("api") + 1]
        if "/comments" in api_path:
            return _make_gh_mock(returncode=1, stderr="HTTP 500: Internal Server Error")
        return _make_gh_mock(stdout=json.dumps(GITHUB_API_ISSUE))

    with patch("github_resolver.shutil.which", return_value="/usr/bin/gh"):
        with patch("github_resolver.subprocess.run", side_effect=side_effect):
            code = _invoke_main(GITHUB_ISSUE_URL)
    assert code != 0
    captured = capsys.readouterr()
    assert captured.err.strip() != ""


def test_network_failure(capsys):
    """subprocess.run raises OSError (network failure) → non-zero exit, error on stderr (no traceback)."""
    with patch("github_resolver.shutil.which", return_value="/usr/bin/gh"):
        with patch("github_resolver.subprocess.run", side_effect=OSError("Network unreachable")):
            code = _invoke_main(GITHUB_ISSUE_URL)
    assert code != 0
    captured = capsys.readouterr()
    assert captured.err.strip() != ""
    assert "Traceback" not in captured.err


def test_happy_path(capsys):
    """Valid URL → combined JSON with issue and comments keys."""
    with patch("github_resolver.shutil.which", return_value="/usr/bin/gh"):
        with patch("github_resolver.subprocess.run", side_effect=_success_side_effect):
            code = _invoke_main(GITHUB_ISSUE_URL)
    assert code == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result == GITHUB_API_RESPONSE
    assert "issue" in result
    assert "comments" in result
    assert result["issue"] == GITHUB_API_ISSUE
    assert result["comments"] == GITHUB_API_COMMENTS


def test_multi_url_array_rejected(capsys):
    """JSON arrays are not supported — resolver exits non-zero with error on stderr."""
    value = json.dumps([GITHUB_ISSUE_URL, GITHUB_PR_URL])
    with patch("github_resolver.shutil.which", return_value="/usr/bin/gh"):
        with patch("github_resolver.subprocess.run", side_effect=_success_side_effect):
            code = _invoke_main(value)
    assert code != 0
    captured = capsys.readouterr()
    assert captured.err.strip() != ""
    assert "array" in captured.err.lower() or "not supported" in captured.err.lower()


def test_multi_url_one_fails(capsys):
    """If any URL in a list fails, the whole resolution fails."""
    call_count = [0]

    def fail_second(*args, **kwargs):
        cmd = args[0]
        api_path = cmd[cmd.index("api") + 1]
        if "/comments" in api_path:
            return _make_gh_mock(stdout=json.dumps(GITHUB_API_COMMENTS))
        call_count[0] += 1
        if call_count[0] == 2:
            return _make_gh_mock(returncode=1, stderr="HTTP 404: Not Found")
        return _make_gh_mock(stdout=json.dumps(GITHUB_API_ISSUE))

    egg = json.dumps([GITHUB_ISSUE_URL, GITHUB_PR_URL])
    with patch("github_resolver.shutil.which", return_value="/usr/bin/gh"):
        with patch("github_resolver.subprocess.run", side_effect=fail_second):
            code = _invoke_main(egg)
    assert code != 0


def test_multi_url_empty_list(capsys):
    """Empty URL list → non-zero exit."""
    code = _invoke_main("[]")
    assert code != 0
    captured = capsys.readouterr()
    assert captured.err.strip() != ""
