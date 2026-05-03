"""Unit tests for src/builtin_resolvers.py.

PURPOSE:
Tests resolve_bee(), resolve_github(), BEES_RESOLVER_CONVENTION,
and GITHUB_RESOLVER_CONVENTION from the builtin_resolvers module.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.builtin_resolvers import (
    BEES_RESOLVER_CONVENTION,
    GITHUB_RESOLVER_CONVENTION,
    resolve_bee,
    resolve_github,
)
from tests.test_constants import GITHUB_API_COMMENTS, GITHUB_API_ISSUE, GITHUB_ISSUE_URL


# ===========================================================================
# Convention string constants
# ===========================================================================


@pytest.mark.parametrize(
    "constant",
    [
        pytest.param(BEES_RESOLVER_CONVENTION, id="bees_convention"),
        pytest.param(GITHUB_RESOLVER_CONVENTION, id="github_convention"),
    ],
)
def test_convention_is_nonempty_string(constant):
    assert isinstance(constant, str)
    assert constant.strip()


# ===========================================================================
# resolve_bee
# ===========================================================================


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("b.abc", id="bee_id_string"),
        pytest.param("b.xyz", id="bee_id_other"),
        pytest.param(42, id="integer"),
        pytest.param(None, id="none"),
        pytest.param({"nested": "dict"}, id="dict"),
    ],
)
def test_resolve_bee_identity(value):
    """resolve_bee always returns status=success with value unchanged."""
    result = resolve_bee(value)
    assert result == {"status": "success", "value": value}


# ===========================================================================
# resolve_github — error paths
# ===========================================================================


def test_resolve_github_gh_not_on_path():
    """gh absent from PATH → error dict, no exception raised."""
    with patch("src.builtin_resolvers.shutil.which", return_value=None):
        result = resolve_github(GITHUB_ISSUE_URL)

    assert result["status"] == "error"
    assert result["raw_value"] == GITHUB_ISSUE_URL
    assert "gh" in result["error"].lower() or "not" in result["error"].lower()


def test_resolve_github_non_string_value():
    """Non-string value → error dict without calling gh."""
    with patch("src.builtin_resolvers.shutil.which", return_value="/usr/bin/gh"):
        result = resolve_github(123)

    assert result["status"] == "error"
    assert result["raw_value"] == 123
    assert "string" in result["error"].lower()


@pytest.mark.parametrize(
    "invalid_url",
    [
        pytest.param("not-a-url", id="no_scheme"),
        pytest.param("https://github.com/no-issue-path", id="missing_issue_path"),
        pytest.param("", id="empty_string"),
    ],
)
def test_resolve_github_invalid_url(invalid_url):
    """Invalid URL → error dict with raw_value preserved."""
    with patch("src.builtin_resolvers.shutil.which", return_value="/usr/bin/gh"):
        result = resolve_github(invalid_url)

    assert result["status"] == "error"
    assert result["raw_value"] == invalid_url


def test_resolve_github_json_array_rejected():
    """JSON array value → error dict (single URLs only)."""
    array_value = json.dumps([GITHUB_ISSUE_URL])
    with patch("src.builtin_resolvers.shutil.which", return_value="/usr/bin/gh"):
        result = resolve_github(array_value)

    assert result["status"] == "error"
    assert result["raw_value"] == array_value
    assert "array" in result["error"].lower() or "not supported" in result["error"].lower()


def _make_subprocess_result(returncode=0, stdout="", stderr=""):
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


def test_resolve_github_subprocess_nonzero():
    """Non-zero gh exit → error dict."""
    mock_result = _make_subprocess_result(returncode=1, stderr="HTTP 401: Unauthorized")
    with patch("src.builtin_resolvers.shutil.which", return_value="/usr/bin/gh"):
        with patch("src.builtin_resolvers.subprocess.run", return_value=mock_result):
            result = resolve_github(GITHUB_ISSUE_URL)

    assert result["status"] == "error"
    assert result["raw_value"] == GITHUB_ISSUE_URL
    assert result["error"]


def test_resolve_github_success():
    """Valid URL + working gh CLI → returns {issue: ..., comments: ...}."""
    def side_effect(*args, **kwargs):
        cmd = args[0]
        api_path = cmd[cmd.index("api") + 1]
        if "/comments" in api_path:
            return _make_subprocess_result(stdout=json.dumps(GITHUB_API_COMMENTS))
        return _make_subprocess_result(stdout=json.dumps(GITHUB_API_ISSUE))

    with patch("src.builtin_resolvers.shutil.which", return_value="/usr/bin/gh"):
        with patch("src.builtin_resolvers.subprocess.run", side_effect=side_effect):
            result = resolve_github(GITHUB_ISSUE_URL)

    assert result == {"issue": GITHUB_API_ISSUE, "comments": GITHUB_API_COMMENTS}
