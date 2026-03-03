"""CLI integration tests for `bees clone` command."""

import json

from tests.helpers import write_ticket_file
from tests.test_constants import (
    HIVE_CLONE_DEST,
    HIVE_TEST,
    TICKET_ID_CLONE_BEE_ROOT,
    TICKET_ID_NONEXISTENT,
    TICKET_ID_T1,
)


def test_clone_happy_path(cli_runner, isolated_bees_env):
    """Create source bee, run `bees clone <id>`, exit 0, parse JSON stdout, assert success."""
    env = isolated_bees_env
    hive_dir = env.create_hive(HIVE_TEST)
    env.write_config()

    write_ticket_file(hive_dir, TICKET_ID_CLONE_BEE_ROOT, title="CLI Clone Source")

    stdout, exit_code = cli_runner(["clone", "--bee-id", TICKET_ID_CLONE_BEE_ROOT])

    assert exit_code == 0
    result = json.loads(stdout)
    assert result["status"] == "success"
    assert result["ticket_id"] != TICKET_ID_CLONE_BEE_ROOT
    assert result["ticket_id"].startswith("b.")
    assert result["written"] >= 1
    assert result["failed"] == []


def test_clone_error_non_bee_id(cli_runner, isolated_bees_env):
    """`bees clone t1.abc.de` exits 1 with invalid_source_type error."""
    env = isolated_bees_env
    env.create_hive(HIVE_TEST)
    env.write_config()

    stdout, exit_code = cli_runner(["clone", "--bee-id", TICKET_ID_T1])

    assert exit_code == 1
    result = json.loads(stdout)
    assert result["status"] == "error"
    assert result["error_type"] == "invalid_source_type"


def test_clone_error_nonexistent_bee(cli_runner, isolated_bees_env):
    """`bees clone b.zzz` exits 1 with bee_not_found error."""
    env = isolated_bees_env
    env.create_hive(HIVE_TEST)
    env.write_config()

    stdout, exit_code = cli_runner(["clone", "--bee-id", TICKET_ID_NONEXISTENT])

    assert exit_code == 1
    result = json.loads(stdout)
    assert result["status"] == "error"
    assert result["error_type"] == "bee_not_found"


def test_clone_hive_happy_path(cli_runner, isolated_bees_env):
    """`bees clone <id> --hive <dest>` exits 0; cloned bee exists in destination hive."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_CLONE_DEST)
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_CLONE_BEE_ROOT, title="CLI Clone Hive Source")

    stdout, exit_code = cli_runner(["clone", "--bee-id", TICKET_ID_CLONE_BEE_ROOT, "--hive", HIVE_CLONE_DEST])

    assert exit_code == 0
    result = json.loads(stdout)
    assert result["status"] == "success"
    new_id = result["ticket_id"]
    assert new_id.startswith("b.")
    assert (dest_dir / new_id).exists()


def test_clone_force_bypasses_incompatibility(cli_runner, isolated_bees_env):
    """`bees clone <id> --hive <dest> --force` exits 0 despite incompatible dest status_values."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_CLONE_DEST)
    env.hives[HIVE_CLONE_DEST]["status_values"] = ["open"]
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_CLONE_BEE_ROOT, title="Force CLI Bee", status="pupa")

    stdout, exit_code = cli_runner(["clone", "--bee-id", TICKET_ID_CLONE_BEE_ROOT, "--hive", HIVE_CLONE_DEST, "--force"])

    assert exit_code == 0
    result = json.loads(stdout)
    assert result["status"] == "success"
    assert (dest_dir / result["ticket_id"]).exists()


def test_clone_compatibility_error_via_cli(cli_runner, isolated_bees_env):
    """Incompatible dest exits 1; error_type==compatibility_error; both list fields present."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    env.create_hive(HIVE_CLONE_DEST)
    env.hives[HIVE_CLONE_DEST]["status_values"] = ["open"]
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_CLONE_BEE_ROOT, title="Compat Error CLI Bee", status="pupa")

    stdout, exit_code = cli_runner(["clone", "--bee-id", TICKET_ID_CLONE_BEE_ROOT, "--hive", HIVE_CLONE_DEST])

    assert exit_code == 1
    result = json.loads(stdout)
    assert result["status"] == "error"
    assert result["error_type"] == "compatibility_error"
    assert "incompatible_status_values" in result
    assert "incompatible_tier_types" in result


def test_clone_hive_not_found_via_cli(cli_runner, isolated_bees_env):
    """`bees clone <id> --hive nonexistent` exits 1; error_type==hive_not_found."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_CLONE_BEE_ROOT, title="Hive Not Found CLI Bee")

    stdout, exit_code = cli_runner(["clone", "--bee-id", TICKET_ID_CLONE_BEE_ROOT, "--hive", "nonexistent_hive"])

    assert exit_code == 1
    result = json.loads(stdout)
    assert result["status"] == "error"
    assert result["error_type"] == "hive_not_found"
