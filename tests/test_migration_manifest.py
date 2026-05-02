"""Unit tests for migrations.manifest — ManifestEntry dataclass and find_pending_hops."""

import pytest

import src.migrations.manifest as manifest
from src.migrations.manifest import ManifestEntry, find_pending_hops


def _noop(cfg: dict) -> None:
    """Upgrade script stub that does nothing."""


def _make_entry(from_v: str, to_v: str) -> ManifestEntry:
    return ManifestEntry(from_version=from_v, to_version=to_v, upgrade_script=_noop)


# ---------------------------------------------------------------------------
# Empty manifest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "version",
    [
        pytest.param("1.0", id="arbitrary_version"),
        pytest.param("0.0", id="zero_version"),
        pytest.param("", id="empty_string"),
    ],
)
def test_empty_manifest_returns_empty(monkeypatch, version):
    monkeypatch.setattr(manifest, "MANIFEST", [])
    assert find_pending_hops(version) == []


# ---------------------------------------------------------------------------
# Already at latest version (no-op)
# ---------------------------------------------------------------------------


def test_no_pending_hops_when_at_latest(monkeypatch):
    """Version equal to the terminal to_version has no outgoing hop → empty list."""
    monkeypatch.setattr(manifest, "MANIFEST", [_make_entry("1.0", "2.0")])
    assert find_pending_hops("2.0") == []


# ---------------------------------------------------------------------------
# Single hop
# ---------------------------------------------------------------------------


def test_single_hop_returns_that_entry(monkeypatch):
    entry = _make_entry("1.0", "2.0")
    monkeypatch.setattr(manifest, "MANIFEST", [entry])
    result = find_pending_hops("1.0")
    assert result == [entry]


# ---------------------------------------------------------------------------
# Multi-hop chain
# ---------------------------------------------------------------------------


def test_multi_hop_chain_returns_ordered_entries(monkeypatch):
    hop_a = _make_entry("1.0", "2.0")
    hop_b = _make_entry("2.0", "3.0")
    monkeypatch.setattr(manifest, "MANIFEST", [hop_a, hop_b])

    result = find_pending_hops("1.0")

    assert result == [hop_a, hop_b]


def test_multi_hop_chain_mid_start(monkeypatch):
    """Starting from the second hop skips the first."""
    hop_a = _make_entry("1.0", "2.0")
    hop_b = _make_entry("2.0", "3.0")
    monkeypatch.setattr(manifest, "MANIFEST", [hop_a, hop_b])

    result = find_pending_hops("2.0")

    assert result == [hop_b]


# ---------------------------------------------------------------------------
# Boundary / out-of-range versions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "version",
    [
        pytest.param("0.9", id="before_first_hop"),
        pytest.param("9.9", id="beyond_all_hops"),
        pytest.param("1.5", id="between_hops"),
    ],
)
def test_unknown_version_returns_empty(monkeypatch, version):
    monkeypatch.setattr(manifest, "MANIFEST", [_make_entry("1.0", "2.0"), _make_entry("2.0", "3.0")])
    assert find_pending_hops(version) == []


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


def test_cycle_in_manifest_raises_value_error(monkeypatch):
    """A circular hop chain must raise ValueError, not loop forever."""
    monkeypatch.setattr(
        manifest, "MANIFEST", [_make_entry("1.0", "2.0"), _make_entry("2.0", "1.0")]
    )
    with pytest.raises(ValueError, match="Cycle detected"):
        find_pending_hops("1.0")
