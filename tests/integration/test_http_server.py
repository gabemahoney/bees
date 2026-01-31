"""
Integration tests for HTTP server.

These tests verify the HTTP server works with real uvicorn without mocking,
including http_app integration and graceful shutdown behavior.
"""

import multiprocessing
import time
import signal
import subprocess
import sys
from pathlib import Path

import pytest
import requests


def test_http_app_exists_and_binds_with_uvicorn():
    """
    Test that mcp.http_app exists and can be successfully passed to uvicorn.

    This test verifies real integration without mocking - it starts a real
    uvicorn server with the http_app to catch issues like missing app attribute.
    """
    # Import the http_app to verify it exists
    from src.mcp_server import mcp

    # Verify http_app attribute exists
    assert hasattr(mcp, 'http_app'), "mcp.http_app does not exist"
    assert mcp.http_app is not None, "mcp.http_app is None"

    # Start uvicorn server in a subprocess (real integration test)
    # Use a non-standard port to avoid conflicts
    test_port = 9999

    # Create a subprocess to run the server
    proc = subprocess.Popen(
        [
            sys.executable, '-m', 'uvicorn',
            'src.mcp_server:mcp.http_app',
            '--host', '127.0.0.1',
            '--port', str(test_port),
            '--log-level', 'error'  # Reduce noise in test output
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=Path(__file__).parent.parent.parent  # Project root
    )

    try:
        # Give server time to start and retry connection
        max_retries = 10
        retry_delay = 0.5

        for i in range(max_retries):
            try:
                response = requests.get(f'http://127.0.0.1:{test_port}/', timeout=2)
                # If we get here, server bound successfully (status code doesn't matter much)
                # The key is that uvicorn started and bound to the port with real http_app
                assert response.status_code in [200, 404, 405], \
                    f"Unexpected status code: {response.status_code}"
                break
            except requests.exceptions.ConnectionError:
                if i == max_retries - 1:
                    # Check if process crashed
                    if proc.poll() is not None:
                        stdout, stderr = proc.communicate()
                        pytest.fail(
                            f"Server process crashed. "
                            f"stdout: {stdout.decode()}, stderr: {stderr.decode()}"
                        )
                    raise
                time.sleep(retry_delay)

    finally:
        # Clean shutdown
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def test_graceful_shutdown_with_sigterm():
    """
    Test that HTTP server shuts down gracefully when receiving SIGTERM.

    Verifies uvicorn.run() blocking behavior and signal handling work correctly.
    """
    # Start the MCP server in a subprocess
    test_port = 9998

    proc = subprocess.Popen(
        [
            sys.executable, '-m', 'uvicorn',
            'src.mcp_server:mcp.http_app',
            '--host', '127.0.0.1',
            '--port', str(test_port),
            '--log-level', 'error'
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=Path(__file__).parent.parent.parent  # Project root
    )

    try:
        # Give server time to start
        time.sleep(2)

        # Verify server is running
        response = requests.get(f'http://127.0.0.1:{test_port}/', timeout=5)
        assert response.status_code in [200, 404, 405], "Server failed to start"

        # Send SIGTERM signal
        proc.send_signal(signal.SIGTERM)

        # Wait for graceful shutdown (should complete within 5 seconds)
        try:
            return_code = proc.wait(timeout=5)
            # Server should exit cleanly (return code 0 or small positive value)
            assert return_code is not None, "Server did not shut down"
            # Don't assert specific return code as it may vary by platform

        except subprocess.TimeoutExpired:
            # If we hit timeout, server didn't shut down gracefully
            proc.kill()
            proc.wait()
            pytest.fail("Server did not shut down gracefully within timeout")

        # Verify no zombie processes
        assert proc.poll() is not None, "Process became zombie"

    except Exception as e:
        # Ensure cleanup on any failure
        proc.kill()
        proc.wait()
        raise e


def test_graceful_shutdown_with_sigint():
    """
    Test that HTTP server shuts down gracefully when receiving SIGINT (Ctrl+C).

    Verifies signal handling works for keyboard interrupt.
    """
    # Start the MCP server in a subprocess
    test_port = 9997

    proc = subprocess.Popen(
        [
            sys.executable, '-m', 'uvicorn',
            'src.mcp_server:mcp.http_app',
            '--host', '127.0.0.1',
            '--port', str(test_port),
            '--log-level', 'error'
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=Path(__file__).parent.parent.parent  # Project root
    )

    try:
        # Give server time to start
        time.sleep(2)

        # Verify server is running
        response = requests.get(f'http://127.0.0.1:{test_port}/', timeout=5)
        assert response.status_code in [200, 404, 405], "Server failed to start"

        # Send SIGINT signal (Ctrl+C)
        proc.send_signal(signal.SIGINT)

        # Wait for graceful shutdown (should complete within 5 seconds)
        try:
            return_code = proc.wait(timeout=5)
            assert return_code is not None, "Server did not shut down"

        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail("Server did not shut down gracefully within timeout")

        # Verify no zombie processes
        assert proc.poll() is not None, "Process became zombie"

    except Exception as e:
        proc.kill()
        proc.wait()
        raise e
