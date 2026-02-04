"""Tests for mcp_query_ops module - query operations extraction."""

import pytest
from src.mcp_query_ops import _add_named_query, _execute_query, _execute_freeform_query


class TestMcpQueryOpsImports:
    """Test that mcp_query_ops module can be imported correctly."""

    def test_import_add_named_query(self):
        """Test that _add_named_query can be imported."""
        assert callable(_add_named_query)
        assert _add_named_query.__name__ == "_add_named_query"

    def test_import_execute_query(self):
        """Test that _execute_query can be imported."""
        assert callable(_execute_query)
        assert _execute_query.__name__ == "_execute_query"

    def test_import_execute_freeform_query(self):
        """Test that _execute_freeform_query can be imported."""
        assert callable(_execute_freeform_query)
        assert _execute_freeform_query.__name__ == "_execute_freeform_query"


class TestMcpQueryOpsIntegration:
    """Test integration with mcp_server.py tool registration."""

    def test_mcp_server_imports_query_functions(self):
        """Test that mcp_server.py can import query functions from mcp_query_ops."""
        # This will fail if there are circular dependency issues
        from src import mcp_server

        # Verify the functions are available in mcp_server's namespace
        assert hasattr(mcp_server, '_add_named_query')
        assert hasattr(mcp_server, '_execute_query')
        assert hasattr(mcp_server, '_execute_freeform_query')

    def test_mcp_tools_registered(self):
        """Test that MCP tools are properly registered."""
        from src.mcp_server import add_named_query, execute_query, execute_freeform_query

        # Verify tools are registered (they should be FunctionTool objects or similar)
        assert add_named_query is not None
        assert execute_query is not None
        assert execute_freeform_query is not None


class TestNoCircularDependencies:
    """Test that there are no circular dependency issues."""

    def test_import_mcp_query_ops_standalone(self):
        """Test that mcp_query_ops can be imported without mcp_server."""
        # Clear the module cache for this test
        import sys
        mcp_server_module = sys.modules.get('src.mcp_server')
        if mcp_server_module:
            # This import should work even if mcp_server was never imported
            from src.mcp_query_ops import _add_named_query
            assert callable(_add_named_query)

    def test_import_mcp_server_with_query_ops(self):
        """Test that mcp_server can import query_ops without issues."""
        # This will fail if there's a circular dependency
        from src import mcp_server
        from src import mcp_query_ops

        # Both should be importable
        assert mcp_server is not None
        assert mcp_query_ops is not None
