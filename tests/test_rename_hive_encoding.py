"""
Unit tests for rename_hive file encoding operations.

Tests that rename_hive correctly uses UTF-8 encoding for all file operations
to ensure cross-platform compatibility, especially on Windows and non-UTF-8 systems.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock, call
from src.mcp_server import _rename_hive


class TestRenameHiveEncoding:
    """Tests for UTF-8 encoding in rename_hive file operations."""

    @patch('src.mcp_server.save_bees_config')
    @patch('src.mcp_server.load_bees_config')
    @patch('src.mcp_server.normalize_hive_name')
    @patch('builtins.open', new_callable=mock_open)
    @patch('pathlib.Path.glob')
    async def test_read_ticket_uses_utf8_encoding(
        self, mock_glob, mock_file, mock_normalize, mock_load_config, mock_save_config
    ):
        """Test that reading ticket files uses UTF-8 encoding."""
        # Setup mock hive config
        mock_config = MagicMock()
        mock_hive = MagicMock()
        mock_hive.path = "/fake/hive"
        mock_hive.display_name = "old_hive"
        mock_config.hives = {"old_hive": mock_hive}
        mock_load_config.return_value = mock_config
        
        # Mock normalize to return expected values
        mock_normalize.side_effect = lambda x: x.lower()
        
        # Mock a ticket file
        mock_ticket = MagicMock()
        mock_ticket.stem = "old_hive.bees-abc123"
        mock_ticket.name = "old_hive.bees-abc123.md"
        mock_glob.return_value = [mock_ticket]
        
        # Mock file content with frontmatter
        file_content = "---\nid: old_hive.bees-abc123\ntitle: Test\n---\nBody content"
        mock_file.return_value.read.return_value = file_content
        
        # Execute rename
        await _rename_hive(old_name="old_hive", new_name="new_hive")
        
        # Verify open() was called with encoding='utf-8' for read operations
        read_calls = [c for c in mock_file.call_args_list if 'r' in str(c)]
        for call_args in read_calls:
            args, kwargs = call_args
            assert kwargs.get('encoding') == 'utf-8', \
                f"Expected encoding='utf-8' for read operation, got {kwargs}"

    @patch('src.mcp_server.save_bees_config')
    @patch('src.mcp_server.load_bees_config')
    @patch('src.mcp_server.normalize_hive_name')
    @patch('builtins.open', new_callable=mock_open)
    @patch('pathlib.Path.glob')
    async def test_write_ticket_uses_utf8_encoding(
        self, mock_glob, mock_file, mock_normalize, mock_load_config, mock_save_config
    ):
        """Test that writing ticket files uses UTF-8 encoding."""
        # Setup mock hive config
        mock_config = MagicMock()
        mock_hive = MagicMock()
        mock_hive.path = "/fake/hive"
        mock_hive.display_name = "old_hive"
        mock_config.hives = {"old_hive": mock_hive}
        mock_load_config.return_value = mock_config
        
        # Mock normalize
        mock_normalize.side_effect = lambda x: x.lower()
        
        # Mock a ticket file
        mock_ticket = MagicMock()
        mock_ticket.stem = "old_hive.bees-abc123"
        mock_ticket.name = "old_hive.bees-abc123.md"
        mock_glob.return_value = [mock_ticket]
        
        # Mock file content with frontmatter
        file_content = "---\nid: old_hive.bees-abc123\ntitle: Test\n---\nBody content"
        mock_file.return_value.read.return_value = file_content
        
        # Execute rename
        await _rename_hive(old_name="old_hive", new_name="new_hive")
        
        # Verify open() was called with encoding='utf-8' for write operations
        write_calls = [c for c in mock_file.call_args_list if 'w' in str(c)]
        for call_args in write_calls:
            args, kwargs = call_args
            assert kwargs.get('encoding') == 'utf-8', \
                f"Expected encoding='utf-8' for write operation, got {kwargs}"

    @patch('src.mcp_server.save_bees_config')
    @patch('src.mcp_server.load_bees_config')
    @patch('src.mcp_server.normalize_hive_name')
    @patch('builtins.open', new_callable=mock_open)
    @patch('pathlib.Path.glob')
    @patch('pathlib.Path.rename')
    async def test_unicode_content_handling(
        self, mock_rename, mock_glob, mock_file, mock_normalize, 
        mock_load_config, mock_save_config
    ):
        """Test that Unicode characters in ticket content are handled correctly."""
        # Setup mock hive config
        mock_config = MagicMock()
        mock_hive = MagicMock()
        mock_hive.path = "/fake/hive"
        mock_hive.display_name = "test_hive"
        mock_config.hives = {"test_hive": mock_hive}
        mock_load_config.return_value = mock_config
        
        # Mock normalize
        mock_normalize.side_effect = lambda x: x.lower()
        
        # Mock ticket with Unicode content
        mock_ticket = MagicMock()
        mock_ticket.stem = "test_hive.bees-abc123"
        mock_ticket.name = "test_hive.bees-abc123.md"
        mock_glob.return_value = [mock_ticket]
        
        # File content with special characters: emoji, accents, CJK
        unicode_content = (
            "---\n"
            "id: test_hive.bees-abc123\n"
            "title: Test with émojis 🐝 and 中文\n"
            "---\n"
            "Body with Üñíçödé characters and symbols: ∑∂√"
        )
        mock_file.return_value.read.return_value = unicode_content
        
        # Execute rename
        result = await _rename_hive(old_name="test_hive", new_name="unicode_hive")
        
        # Should not error with Unicode content when UTF-8 encoding is used
        assert result is not None

    @patch('src.mcp_server.save_bees_config')
    @patch('src.mcp_server.load_bees_config')
    @patch('src.mcp_server.normalize_hive_name')
    @patch('builtins.open', new_callable=mock_open)
    @patch('pathlib.Path.glob')
    async def test_all_open_calls_have_encoding(
        self, mock_glob, mock_file, mock_normalize, mock_load_config, mock_save_config
    ):
        """Test that ALL open() calls in rename_hive specify encoding parameter."""
        # Setup mock hive config with two hives (for cross-reference update)
        mock_config = MagicMock()
        
        mock_hive1 = MagicMock()
        mock_hive1.path = "/fake/hive1"
        mock_hive1.display_name = "hive1"
        
        mock_hive2 = MagicMock()
        mock_hive2.path = "/fake/hive2"
        mock_hive2.display_name = "hive2"
        
        mock_config.hives = {"hive1": mock_hive1, "hive2": mock_hive2}
        mock_load_config.return_value = mock_config
        
        # Mock normalize
        mock_normalize.side_effect = lambda x: x.lower()
        
        # Mock tickets in both hives
        mock_ticket1 = MagicMock()
        mock_ticket1.stem = "hive1.bees-abc123"
        mock_ticket1.name = "hive1.bees-abc123.md"
        
        mock_ticket2 = MagicMock()
        mock_ticket2.stem = "hive2.bees-xyz789"
        mock_ticket2.name = "hive2.bees-xyz789.md"
        
        # First call returns hive1 tickets, subsequent calls return hive2 tickets
        mock_glob.side_effect = [
            [mock_ticket1],  # Initial rename operation
            [mock_ticket1],  # Cross-reference scan for hive1
            [mock_ticket2],  # Cross-reference scan for hive2
        ]
        
        # Mock file content with cross-references
        content1 = "---\nid: hive1.bees-abc123\ntitle: Test\ndependencies:\n  - hive1.bees-abc123\n---\nBody"
        content2 = "---\nid: hive2.bees-xyz789\ntitle: Test2\nparent: hive1.bees-abc123\n---\nBody2"
        mock_file.return_value.read.side_effect = [content1, content1, content2]
        
        # Execute rename
        await _rename_hive(old_name="hive1", new_name="renamed_hive")
        
        # Verify ALL open() calls have encoding parameter
        for call_args in mock_file.call_args_list:
            args, kwargs = call_args
            if len(args) >= 2:  # Has mode argument
                assert 'encoding' in kwargs, \
                    f"open() called without encoding parameter: {call_args}"
                assert kwargs['encoding'] == 'utf-8', \
                    f"Expected UTF-8 encoding, got {kwargs['encoding']}"


class TestRenameHiveIdentityJsonEncoding:
    """Tests for UTF-8 encoding in identity.json operations."""

    @patch('src.mcp_server.save_bees_config')
    @patch('src.mcp_server.load_bees_config')
    @patch('src.mcp_server.normalize_hive_name')
    @patch('builtins.open', new_callable=mock_open)
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.glob')
    async def test_identity_json_read_uses_utf8(
        self, mock_glob, mock_exists, mock_file, mock_normalize, 
        mock_load_config, mock_save_config
    ):
        """Test that reading identity.json uses UTF-8 encoding."""
        # Setup mock hive config
        mock_config = MagicMock()
        mock_hive = MagicMock()
        mock_hive.path = Path("/fake/hive")
        mock_hive.display_name = "old_hive"
        mock_config.hives = {"old_hive": mock_hive}
        mock_load_config.return_value = mock_config
        
        # Mock normalize
        mock_normalize.side_effect = lambda x: x.lower()
        
        # No ticket files to simplify test
        mock_glob.return_value = []
        
        # Mock identity.json exists
        mock_exists.return_value = True
        
        # Mock identity.json content
        identity_content = '{"normalized_name": "old_hive", "display_name": "Old Hive"}'
        mock_file.return_value.read.return_value = identity_content
        
        # Execute rename
        await _rename_hive(old_name="old_hive", new_name="new_hive")
        
        # Find the identity.json read call (line 2375)
        identity_read_calls = [
            c for c in mock_file.call_args_list 
            if 'identity.json' in str(c) and "'r'" in str(c)
        ]
        
        assert len(identity_read_calls) > 0, "Expected identity.json read operation"
        for call_args in identity_read_calls:
            args, kwargs = call_args
            assert kwargs.get('encoding') == 'utf-8', \
                f"Expected encoding='utf-8' for identity.json read, got {kwargs}"

    @patch('src.mcp_server.save_bees_config')
    @patch('src.mcp_server.load_bees_config')
    @patch('src.mcp_server.normalize_hive_name')
    @patch('builtins.open', new_callable=mock_open)
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.glob')
    async def test_identity_json_write_uses_utf8_update(
        self, mock_glob, mock_exists, mock_file, mock_normalize,
        mock_load_config, mock_save_config
    ):
        """Test that writing identity.json uses UTF-8 encoding (update path - line 2383)."""
        # Setup mock hive config
        mock_config = MagicMock()
        mock_hive = MagicMock()
        mock_hive.path = Path("/fake/hive")
        mock_hive.display_name = "old_hive"
        mock_config.hives = {"old_hive": mock_hive}
        mock_load_config.return_value = mock_config
        
        # Mock normalize
        mock_normalize.side_effect = lambda x: x.lower()
        
        # No ticket files
        mock_glob.return_value = []
        
        # Mock identity.json exists (update path)
        mock_exists.return_value = True
        
        # Mock identity.json content
        identity_content = '{"normalized_name": "old_hive", "display_name": "Old Hive"}'
        mock_file.return_value.read.return_value = identity_content
        
        # Execute rename
        await _rename_hive(old_name="old_hive", new_name="new_hive")
        
        # Find the identity.json write call
        identity_write_calls = [
            c for c in mock_file.call_args_list 
            if 'identity.json' in str(c) and "'w'" in str(c)
        ]
        
        assert len(identity_write_calls) > 0, "Expected identity.json write operation"
        for call_args in identity_write_calls:
            args, kwargs = call_args
            assert kwargs.get('encoding') == 'utf-8', \
                f"Expected encoding='utf-8' for identity.json write, got {kwargs}"

    @patch('src.mcp_server.save_bees_config')
    @patch('src.mcp_server.load_bees_config')
    @patch('src.mcp_server.normalize_hive_name')
    @patch('builtins.open', new_callable=mock_open)
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.mkdir')
    @patch('pathlib.Path.glob')
    async def test_identity_json_write_uses_utf8_create(
        self, mock_glob, mock_mkdir, mock_exists, mock_file, mock_normalize,
        mock_load_config, mock_save_config
    ):
        """Test that creating identity.json uses UTF-8 encoding (create path - line 2396)."""
        # Setup mock hive config
        mock_config = MagicMock()
        mock_hive = MagicMock()
        mock_hive.path = Path("/fake/hive")
        mock_hive.display_name = "old_hive"
        mock_config.hives = {"old_hive": mock_hive}
        mock_load_config.return_value = mock_config
        
        # Mock normalize
        mock_normalize.side_effect = lambda x: x.lower()
        
        # No ticket files
        mock_glob.return_value = []
        
        # Mock identity.json does NOT exist (create path)
        mock_exists.return_value = False
        
        # Execute rename
        await _rename_hive(old_name="old_hive", new_name="new_hive")
        
        # Find the identity.json write call
        identity_write_calls = [
            c for c in mock_file.call_args_list 
            if 'identity.json' in str(c) and "'w'" in str(c)
        ]
        
        assert len(identity_write_calls) > 0, "Expected identity.json write operation"
        for call_args in identity_write_calls:
            args, kwargs = call_args
            assert kwargs.get('encoding') == 'utf-8', \
                f"Expected encoding='utf-8' for identity.json create, got {kwargs}"

    @patch('src.mcp_server.save_bees_config')
    @patch('src.mcp_server.load_bees_config')
    @patch('src.mcp_server.normalize_hive_name')
    @patch('builtins.open', new_callable=mock_open)
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.glob')
    async def test_identity_json_with_non_ascii_display_name(
        self, mock_glob, mock_exists, mock_file, mock_normalize,
        mock_load_config, mock_save_config
    ):
        """Test identity.json handles non-ASCII display names (emoji, accents)."""
        # Setup mock hive config
        mock_config = MagicMock()
        mock_hive = MagicMock()
        mock_hive.path = Path("/fake/hive")
        mock_hive.display_name = "test_hive"
        mock_config.hives = {"test_hive": mock_hive}
        mock_load_config.return_value = mock_config
        
        # Mock normalize (removes emoji/accents for normalized name)
        mock_normalize.side_effect = lambda x: x.lower().replace('🐝', '').replace('é', 'e').strip()
        
        # No ticket files
        mock_glob.return_value = []
        
        # Mock identity.json exists
        mock_exists.return_value = True
        
        # Identity with plain ASCII
        identity_content = '{"normalized_name": "test_hive", "display_name": "Test Hive"}'
        mock_file.return_value.read.return_value = identity_content
        
        # Rename with non-ASCII display name
        result = await _rename_hive(old_name="test_hive", new_name="🐝 Café Hive")
        
        # Should not error with non-ASCII characters when UTF-8 is used
        assert result is not None
        assert result.get('status') != 'error', f"Got error: {result.get('message')}"


class TestRenameHiveCrossPlatform:
    """Tests for cross-platform compatibility of rename_hive."""

    @patch('src.mcp_server.save_bees_config')
    @patch('src.mcp_server.load_bees_config')
    @patch('src.mcp_server.normalize_hive_name')
    @patch('builtins.open', new_callable=mock_open)
    @patch('pathlib.Path.glob')
    async def test_windows_line_endings(
        self, mock_glob, mock_file, mock_normalize, mock_load_config, mock_save_config
    ):
        """Test handling of Windows line endings (CRLF) in ticket files."""
        # Setup mock hive config
        mock_config = MagicMock()
        mock_hive = MagicMock()
        mock_hive.path = "/fake/hive"
        mock_hive.display_name = "win_hive"
        mock_config.hives = {"win_hive": mock_hive}
        mock_load_config.return_value = mock_config
        
        # Mock normalize
        mock_normalize.side_effect = lambda x: x.lower()
        
        # Mock ticket
        mock_ticket = MagicMock()
        mock_ticket.stem = "win_hive.bees-abc123"
        mock_ticket.name = "win_hive.bees-abc123.md"
        mock_glob.return_value = [mock_ticket]
        
        # File content with Windows CRLF line endings
        windows_content = "---\r\nid: win_hive.bees-abc123\r\ntitle: Windows Test\r\n---\r\nBody with CRLF"
        mock_file.return_value.read.return_value = windows_content
        
        # Execute rename - should handle CRLF without errors
        result = await _rename_hive(old_name="win_hive", new_name="cross_platform")
        
        # Should complete without encoding errors
        assert result is not None
