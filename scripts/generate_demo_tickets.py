#!/usr/bin/env python3
"""Generate diverse sample tickets for testing index generation.

This script creates a representative set of epics, tasks, and subtasks with:
- Various statuses (open, in progress, completed)
- Different priorities (0-4)
- Multiple labels
- Dependency chains (blocked_by relationships)
- Parent-child relationships

Usage:
    python scripts/generate_demo_tickets.py
"""

import sys
from pathlib import Path

# Add project root to path so we can import src module
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ticket_factory import create_epic, create_task, create_subtask


def generate_demo_epics() -> dict[str, str]:
    """Generate diverse sample epic tickets.

    Returns:
        Dictionary mapping epic names to their ticket IDs
    """
    epics = {}

    # Epic 1: High priority, open, backend
    epics["auth_system"] = create_epic(
        title="User Authentication System",
        description="Implement complete user authentication with login, registration, and password reset",
        labels=["backend", "security", "high-priority"],
        status="open",
        priority=0,
        owner="backend-team",
        hive_name="default"
    )

    # Epic 2: In progress, frontend
    epics["dashboard"] = create_epic(
        title="Admin Dashboard",
        description="Build admin dashboard with analytics and user management",
        labels=["frontend", "ui", "analytics"],
        status="in progress",
        priority=1,
        owner="frontend-team",
        hive_name="default"
    )

    # Epic 3: Completed, full-stack
    epics["api_core"] = create_epic(
        title="Core API Infrastructure",
        description="Set up core API infrastructure with error handling, logging, and monitoring",
        labels=["backend", "devops", "infrastructure"],
        status="completed",
        priority=0,
        owner="platform-team",
        hive_name="default"
    )

    # Epic 4: Open, low priority, documentation
    epics["docs"] = create_epic(
        title="Developer Documentation Portal",
        description="Create comprehensive documentation portal for developers",
        labels=["documentation", "developer-experience"],
        status="open",
        priority=3,
        owner="docs-team",
        hive_name="default"
    )

    # Epic 5: In progress, mobile
    epics["mobile_app"] = create_epic(
        title="Mobile Application",
        description="Develop iOS and Android mobile applications",
        labels=["mobile", "ios", "android"],
        status="in progress",
        priority=1,
        owner="mobile-team",
        hive_name="default"
    )

    print(f"✓ Generated {len(epics)} epics")
    return epics


def generate_demo_tasks(epics: dict[str, str]) -> dict[str, str]:
    """Generate diverse sample task tickets with dependencies.

    Args:
        epics: Dictionary of epic names to IDs

    Returns:
        Dictionary mapping task names to their ticket IDs
    """
    tasks = {}

    # Tasks for auth_system epic
    tasks["auth_db_schema"] = create_task(
        title="Design authentication database schema",
        description="Create database tables for users, sessions, and password reset tokens",
        parent=epics["auth_system"],
        labels=["backend", "database", "schema"],
        status="completed",
        priority=0,
        owner="alice@example.com",
        hive_name="default"
    )

    tasks["auth_api"] = create_task(
        title="Implement authentication API endpoints",
        description="Build REST API for login, register, logout, and password reset",
        parent=epics["auth_system"],
        labels=["backend", "api"],
        status="in progress",
        priority=0,
        owner="bob@example.com",
        up_dependencies=[tasks["auth_db_schema"]],  # Blocked by database schema
        hive_name="default"
    )

    tasks["auth_jwt"] = create_task(
        title="Add JWT token generation and validation",
        description="Implement JWT-based authentication with refresh tokens",
        parent=epics["auth_system"],
        labels=["backend", "security"],
        status="open",
        priority=1,
        owner="alice@example.com",
        up_dependencies=[tasks["auth_api"]],  # Blocked by API implementation
        hive_name="default"
    )

    # Tasks for dashboard epic
    tasks["dashboard_layout"] = create_task(
        title="Create dashboard layout components",
        description="Build responsive layout with sidebar, header, and content areas",
        parent=epics["dashboard"],
        labels=["frontend", "ui", "react"],
        status="completed",
        priority=1,
        owner="carol@example.com",
        hive_name="default"
    )

    tasks["dashboard_analytics"] = create_task(
        title="Implement analytics charts and graphs",
        description="Add data visualization for user metrics and system stats",
        parent=epics["dashboard"],
        labels=["frontend", "analytics", "charts"],
        status="in progress",
        priority=1,
        owner="dave@example.com",
        up_dependencies=[tasks["dashboard_layout"]],  # Blocked by layout
        hive_name="default"
    )

    # Tasks for api_core epic (completed)
    tasks["api_logging"] = create_task(
        title="Set up API logging infrastructure",
        description="Configure structured logging with request/response tracking",
        parent=epics["api_core"],
        labels=["backend", "logging", "monitoring"],
        status="completed",
        priority=0,
        owner="eve@example.com",
        hive_name="default"
    )

    tasks["api_error_handling"] = create_task(
        title="Implement centralized error handling",
        description="Create error handling middleware with standardized error responses",
        parent=epics["api_core"],
        labels=["backend", "error-handling"],
        status="completed",
        priority=0,
        owner="frank@example.com",
        hive_name="default"
    )

    # Tasks for docs epic
    tasks["docs_setup"] = create_task(
        title="Set up documentation site framework",
        description="Initialize documentation site with MkDocs or similar framework",
        parent=epics["docs"],
        labels=["documentation", "setup"],
        status="open",
        priority=3,
        owner="grace@example.com",
        hive_name="default"
    )

    print(f"✓ Generated {len(tasks)} tasks")
    return tasks


def generate_demo_subtasks(tasks: dict[str, str]) -> dict[str, str]:
    """Generate diverse sample subtask tickets.

    Args:
        tasks: Dictionary of task names to IDs

    Returns:
        Dictionary mapping subtask names to their ticket IDs
    """
    subtasks = {}

    # Subtasks for auth_db_schema (completed)
    subtasks["auth_users_table"] = create_subtask(
        title="Create users table migration",
        parent=tasks["auth_db_schema"],
        description="Define users table with email, password_hash, created_at, etc.",
        labels=["database", "migration"],
        status="completed",
        priority=0,
        owner="alice@example.com",
        hive_name="default"
    )

    subtasks["auth_sessions_table"] = create_subtask(
        title="Create sessions table migration",
        parent=tasks["auth_db_schema"],
        description="Define sessions table with user_id, token, expires_at",
        labels=["database", "migration"],
        status="completed",
        priority=0,
        owner="alice@example.com",
        hive_name="default"
    )

    # Subtasks for auth_api (in progress)
    subtasks["auth_login_endpoint"] = create_subtask(
        title="Implement POST /auth/login endpoint",
        parent=tasks["auth_api"],
        description="Create login endpoint with email/password validation",
        labels=["backend", "api", "endpoint"],
        status="completed",
        priority=0,
        owner="bob@example.com",
        hive_name="default"
    )

    subtasks["auth_register_endpoint"] = create_subtask(
        title="Implement POST /auth/register endpoint",
        parent=tasks["auth_api"],
        description="Create registration endpoint with validation and email verification",
        labels=["backend", "api", "endpoint"],
        status="in progress",
        priority=0,
        owner="bob@example.com",
        hive_name="default"
    )

    subtasks["auth_logout_endpoint"] = create_subtask(
        title="Implement POST /auth/logout endpoint",
        parent=tasks["auth_api"],
        description="Create logout endpoint to invalidate sessions",
        labels=["backend", "api", "endpoint"],
        status="open",
        priority=1,
        owner="bob@example.com",
        hive_name="default"
    )

    # Subtasks for auth_jwt (open)
    subtasks["jwt_generation"] = create_subtask(
        title="Implement JWT token generation",
        parent=tasks["auth_jwt"],
        description="Create function to generate JWT with user claims",
        labels=["backend", "security", "jwt"],
        status="open",
        priority=1,
        owner="alice@example.com",
        hive_name="default"
    )

    subtasks["jwt_validation"] = create_subtask(
        title="Implement JWT token validation",
        parent=tasks["auth_jwt"],
        description="Create middleware to validate JWT tokens on protected routes",
        labels=["backend", "security", "jwt"],
        status="open",
        priority=1,
        owner="alice@example.com",
        hive_name="default"
    )

    # Subtasks for dashboard_layout (completed)
    subtasks["dashboard_sidebar"] = create_subtask(
        title="Create sidebar navigation component",
        parent=tasks["dashboard_layout"],
        description="Build responsive sidebar with menu items and active state",
        labels=["frontend", "ui", "component"],
        status="completed",
        priority=1,
        owner="carol@example.com",
        hive_name="default"
    )

    subtasks["dashboard_header"] = create_subtask(
        title="Create header component with user menu",
        parent=tasks["dashboard_layout"],
        description="Build header with logo, search, and user dropdown menu",
        labels=["frontend", "ui", "component"],
        status="completed",
        priority=1,
        owner="carol@example.com",
        hive_name="default"
    )

    # Subtasks for dashboard_analytics (in progress)
    subtasks["analytics_line_chart"] = create_subtask(
        title="Add line chart for time series data",
        parent=tasks["dashboard_analytics"],
        description="Implement line chart component using Chart.js or similar",
        labels=["frontend", "charts", "visualization"],
        status="in progress",
        priority=1,
        owner="dave@example.com",
        hive_name="default"
    )

    subtasks["analytics_bar_chart"] = create_subtask(
        title="Add bar chart for categorical data",
        parent=tasks["dashboard_analytics"],
        description="Implement bar chart for displaying category comparisons",
        labels=["frontend", "charts", "visualization"],
        status="open",
        priority=2,
        owner="dave@example.com",
        hive_name="default"
    )

    subtasks["analytics_pie_chart"] = create_subtask(
        title="Add pie chart for distribution data",
        parent=tasks["dashboard_analytics"],
        description="Implement pie chart for showing percentage distributions",
        labels=["frontend", "charts", "visualization"],
        status="open",
        priority=2,
        owner="dave@example.com",
        hive_name="default"
    )

    # Subtasks for api_logging (completed)
    subtasks["logging_setup"] = create_subtask(
        title="Configure Winston logging library",
        parent=tasks["api_logging"],
        description="Set up Winston with appropriate log levels and transports",
        labels=["backend", "logging", "configuration"],
        status="completed",
        priority=0,
        owner="eve@example.com",
        hive_name="default"
    )

    subtasks["logging_middleware"] = create_subtask(
        title="Create request logging middleware",
        parent=tasks["api_logging"],
        description="Add middleware to log all incoming requests and responses",
        labels=["backend", "logging", "middleware"],
        status="completed",
        priority=0,
        owner="eve@example.com",
        hive_name="default"
    )

    # Subtasks for docs_setup (open)
    subtasks["docs_framework"] = create_subtask(
        title="Install and configure MkDocs",
        parent=tasks["docs_setup"],
        description="Set up MkDocs with material theme and plugins",
        labels=["documentation", "setup", "tooling"],
        status="open",
        priority=3,
        owner="grace@example.com",
        hive_name="default"
    )

    print(f"✓ Generated {len(subtasks)} subtasks")
    return subtasks


def main():
    """Generate all demo tickets."""
    print("Generating demo tickets...")
    print()

    # Generate epics
    epics = generate_demo_epics()

    # Generate tasks
    tasks = generate_demo_tasks(epics)

    # Generate subtasks
    subtasks = generate_demo_subtasks(tasks)

    print()
    print("Demo tickets generated successfully!")
    print(f"Total: {len(epics)} epics, {len(tasks)} tasks, {len(subtasks)} subtasks")


if __name__ == "__main__":
    main()
