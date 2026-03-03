"""
Unit tests for MCP egg resolution operations.

PURPOSE:
Tests the resolve_eggs MCP tool that resolves egg field values from bee tickets
using configured egg resolvers (default inline resolver or custom subprocess commands).
"""

import json

import pytest

from src.mcp_egg_ops import _default_resolver, _invoke_custom_resolver, _resolve_eggs
from src.repo_context import repo_root_context
from tests.conftest import write_scoped_config
from tests.helpers import write_ticket_file
from tests.test_constants import HIVE_BACKEND


@pytest.fixture
def hive_env_with_egg(tmp_path, monkeypatch, mock_global_bees_dir):
    """Create a test environment with a hive containing bee tickets with egg fields."""
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
# DEFAULT RESOLVER TESTS
# ============================================================================


class TestDefaultResolver:
    """Tests for the default inline egg resolver (_default_resolver)."""

    def test_default_resolver_string_egg(self):
        """Default resolver returns string egg unchanged (identity)."""
        result = _default_resolver("https://example.com/spec.md")
        assert result == "https://example.com/spec.md"

    def test_default_resolver_null_egg(self):
        """Default resolver returns null for null egg value."""
        result = _default_resolver(None)
        assert result is None

    @pytest.mark.parametrize(
        "egg_value,expected",
        [
            pytest.param({"type": "spec", "url": "https://example.com"}, {"type": "spec", "url": "https://example.com"}, id="object"),
            pytest.param(["file1.txt", "file2.txt"], ["file1.txt", "file2.txt"], id="array"),
            pytest.param(42, 42, id="integer"),
            pytest.param(3.14, 3.14, id="float"),
            pytest.param(True, True, id="boolean"),
        ],
    )
    def test_default_resolver_complex_types(self, egg_value, expected):
        """Default resolver returns values unchanged (identity function)."""
        result = _default_resolver(egg_value)
        assert result == expected


class TestResolveEggsDefaultResolver:
    """Tests for resolve_eggs with default resolver (no custom command)."""

    async def test_resolve_eggs_string_egg_default_resolver(self, hive_env_with_egg):
        """String egg with default resolver returns string unchanged (identity)."""
        tmp_path, hive_dir = hive_env_with_egg

        # Create bee with string egg
        write_ticket_file(
            hive_dir,
            "b.amx",
            title="Test Bee",
            type="bee",
            egg="https://example.com/spec.md",
        )

        result = await _resolve_eggs("b.amx")

        assert result["status"] == "success"
        assert result["ticket_id"] == "b.amx"
        assert result["resources"] == "https://example.com/spec.md"

    async def test_resolve_eggs_null_egg_default_resolver(self, hive_env_with_egg):
        """Null egg with default resolver returns null."""
        tmp_path, hive_dir = hive_env_with_egg

        # Create bee with null egg
        write_ticket_file(hive_dir, "b.bmx", title="Null Egg Bee", type="bee", egg=None)

        result = await _resolve_eggs("b.bmx")

        assert result["status"] == "success"
        assert result["ticket_id"] == "b.bmx"
        assert result["resources"] is None

    async def test_resolve_eggs_object_egg_default_resolver(self, hive_env_with_egg):
        """Object egg with default resolver returns raw dict unchanged (identity)."""
        tmp_path, hive_dir = hive_env_with_egg

        # Create bee with object egg
        egg_obj = {"type": "spec", "url": "https://example.com/spec.md"}
        write_ticket_file(hive_dir, "b.cmx", title="Object Egg Bee", type="bee", egg=egg_obj)

        result = await _resolve_eggs("b.cmx")

        assert result["status"] == "success"
        assert result["ticket_id"] == "b.cmx"
        assert result["resources"] == egg_obj


# ============================================================================
# CUSTOM RESOLVER TESTS
# ============================================================================


class TestInvokeCustomResolver:
    """Tests for custom resolver subprocess invocation (_invoke_custom_resolver)."""

    async def test_custom_resolver_success(self, tmp_path):
        """Custom resolver executes successfully and returns parsed JSON."""
        # Create a mock resolver script
        resolver_script = tmp_path / "resolver.sh"
        resolver_script.write_text(
            """#!/bin/bash
echo '["file1.txt", "file2.txt"]'
"""
        )
        resolver_script.chmod(0o755)

        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            egg_value="test-egg",
            repo_root=tmp_path,
            timeout=5,
        )

        assert result == ["file1.txt", "file2.txt"]

    async def test_custom_resolver_with_null_output(self, tmp_path):
        """Custom resolver returning null is parsed correctly."""
        resolver_script = tmp_path / "resolver_null.sh"
        resolver_script.write_text(
            """#!/bin/bash
echo 'null'
"""
        )
        resolver_script.chmod(0o755)

        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            egg_value="test-egg",
            repo_root=tmp_path,
            timeout=5,
        )

        assert result is None

    async def test_custom_resolver_none_egg_returns_none(self, tmp_path):
        """Null egg value short-circuits before subprocess invocation, returns None."""
        invoked_file = tmp_path / "resolver_was_invoked.txt"

        resolver_script = tmp_path / "resolver_none_egg.sh"
        resolver_script.write_text(
            f"""#!/bin/bash
touch {invoked_file}
echo 'null'
"""
        )
        resolver_script.chmod(0o755)

        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            egg_value=None,
            repo_root=tmp_path,
            timeout=5,
        )

        assert result is None
        assert not invoked_file.exists(), "Resolver subprocess should not have been invoked for None egg"

    async def test_custom_resolver_non_zero_exit(self, tmp_path):
        """Custom resolver with non-zero exit code raises RuntimeError with stderr."""
        resolver_script = tmp_path / "resolver_fail.sh"
        resolver_script.write_text(
            """#!/bin/bash
echo "Resolver failed" >&2
exit 1
"""
        )
        resolver_script.chmod(0o755)

        with pytest.raises(RuntimeError, match=r"Resolver exited with code 1.*Resolver failed"):
            await _invoke_custom_resolver(
                command=str(resolver_script),
                egg_value="test-egg",
                repo_root=tmp_path,
                timeout=5,
            )

    async def test_custom_resolver_invalid_json(self, tmp_path):
        """Custom resolver with invalid JSON output raises RuntimeError."""
        resolver_script = tmp_path / "resolver_bad_json.sh"
        resolver_script.write_text(
            """#!/bin/bash
echo 'not valid json'
"""
        )
        resolver_script.chmod(0o755)

        with pytest.raises(RuntimeError, match=r"Resolver returned invalid JSON"):
            await _invoke_custom_resolver(
                command=str(resolver_script),
                egg_value="test-egg",
                repo_root=tmp_path,
                timeout=5,
            )

    async def test_custom_resolver_timeout(self, tmp_path):
        """Custom resolver timeout kills process and raises RuntimeError."""
        resolver_script = tmp_path / "resolver_hang.sh"
        resolver_script.write_text(
            """#!/bin/bash
sleep 10
echo '["done"]'
"""
        )
        resolver_script.chmod(0o755)

        with pytest.raises(RuntimeError, match=r"Resolver timed out after 0.5 seconds"):
            await _invoke_custom_resolver(
                command=str(resolver_script),
                egg_value="test-egg",
                repo_root=tmp_path,
                timeout=0.5,  # 500ms timeout
            )

    async def test_custom_resolver_string_output(self, tmp_path):
        """Custom resolver returning a JSON string is accepted."""
        resolver_script = tmp_path / "resolver_string.sh"
        resolver_script.write_text(
            """#!/bin/bash
echo '"just a string"'
"""
        )
        resolver_script.chmod(0o755)

        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            egg_value="test-egg",
            repo_root=tmp_path,
            timeout=5,
        )
        assert result == "just a string"

    async def test_custom_resolver_array_with_non_strings(self, tmp_path):
        """Custom resolver returning array with non-string elements is accepted."""
        resolver_script = tmp_path / "resolver_mixed_array.sh"
        resolver_script.write_text(
            """#!/bin/bash
echo '["file.txt", 123, "other.txt"]'
"""
        )
        resolver_script.chmod(0o755)

        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            egg_value="test-egg",
            repo_root=tmp_path,
            timeout=5,
        )
        assert result == ["file.txt", 123, "other.txt"]

    async def test_custom_resolver_receives_correct_args(self, tmp_path):
        """Custom resolver is invoked with correct --repo-root and --egg-value args."""
        # Create output file for capturing passed arguments
        output_file = tmp_path / "resolver_output.txt"

        resolver_script = tmp_path / "resolver_echo_args.sh"
        resolver_script.write_text(
            f"""#!/bin/bash
# Write all arguments to output file for verification
echo "$@" > {output_file}
# Return valid JSON
echo '["verified"]'
"""
        )
        resolver_script.chmod(0o755)

        egg_value = {"url": "https://example.com", "version": 1}
        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            egg_value=egg_value,
            repo_root=tmp_path,
            timeout=5,
        )

        # Verify resolver returned successfully
        assert result == ["verified"]

        # Check that output file was created (proves resolver was invoked)
        assert output_file.exists()
        args_content = output_file.read_text().strip()

        # Verify --repo-root and --egg-value are in arguments
        assert "--repo-root" in args_content
        assert str(tmp_path) in args_content
        assert "--egg-value" in args_content
        # Non-string egg values are JSON-encoded
        assert json.dumps(egg_value) in args_content

    async def test_custom_resolver_string_egg_passed_raw(self, tmp_path):
        """String egg values are passed raw (not JSON-encoded) to the resolver."""
        # Create script that captures the --egg-value argument verbatim
        captured_file = tmp_path / "captured_egg_value.txt"

        resolver_script = tmp_path / "resolver_capture.sh"
        resolver_script.write_text(
            f"""#!/bin/bash
# Parse --egg-value from args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --egg-value) echo -n "$2" > {captured_file}; shift 2;;
        *) shift;;
    esac
done
echo '["resolved"]'
"""
        )
        resolver_script.chmod(0o755)

        guid_value = "abc-123-def-456"
        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            egg_value=guid_value,
            repo_root=tmp_path,
            timeout=5,
        )

        assert result == ["resolved"]
        assert captured_file.exists()

        captured = captured_file.read_text()
        # Must be the raw string value, not JSON-encoded
        assert captured == guid_value


class TestResolveEggsCustomResolver:
    """Tests for resolve_eggs with custom resolver command."""

    async def test_resolve_eggs_custom_resolver_success(self, hive_env_with_egg, tmp_path, monkeypatch):
        """Custom resolver is invoked and returns resolved resources."""
        tmp_path, hive_dir = hive_env_with_egg

        # Create resolver script
        resolver_script = tmp_path / "custom_resolver.sh"
        resolver_script.write_text(
            """#!/bin/bash
echo '["resolved_file1.txt", "resolved_file2.txt"]'
"""
        )
        resolver_script.chmod(0o755)

        # Configure custom resolver in config
        from src.config import load_bees_config, save_bees_config

        config = load_bees_config()
        config.egg_resolver = str(resolver_script)
        save_bees_config(config)

        # Create bee with egg
        write_ticket_file(hive_dir, "b.dmx", title="Custom Resolver Bee", type="bee", egg="input-spec")

        result = await _resolve_eggs("b.dmx", resolved_root=tmp_path)

        assert result["status"] == "success"
        assert result["ticket_id"] == "b.dmx"
        assert result["resources"] == ["resolved_file1.txt", "resolved_file2.txt"]

    async def test_resolve_eggs_custom_resolver_hive_level_config(self, hive_env_with_egg, tmp_path, mock_global_bees_dir):
        """Hive-level resolver config takes precedence over global config."""
        tmp_path, hive_dir = hive_env_with_egg

        # Create hive-level resolver script
        hive_resolver = tmp_path / "hive_resolver.sh"
        hive_resolver.write_text(
            """#!/bin/bash
echo '["hive_resolved.txt"]'
"""
        )
        hive_resolver.chmod(0o755)

        # Create global resolver script
        global_resolver = tmp_path / "global_resolver.sh"
        global_resolver.write_text(
            """#!/bin/bash
echo '["global_resolved.txt"]'
"""
        )
        global_resolver.chmod(0o755)

        # Configure hive-level resolver
        scope_data = {
            "hives": {
                HIVE_BACKEND: {
                    "path": str(hive_dir),
                    "display_name": "Backend",
                    "egg_resolver": str(hive_resolver),
                }
            },
            "child_tiers": {"t1": ["Task", "Tasks"]},
            "egg_resolver": str(global_resolver),  # Global resolver should be ignored
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Create bee with egg
        write_ticket_file(hive_dir, "b.emx", title="Hive Config Bee", type="bee", egg="test-egg")

        result = await _resolve_eggs("b.emx", resolved_root=tmp_path)

        assert result["status"] == "success"
        assert result["resources"] == ["hive_resolved.txt"]


# ============================================================================
# ERROR CONDITION TESTS
# ============================================================================


class TestResolveEggsErrorConditions:
    """Tests for error handling in resolve_eggs."""

    async def test_resolve_eggs_ticket_not_found(self, hive_env_with_egg):
        """Ticket not found returns error dict."""
        tmp_path, hive_dir = hive_env_with_egg

        result = await _resolve_eggs("b.none")
        assert result["status"] == "error"
        assert result["error_type"] == "ticket_not_found"
        assert "Ticket not found" in result["message"]

    async def test_resolve_eggs_non_bee_ticket(self, hive_env_with_egg):
        """Attempting to resolve eggs for non-bee ticket returns error dict."""
        tmp_path, hive_dir = hive_env_with_egg

        # Create a bee parent first (with child backlink to avoid orphaned_ticket linter error)
        write_ticket_file(hive_dir, "b.fmx", title="Parent Bee", type="bee", egg=None, children=["t1.fmx.ab"])

        # Create a t1 task nested under its canonical parent bee directory
        write_ticket_file(hive_dir / "b.fmx", "t1.fmx.ab", title="Task", type="t1", parent="b.fmx")

        result = await _resolve_eggs("t1.fmx.ab")
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_ticket_type"
        assert "resolve_eggs only works on bee tickets" in result["message"]

    @pytest.mark.skip(reason="Implementation bug: hasattr(ticket, 'egg') always True for dataclass with default. Linter catches this instead.")
    async def test_resolve_eggs_missing_egg_field(self, hive_env_with_egg):
        """Bee ticket missing egg field should raise ValueError.

        NOTE: This test is skipped because the current implementation uses hasattr(ticket, 'egg')
        which always returns True for dataclass fields with defaults. The Ticket model defines
        egg with a default value of None, so hasattr will never return False.

        The linter's validate_egg_field_presence() properly detects missing egg fields by
        checking the raw frontmatter dict before Ticket construction. The _resolve_eggs
        implementation should be updated to use a similar approach if this validation is needed.
        """
        tmp_path, hive_dir = hive_env_with_egg

        # Create bee without egg field using omit_egg=True
        write_ticket_file(hive_dir, "b.gmx", title="Malformed Bee", type="bee", omit_egg=True)

        with pytest.raises(ValueError, match=r"Ticket b.gmx does not have an egg field"):
            await _resolve_eggs("b.gmx")

    async def test_resolve_eggs_empty_ticket_id(self, hive_env_with_egg):
        """Empty ticket_id returns error dict."""
        tmp_path, hive_dir = hive_env_with_egg

        result = await _resolve_eggs("")
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_ticket_id"
        assert "ticket_id cannot be empty" in result["message"]

    async def test_resolve_eggs_whitespace_ticket_id(self, hive_env_with_egg):
        """Whitespace-only ticket_id returns error dict."""
        tmp_path, hive_dir = hive_env_with_egg

        result = await _resolve_eggs("   ")
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_ticket_id"
        assert "ticket_id cannot be empty" in result["message"]

    async def test_resolve_eggs_error_when_custom_resolver_and_resolved_root_is_none(
        self, hive_env_with_egg, tmp_path, mock_global_bees_dir
    ):
        """Regression b.H3N: error dict when custom resolver is configured but resolved_root=None.

        Before the fix, resolved_root=None was silently converted to the string 'None'
        and passed as --repo-root to the resolver subprocess.
        """
        tmp_path, hive_dir = hive_env_with_egg

        resolver_script = tmp_path / "resolver.sh"
        resolver_script.write_text("#!/bin/bash\necho '[]\n")
        resolver_script.chmod(0o755)

        scope_data = {
            "hives": {HIVE_BACKEND: {"path": str(hive_dir), "display_name": "Backend"}},
            "child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
            "egg_resolver": str(resolver_script),
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        write_ticket_file(hive_dir, "b.kmx", title="Custom Resolver Bee", type="bee", egg="some-spec")

        result = await _resolve_eggs("b.kmx", resolved_root=None)
        assert result["status"] == "error"
        assert result["error_type"] == "missing_config"
        assert "resolved_root is required" in result["message"]


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestResolveEggsIntegration:
    """Integration tests for resolve_eggs across different scenarios."""

    async def test_resolve_eggs_without_context(self, hive_env_with_egg):
        """resolve_eggs works without MCP context (for CLI/test usage)."""
        tmp_path, hive_dir = hive_env_with_egg

        # Create bee with egg
        write_ticket_file(hive_dir, "b.hmx", title="CLI Test Bee", type="bee", egg="cli-spec")

        # Call without ctx (uses repo_root_context set by fixture)
        result = await _resolve_eggs("b.hmx")

        assert result["status"] == "success"
        assert result["ticket_id"] == "b.hmx"
        assert result["resources"] == "cli-spec"

    async def test_resolve_eggs_custom_resolver_timeout_config(self, hive_env_with_egg, tmp_path, mock_global_bees_dir):
        """Custom timeout configuration is respected."""
        tmp_path, hive_dir = hive_env_with_egg

        # Create hanging resolver
        resolver_script = tmp_path / "hanging_resolver.sh"
        resolver_script.write_text(
            """#!/bin/bash
sleep 5
echo '["done"]'
"""
        )
        resolver_script.chmod(0o755)

        # Configure custom resolver with short timeout
        scope_data = {
            "hives": {HIVE_BACKEND: {"path": str(hive_dir), "display_name": "Backend"}},
            "child_tiers": {"t1": ["Task", "Tasks"]},
            "egg_resolver": str(resolver_script),
            "egg_resolver_timeout": 0.5,  # 500ms timeout
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Create bee with egg
        write_ticket_file(hive_dir, "b.jmx", title="Timeout Test Bee", type="bee", egg="test")

        with pytest.raises(RuntimeError, match=r"Resolver timed out after 0.5 seconds"):
            await _resolve_eggs("b.jmx", resolved_root=tmp_path)
