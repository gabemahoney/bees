"""
Unit tests for MCP reference_materials resolution operations.

PURPOSE:
Tests the _resolve_references pipeline and helper functions in mcp_reference_ops:
  - resolve_file_path(): default resolver for file-path entries
  - _invoke_custom_resolver(): custom subprocess resolver
  - _resolve_references(): orchestrates resolution for a full reference_materials list
"""

import json

import pytest

from src.mcp_reference_ops import (
    DEFAULT_RESOLVER_CONVENTION,
    _invoke_custom_resolver,
    _resolve_references,
    resolve_file_path,
)
from src.repo_context import repo_root_context
from tests.conftest import write_scoped_config
from tests.helpers import write_ticket_file
from tests.test_constants import HIVE_BACKEND


@pytest.fixture
def hive_env_with_refs(tmp_path, monkeypatch, mock_global_bees_dir):
    """Create a test environment with a hive containing bee tickets with reference_materials."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()

    hive_dir = tmp_path / HIVE_BACKEND
    hive_dir.mkdir(parents=True)

    # Create .hive identity marker
    hive_identity_dir = hive_dir / ".hive"
    hive_identity_dir.mkdir(parents=True, exist_ok=True)
    identity_data = {
        "normalized_name": HIVE_BACKEND,
        "display_name": "Backend",
        "created_at": "2026-02-05T00:00:00",
    }
    (hive_identity_dir / "identity.json").write_text(json.dumps(identity_data, indent=2))

    # Write scoped config
    scope_data = {
        "hives": {HIVE_BACKEND: {"path": str(hive_dir), "display_name": "Backend"}},
        "child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
    }
    write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

    with repo_root_context(tmp_path):
        yield tmp_path, hive_dir


# ============================================================================
# DEFAULT_RESOLVER_CONVENTION CONSTANT
# ============================================================================


class TestDefaultResolverConvention:
    """Tests that DEFAULT_RESOLVER_CONVENTION is a non-empty string."""

    def test_is_string(self):
        """DEFAULT_RESOLVER_CONVENTION is a string."""
        assert isinstance(DEFAULT_RESOLVER_CONVENTION, str)

    def test_is_non_empty(self):
        """DEFAULT_RESOLVER_CONVENTION is not empty."""
        assert DEFAULT_RESOLVER_CONVENTION.strip() != ""


# ============================================================================
# resolve_file_path TESTS
# ============================================================================


class TestResolveFilePath:
    """Tests for resolve_file_path() — the default resolver."""

    def test_existing_absolute_path_succeeds(self, tmp_path):
        """Existing absolute path returns success with resolved_path."""
        existing = tmp_path / "spec.md"
        existing.touch()

        result = resolve_file_path(str(existing))

        assert result["status"] == "success"
        assert result["resolved_path"] == str(existing.resolve())

    def test_nonexistent_absolute_path_fails(self, tmp_path):
        """Non-existent absolute path returns error."""
        missing = tmp_path / "nonexistent.md"

        result = resolve_file_path(str(missing))

        assert result["status"] == "error"
        assert "raw_value" in result
        assert "does not exist" in result["error"]

    def test_relative_path_with_repo_root(self, tmp_path):
        """Relative path resolved against repo_root returns success when file exists."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").touch()

        result = resolve_file_path("docs/guide.md", repo_root=tmp_path)

        assert result["status"] == "success"
        assert "guide.md" in result["resolved_path"]

    def test_relative_path_without_repo_root_fails(self):
        """Relative path without repo_root returns error."""
        result = resolve_file_path("relative/path.md", repo_root=None)

        assert result["status"] == "error"
        assert "repo_root is required" in result["error"]

    def test_non_string_value_fails(self, tmp_path):
        """Non-string value returns error (value must be a string file path)."""
        result = resolve_file_path({"url": "http://example.com"})

        assert result["status"] == "error"
        assert "raw_value" in result
        assert "string file path" in result["error"]

    def test_none_value_fails(self, tmp_path):
        """None value returns error."""
        result = resolve_file_path(None)

        assert result["status"] == "error"
        assert "raw_value" in result


# ============================================================================
# _invoke_custom_resolver TESTS
# ============================================================================


class TestInvokeCustomResolver:
    """Tests for custom resolver subprocess invocation (_invoke_custom_resolver)."""

    async def test_custom_resolver_success(self, tmp_path):
        """Custom resolver executes successfully and returns parsed JSON."""
        resolver_script = tmp_path / "resolver.sh"
        resolver_script.write_text(
            "#!/bin/bash\necho '[\"file1.txt\", \"file2.txt\"]'\n"
        )
        resolver_script.chmod(0o755)

        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            value="test-value",
            repo_root=tmp_path,
            timeout=5,
        )

        assert result == ["file1.txt", "file2.txt"]

    async def test_custom_resolver_with_null_output(self, tmp_path):
        """Custom resolver returning null is parsed correctly."""
        resolver_script = tmp_path / "resolver_null.sh"
        resolver_script.write_text("#!/bin/bash\necho 'null'\n")
        resolver_script.chmod(0o755)

        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            value="test-value",
            repo_root=tmp_path,
            timeout=5,
        )

        assert result is None

    async def test_custom_resolver_none_value_returns_none(self, tmp_path):
        """None value short-circuits before subprocess invocation, returns None."""
        invoked_file = tmp_path / "resolver_was_invoked.txt"

        resolver_script = tmp_path / "resolver_none.sh"
        resolver_script.write_text(
            f"#!/bin/bash\ntouch {invoked_file}\necho 'null'\n"
        )
        resolver_script.chmod(0o755)

        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            value=None,
            repo_root=tmp_path,
            timeout=5,
        )

        assert result is None
        assert not invoked_file.exists(), "Resolver subprocess should not have been invoked for None value"

    async def test_custom_resolver_non_zero_exit(self, tmp_path):
        """Custom resolver with non-zero exit code raises RuntimeError with stderr."""
        resolver_script = tmp_path / "resolver_fail.sh"
        resolver_script.write_text(
            "#!/bin/bash\necho 'Resolver failed' >&2\nexit 1\n"
        )
        resolver_script.chmod(0o755)

        with pytest.raises(RuntimeError, match=r"Resolver exited with code 1.*Resolver failed"):
            await _invoke_custom_resolver(
                command=str(resolver_script),
                value="test-value",
                repo_root=tmp_path,
                timeout=5,
            )

    async def test_custom_resolver_invalid_json(self, tmp_path):
        """Custom resolver with invalid JSON output raises RuntimeError."""
        resolver_script = tmp_path / "resolver_bad_json.sh"
        resolver_script.write_text("#!/bin/bash\necho 'not valid json'\n")
        resolver_script.chmod(0o755)

        with pytest.raises(RuntimeError, match=r"Resolver returned invalid JSON"):
            await _invoke_custom_resolver(
                command=str(resolver_script),
                value="test-value",
                repo_root=tmp_path,
                timeout=5,
            )

    async def test_custom_resolver_timeout(self, tmp_path):
        """Custom resolver timeout kills process and raises RuntimeError."""
        resolver_script = tmp_path / "resolver_hang.sh"
        resolver_script.write_text("#!/bin/bash\nsleep 10\necho '[\"done\"]'\n")
        resolver_script.chmod(0o755)

        with pytest.raises(RuntimeError, match=r"Resolver timed out after 0.5 seconds"):
            await _invoke_custom_resolver(
                command=str(resolver_script),
                value="test-value",
                repo_root=tmp_path,
                timeout=0.5,
            )

    async def test_custom_resolver_receives_value_arg(self, tmp_path):
        """Custom resolver is invoked with --repo-root and --value args."""
        output_file = tmp_path / "resolver_output.txt"

        resolver_script = tmp_path / "resolver_echo_args.sh"
        resolver_script.write_text(
            f"#!/bin/bash\necho \"$@\" > {output_file}\necho '[\"verified\"]'\n"
        )
        resolver_script.chmod(0o755)

        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            value="my-spec-value",
            repo_root=tmp_path,
            timeout=5,
        )

        assert result == ["verified"]
        assert output_file.exists()
        args_content = output_file.read_text().strip()
        assert "--repo-root" in args_content
        assert "--value" in args_content

    async def test_custom_resolver_string_value_passed_raw(self, tmp_path):
        """String values are passed raw (not JSON-encoded) to the resolver."""
        captured_file = tmp_path / "captured_value.txt"

        resolver_script = tmp_path / "resolver_capture.sh"
        resolver_script.write_text(
            f"""#!/bin/bash
while [[ $# -gt 0 ]]; do
    case "$1" in
        --value) echo -n "$2" > {captured_file}; shift 2;;
        *) shift;;
    esac
done
echo '["resolved"]'
"""
        )
        resolver_script.chmod(0o755)

        raw_value = "abc-123-def-456"
        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            value=raw_value,
            repo_root=tmp_path,
            timeout=5,
        )

        assert result == ["resolved"]
        assert captured_file.exists()
        captured = captured_file.read_text()
        assert captured == raw_value

    async def test_custom_resolver_non_string_value_json_encoded(self, tmp_path):
        """Non-string values are JSON-encoded before being passed to the resolver."""
        captured_file = tmp_path / "captured_value.txt"

        resolver_script = tmp_path / "resolver_capture_dict.sh"
        resolver_script.write_text(
            f"""#!/bin/bash
while [[ $# -gt 0 ]]; do
    case "$1" in
        --value) echo -n "$2" > {captured_file}; shift 2;;
        *) shift;;
    esac
done
echo '["verified"]'
"""
        )
        resolver_script.chmod(0o755)

        dict_value = {"url": "https://example.com", "version": 1}
        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            value=dict_value,
            repo_root=tmp_path,
            timeout=5,
        )

        assert result == ["verified"]
        assert captured_file.exists()
        captured = captured_file.read_text()
        # Dict values are JSON-encoded
        assert captured == json.dumps(dict_value)


# ============================================================================
# _resolve_references TESTS
# ============================================================================


class TestResolveReferencesNull:
    """Tests for _resolve_references with None input."""

    async def test_none_returns_none(self, tmp_path):
        """None reference_materials returns None directly."""
        result = await _resolve_references(None, repo_root=tmp_path)
        assert result is None


class TestResolveReferencesDefaultResolver:
    """Tests for _resolve_references with default resolver."""

    async def test_single_entry_existing_file(self, tmp_path):
        """Single entry with existing file resolves successfully."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "spec.md").touch()

        reference_materials = [{"value": "docs/spec.md"}]
        result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        assert len(result) == 1
        assert result[0]["value"] == "docs/spec.md"
        assert result[0]["resolved"]["status"] == "success"
        assert "spec.md" in result[0]["resolved"]["resolved_path"]

    async def test_single_entry_missing_file(self, tmp_path):
        """Single entry with missing file returns error in resolved."""
        reference_materials = [{"value": "docs/missing.md"}]
        result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        assert len(result) == 1
        assert result[0]["resolved"]["status"] == "error"

    async def test_multiple_entries_resolved_independently(self, tmp_path):
        """Multiple entries are each resolved independently."""
        (tmp_path / "a.md").touch()

        reference_materials = [
            {"value": "a.md"},
            {"value": "missing.md"},
        ]
        result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        assert len(result) == 2
        assert result[0]["resolved"]["status"] == "success"
        assert result[1]["resolved"]["status"] == "error"

    async def test_entry_preserves_original_fields(self, tmp_path):
        """Each resolved entry preserves all original entry fields plus 'resolved'."""
        (tmp_path / "spec.md").touch()

        entry = {"value": "spec.md", "label": "API Spec"}
        result = await _resolve_references([entry], repo_root=tmp_path)

        assert result is not None
        assert result[0]["value"] == "spec.md"
        assert result[0]["label"] == "API Spec"
        assert "resolved" in result[0]


class TestResolveReferencesCustomResolver:
    """Tests for _resolve_references with registered custom resolver."""

    async def test_registered_resolver_invoked(self, tmp_path, mock_global_bees_dir, monkeypatch):
        """Entry with a registered resolver name invokes the custom resolver."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir(exist_ok=True)

        # Create resolver script
        resolver_script = tmp_path / "custom_resolver.sh"
        resolver_script.write_text(
            "#!/bin/bash\necho '{\"resolved\": true}'\n"
        )
        resolver_script.chmod(0o755)

        # Register the resolver in the global config
        from src.config import ResolverEntry, save_resolver_registry
        registry = {"my_resolver": ResolverEntry(path=str(resolver_script), timeout=5)}
        save_resolver_registry(registry)

        reference_materials = [{"value": "some-spec", "resolver": "my_resolver"}]

        with repo_root_context(tmp_path):
            result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        assert len(result) == 1
        assert result[0]["resolved"] == {"resolved": True}

    async def test_unregistered_resolver_returns_error(self, tmp_path):
        """Entry with unregistered resolver name returns error in resolved."""
        reference_materials = [{"value": "spec", "resolver": "nonexistent_resolver"}]
        result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        assert len(result) == 1
        assert result[0]["resolved"]["status"] == "error"
        assert "unregistered resolver" in result[0]["resolved"]["error"]

    async def test_mixed_default_and_custom_resolvers(self, tmp_path, mock_global_bees_dir, monkeypatch):
        """Mix of default and custom resolver entries are each resolved correctly."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir(exist_ok=True)
        (tmp_path / "spec.md").touch()

        resolver_script = tmp_path / "custom.sh"
        resolver_script.write_text("#!/bin/bash\necho '\"custom-result\"'\n")
        resolver_script.chmod(0o755)

        from src.config import ResolverEntry, save_resolver_registry
        registry = {"custom": ResolverEntry(path=str(resolver_script), timeout=5)}
        save_resolver_registry(registry)

        reference_materials = [
            {"value": "spec.md"},                      # default resolver
            {"value": "input", "resolver": "custom"},  # custom resolver
        ]

        with repo_root_context(tmp_path):
            result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        assert len(result) == 2
        assert result[0]["resolved"]["status"] == "success"
        assert result[1]["resolved"] == "custom-result"
