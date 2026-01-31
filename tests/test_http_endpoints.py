"""
Unit tests for HTTP endpoint handlers.

Tests the /health endpoint including routing and error handling.
The /mcp endpoint is provided by FastMCP and tested through MCP integration tests.
"""

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from unittest.mock import patch, MagicMock
from src.main import health_endpoint, setup_http_routes
from src.mcp_server import mcp


@pytest.fixture
def test_app():
    """Create a test Starlette app with HTTP routes configured."""
    # Create a simple Starlette app for testing our custom endpoints
    app = Starlette()
    setup_http_routes(app)
    return app


@pytest.fixture
def client(test_app):
    """Create a test client for making HTTP requests."""
    return TestClient(test_app)


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_endpoint_get(self, client):
        """Test GET request to /health returns correct JSON."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "server_running" in data
        assert "name" in data
        assert data["name"] == "Bees Ticket Management Server"

    def test_health_endpoint_post(self, client):
        """Test POST request to /health returns correct JSON."""
        response = client.post("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "server_running" in data

    @patch('src.main._health_check')
    def test_health_endpoint_error_handling(self, mock_health_check, client):
        """Test health endpoint handles errors gracefully."""
        mock_health_check.side_effect = Exception("Health check failed")
        response = client.get("/health")
        assert response.status_code == 500
        data = response.json()
        assert data["status"] == "error"
        assert "message" in data


class TestMCPEndpointIntegration:
    """Tests for /mcp endpoint integration (provided by FastMCP)."""

    def test_mcp_endpoint_provided_by_fastmcp(self):
        """
        Test that /mcp endpoint is provided by FastMCP.

        Note: The /mcp endpoint is handled by FastMCP's http_app and provides
        full MCP JSON-RPC protocol support. Integration testing of the /mcp
        endpoint is done through FastMCP's test suite and end-to-end testing.
        """
        # This is a documentation test to confirm our architecture
        from src.mcp_server import mcp
        app = mcp.http_app()
        assert app is not None
        # FastMCP's app includes MCP protocol handling at /mcp


class TestHTTPRouting:
    """Tests for HTTP request routing."""

    def test_health_route_exists(self, client):
        """Test /health route is properly configured."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_unknown_route_returns_404(self, client):
        """Test requests to unknown routes return 404."""
        response = client.get("/unknown")
        assert response.status_code == 404

    def test_content_type_headers(self, client):
        """Test responses have correct Content-Type headers."""
        response = client.get("/health")
        assert "application/json" in response.headers.get("content-type", "")

    def test_health_endpoint_supports_get_and_post(self, client):
        """Test /health endpoint supports both GET and POST methods."""
        get_response = client.get("/health")
        assert get_response.status_code == 200

        post_response = client.post("/health")
        assert post_response.status_code == 200


class TestErrorHandling:
    """Tests for HTTP error handling."""

    @patch('src.main._health_check')
    def test_health_endpoint_error_handling(self, mock_health_check, client):
        """Test health endpoint handles internal errors gracefully."""
        mock_health_check.side_effect = Exception("Internal error")
        response = client.get("/health")
        assert response.status_code == 500
        data = response.json()
        assert data["status"] == "error"
        assert "message" in data

    @patch('src.main._health_check')
    def test_error_logging(self, mock_health_check, client):
        """Test that errors are logged appropriately."""
        with patch('src.main.logger') as mock_logger:
            mock_health_check.side_effect = Exception("Test error")
            response = client.get("/health")
            # Check that error was logged
            mock_logger.error.assert_called()
            assert response.status_code == 500
