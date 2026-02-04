"""Tests for mcp_index_ops module - index generation extraction."""

import pytest
from unittest.mock import patch, MagicMock
from src.mcp_index_ops import _generate_index


class TestMcpIndexOpsImports:
    """Test that mcp_index_ops module can be imported correctly."""

    def test_import_generate_index(self):
        """Test that _generate_index can be imported."""
        assert callable(_generate_index)
        assert _generate_index.__name__ == "_generate_index"


class TestMcpIndexOpsIntegration:
    """Test integration with mcp_server.py tool registration."""

    def test_mcp_server_imports_index_function(self):
        """Test that mcp_server.py can import _generate_index from mcp_index_ops."""
        # This will fail if there are circular dependency issues
        from src import mcp_server

        # Verify the function is available in mcp_server's namespace
        assert hasattr(mcp_server, '_generate_index')

    def test_mcp_tool_registered(self):
        """Test that MCP tool is properly registered."""
        from src.mcp_server import generate_index_tool

        # Verify tool is registered
        assert generate_index_tool is not None


class TestNoCircularDependencies:
    """Test that there are no circular dependency issues."""

    def test_can_import_both_modules(self):
        """Test that both mcp_server and mcp_index_ops can be imported."""
        from src import mcp_server
        from src import mcp_index_ops

        assert mcp_server is not None
        assert mcp_index_ops is not None


class TestGenerateIndexFunction:
    """Test _generate_index function behavior."""

    @patch('src.mcp_index_ops.generate_index')
    def test_generate_index_no_filters(self, mock_generate_index):
        """Test _generate_index with no filters."""
        mock_generate_index.return_value = "# Ticket Index\n- ticket1\n- ticket2"

        result = _generate_index()

        assert result['status'] == 'success'
        assert 'markdown' in result
        assert result['markdown'] == "# Ticket Index\n- ticket1\n- ticket2"
        mock_generate_index.assert_called_once_with(
            status_filter=None,
            type_filter=None,
            hive_name=None
        )

    @patch('src.mcp_index_ops.generate_index')
    def test_generate_index_with_status_filter(self, mock_generate_index):
        """Test _generate_index with status filter."""
        mock_generate_index.return_value = "# Open Tickets\n- open-ticket1"

        result = _generate_index(status='open')

        assert result['status'] == 'success'
        assert 'markdown' in result
        mock_generate_index.assert_called_once_with(
            status_filter='open',
            type_filter=None,
            hive_name=None
        )

    @patch('src.mcp_index_ops.generate_index')
    def test_generate_index_with_type_filter(self, mock_generate_index):
        """Test _generate_index with type filter."""
        mock_generate_index.return_value = "# Epic Tickets\n- epic1"

        result = _generate_index(type='epic')

        assert result['status'] == 'success'
        mock_generate_index.assert_called_once_with(
            status_filter=None,
            type_filter='epic',
            hive_name=None
        )

    @patch('src.mcp_index_ops.generate_index')
    def test_generate_index_with_combined_filters(self, mock_generate_index):
        """Test _generate_index with status and type filters."""
        mock_generate_index.return_value = "# Open Tasks\n- task1"

        result = _generate_index(status='open', type='task')

        assert result['status'] == 'success'
        mock_generate_index.assert_called_once_with(
            status_filter='open',
            type_filter='task',
            hive_name=None
        )

    @patch('src.mcp_index_ops.generate_index')
    def test_generate_index_with_hive_name(self, mock_generate_index):
        """Test _generate_index with hive_name filter."""
        mock_generate_index.return_value = "# Backend Hive Index\n- backend-ticket1"

        result = _generate_index(hive_name='backend')

        assert result['status'] == 'success'
        mock_generate_index.assert_called_once_with(
            status_filter=None,
            type_filter=None,
            hive_name='backend'
        )

    @patch('src.mcp_index_ops.generate_index')
    def test_generate_index_with_all_filters(self, mock_generate_index):
        """Test _generate_index with all filters."""
        mock_generate_index.return_value = "# Filtered Index"

        result = _generate_index(status='completed', type='subtask', hive_name='frontend')

        assert result['status'] == 'success'
        mock_generate_index.assert_called_once_with(
            status_filter='completed',
            type_filter='subtask',
            hive_name='frontend'
        )

    @patch('src.mcp_index_ops.generate_index')
    @patch('src.mcp_index_ops.logger')
    def test_generate_index_logs_success(self, mock_logger, mock_generate_index):
        """Test that successful index generation is logged."""
        mock_generate_index.return_value = "# Index"

        _generate_index(status='open', type='epic', hive_name='test')

        mock_logger.info.assert_called_once()
        log_message = mock_logger.info.call_args[0][0]
        assert 'Successfully generated ticket index' in log_message
        assert 'status=open' in log_message
        assert 'type=epic' in log_message
        assert 'hive_name=test' in log_message

    @patch('src.mcp_index_ops.generate_index')
    @patch('src.mcp_index_ops.logger')
    def test_generate_index_error_handling(self, mock_logger, mock_generate_index):
        """Test error handling when index generation fails."""
        mock_generate_index.side_effect = Exception("Index generation failed")

        with pytest.raises(ValueError) as exc_info:
            _generate_index()

        assert "Failed to generate index" in str(exc_info.value)
        assert "Index generation failed" in str(exc_info.value)
        mock_logger.error.assert_called_once()

    @patch('src.mcp_index_ops.generate_index')
    @patch('src.mcp_index_ops.logger')
    def test_generate_index_logs_error(self, mock_logger, mock_generate_index):
        """Test that errors are properly logged."""
        error_message = "File not found"
        mock_generate_index.side_effect = Exception(error_message)

        with pytest.raises(ValueError):
            _generate_index()

        mock_logger.error.assert_called_once()
        log_message = mock_logger.error.call_args[0][0]
        assert 'Failed to generate index' in log_message
        assert error_message in log_message


class TestReturnStructure:
    """Test the return structure of _generate_index."""

    @patch('src.mcp_index_ops.generate_index')
    def test_return_has_status_field(self, mock_generate_index):
        """Test that return value has status field."""
        mock_generate_index.return_value = "# Index"

        result = _generate_index()

        assert 'status' in result
        assert isinstance(result['status'], str)

    @patch('src.mcp_index_ops.generate_index')
    def test_return_has_markdown_field(self, mock_generate_index):
        """Test that return value has markdown field."""
        markdown_content = "# Ticket Index\n\n## Epics\n- Epic 1"
        mock_generate_index.return_value = markdown_content

        result = _generate_index()

        assert 'markdown' in result
        assert result['markdown'] == markdown_content

    @patch('src.mcp_index_ops.generate_index')
    def test_return_structure_is_dict(self, mock_generate_index):
        """Test that return value is a dictionary."""
        mock_generate_index.return_value = "# Index"

        result = _generate_index()

        assert isinstance(result, dict)
        assert len(result) == 2  # status and markdown
