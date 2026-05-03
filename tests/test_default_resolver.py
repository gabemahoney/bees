"""
Unit tests for the built-in default file path resolver.

PURPOSE:
Tests resolve_file_path() and DEFAULT_RESOLVER_CONVENTION from mcp_reference_ops.
Covers success paths (absolute/relative), error paths (missing file, no repo_root,
non-string types), and edge cases (symlinks, directories).
"""

import os
from pathlib import Path

import pytest

from src.mcp_reference_ops import DEFAULT_RESOLVER_CONVENTION, resolve_file_path


# ============================================================================
# Success cases
# ============================================================================


@pytest.mark.parametrize(
    "make_path",
    [
        pytest.param(
            lambda tmp, f: str(f),
            id="absolute_existing",
        ),
        pytest.param(
            lambda tmp, f: str(f.relative_to(tmp)),
            id="relative_with_repo_root",
        ),
    ],
)
def test_resolve_file_path_success(tmp_path, make_path):
    target = tmp_path / "myfile.txt"
    target.write_text("hello")

    value = make_path(tmp_path, target)
    repo_root = tmp_path if not Path(value).is_absolute() else None

    result = resolve_file_path(value, repo_root=repo_root)

    assert result["status"] == "success"
    assert Path(result["resolved_path"]).exists()
    assert result["resolved_path"] == str(target.resolve())


# ============================================================================
# Error cases
# ============================================================================


@pytest.mark.parametrize(
    "value,repo_root_factory,expected_error_fragment",
    [
        pytest.param(
            lambda tmp: str(tmp / "nonexistent.txt"),
            lambda tmp: None,
            "does not exist",
            id="absolute_nonexistent",
        ),
        pytest.param(
            lambda tmp: "relative/missing.txt",
            lambda tmp: None,
            "repo_root is required",
            id="relative_without_repo_root",
        ),
        pytest.param(
            lambda tmp: "relative/missing.txt",
            lambda tmp: tmp,
            "does not exist",
            id="relative_nonexistent_file",
        ),
    ],
)
def test_resolve_file_path_error(tmp_path, value, repo_root_factory, expected_error_fragment):
    result = resolve_file_path(value(tmp_path), repo_root=repo_root_factory(tmp_path))

    assert result["status"] == "error"
    assert expected_error_fragment in result["error"]
    assert "raw_value" in result


@pytest.mark.parametrize(
    "bad_value",
    [
        pytest.param(42, id="int"),
        pytest.param({"key": "val"}, id="dict"),
        pytest.param(["a", "b"], id="list"),
        pytest.param(None, id="none"),
    ],
)
def test_resolve_file_path_non_string_error(bad_value):
    result = resolve_file_path(bad_value)

    assert result["status"] == "error"
    assert result["raw_value"] == bad_value
    assert "string" in result["error"]


# ============================================================================
# Edge cases
# ============================================================================


def test_resolve_file_path_directory(tmp_path):
    """Directories count as existing paths."""
    subdir = tmp_path / "somedir"
    subdir.mkdir()

    result = resolve_file_path(str(subdir))

    assert result["status"] == "success"
    assert result["resolved_path"] == str(subdir.resolve())


def test_resolve_file_path_symlink(tmp_path):
    """Symlinks to existing files resolve successfully."""
    target = tmp_path / "real.txt"
    target.write_text("data")
    link = tmp_path / "link.txt"
    link.symlink_to(target)

    result = resolve_file_path(str(link))

    assert result["status"] == "success"
    assert Path(result["resolved_path"]).exists()


def test_resolve_file_path_relative_resolves_against_repo_root(tmp_path):
    """Relative path is joined against repo_root, not cwd."""
    subdir = tmp_path / "sub"
    subdir.mkdir()
    target = subdir / "file.txt"
    target.write_text("x")

    result = resolve_file_path("sub/file.txt", repo_root=tmp_path)

    assert result["status"] == "success"
    assert result["resolved_path"] == str(target.resolve())


def test_default_resolver_convention_is_nonempty_string():
    assert isinstance(DEFAULT_RESOLVER_CONVENTION, str)
    assert len(DEFAULT_RESOLVER_CONVENTION) > 0
