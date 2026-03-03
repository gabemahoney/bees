#!/usr/bin/env python3
"""
Bees performance benchmark — full test matrix.

Measures create, show, update, find (title query), and delete operations
at multiple scales for bees, t1s, and t2s, with warm/cold cache variants.

Usage:
    poetry run python scripts/benchmark.py
    poetry run python scripts/benchmark.py --sizes 10,100,1000
    poetry run python scripts/benchmark.py --stress
"""

import argparse
import asyncio
import itertools
import json
import shutil
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import src.cache
import src.config
from src.mcp_query_ops import _execute_freeform_query
from src.mcp_ticket_ops import _create_ticket, _delete_ticket, _show_ticket, _update_ticket
from src.repo_context import repo_root_context


PERF_DIR = Path(__file__).parent.parent.parent / "tickets" / "perf"
STRESS_DIR = Path(__file__).parent.parent.parent / "perf" / "stress"

CHARSET = "123456789abcdefghijkmnopqrstuvwxyz"


# ── Infrastructure ────────────────────────────────────────────────────────────


def make_bench_dir(name: str) -> Path:
    """Create a benchmark working directory under tickets/perf/."""
    PERF_DIR.mkdir(parents=True, exist_ok=True)
    d = PERF_DIR / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir()
    return d


def setup_env(tmpdir: Path, child_tiers: dict | None = None, num_hives: int = 1) -> list[str]:
    """Set up an isolated bees environment in tmpdir.

    Creates ``num_hives`` hives and wires up a fresh global config pointing
    at ``tmpdir``.

    Returns:
        List of hive names created.
    """
    global_bees_dir = tmpdir / ".bees"
    global_bees_dir.mkdir(parents=True, exist_ok=True)

    hive_names = [f"bench{i}" for i in range(num_hives)]

    hives_config = {}
    for hive_name in hive_names:
        hive_dir = tmpdir / hive_name
        hive_dir.mkdir(exist_ok=True)
        hives_config[hive_name] = {
            "path": str(hive_dir),
            "display_name": hive_name.capitalize(),
        }

    config = {
        "scopes": {
            str(tmpdir): {
                "hives": hives_config,
                "child_tiers": child_tiers if child_tiers is not None else {},
            }
        },
        "schema_version": "2.0",
    }
    (global_bees_dir / "config.json").write_text(json.dumps(config, indent=2))

    # Redirect global config to our temp dir
    src.config.get_global_bees_dir = lambda: global_bees_dir
    src.config.get_global_config_path = lambda: global_bees_dir / "config.json"
    src.config._SCOPE_PATTERN_CACHE.clear()
    src.config._GLOBAL_CONFIG_CACHE = None
    src.config._GLOBAL_CONFIG_CACHE_MTIME = None
    src.config._GLOBAL_CONFIG_OVERRIDE = None
    src.cache.clear()
    return hive_names


def fmt_ms(seconds: float) -> str:
    if seconds < 1.0:
        return f"{seconds * 1000:.1f}ms"
    return f"{seconds:.3f}s"


def _ticket_content(ticket_id: str, ticket_type: str, title: str, seq: int, parent: str | None = None) -> str:
    short_id = ticket_id.replace(".", "")
    guid = f"{short_id}{seq:0{32 - len(short_id)}d}"[:32]
    parent_line = f"parent: {parent}\n" if parent else ""
    return (
        f"---\n"
        f"id: {ticket_id}\n"
        f"type: {ticket_type}\n"
        f"title: {title}\n"
        f"{parent_line}"
        f"status: null\n"
        f"created_at: '2026-01-01T00:00:00'\n"
        f"schema_version: '0.1'\n"
        f"guid: {guid}\n"
        f"---\n"
    )


def write_bee_direct(hive_dir: Path, ticket_id: str, seq: int, title: str | None = None) -> None:
    """Write a minimal valid bee file directly to disk, no bees code involved."""
    ticket_dir = hive_dir / ticket_id
    ticket_dir.mkdir(exist_ok=True)
    (ticket_dir / f"{ticket_id}.md").write_text(
        _ticket_content(ticket_id, "bee", title or f"Stress bee {seq:05d}", seq)
    )


def write_child_direct(ticket_dir: Path, ticket_id: str, ticket_type: str, title: str, seq: int, parent: str) -> None:
    ticket_dir.mkdir(parents=True, exist_ok=True)
    (ticket_dir / f"{ticket_id}.md").write_text(
        _ticket_content(ticket_id, ticket_type, title, seq, parent)
    )


def _gen_ids(prefix: str, length: int, count: int) -> list[str]:
    """Generate ``count`` sequential IDs with given prefix and char length."""
    ids = []
    for chars in itertools.islice(itertools.product(CHARSET, repeat=length), count):
        raw = "".join(chars)
        if length == 3:
            ids.append(f"{prefix}.{raw}")
        elif length == 5:
            ids.append(f"{prefix}.{raw[:3]}.{raw[3:5]}")
        elif length == 7:
            ids.append(f"{prefix}.{raw[:3]}.{raw[3:5]}.{raw[5:7]}")
    return ids


# ── Output formatting ─────────────────────────────────────────────────────────


def _print_section(label: str):
    print(f"\n[{label}]")


def _print_create(n: int, elapsed: float):
    label = f"Create {n}:"
    print(f"  {label:<16}{fmt_ms(elapsed):>10}")


def _print_warm_cold(op: str, warm: float, cold: float):
    print(f"  {op:<11}warm: {fmt_ms(warm):>10}   cold: {fmt_ms(cold):>10}")


# ── Shared benchmark operations ───────────────────────────────────────────────


async def _bench_ops(
    ticket_ids: list[str],
    ticket_type: str,
    tmpdir: Path,
    del_ids_warm: list[str],
    del_ids_cold: list[str],
) -> None:
    """Run update, show, find, and delete benchmarks with warm/cold variants.

    Args:
        ticket_ids: IDs to use for update / show / find operations.
        ticket_type: Ticket type string for the find query (``bee``, ``t1``, ``t2``).
        tmpdir: Benchmark working directory (passed as resolved_root).
        del_ids_warm: 10 IDs to delete in the warm pass.
        del_ids_cold: 10 IDs to delete in the cold pass.
    """
    # ── Update 1 ──────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    await _update_ticket(ticket_id=ticket_ids[0], status="pupa", resolved_root=tmpdir)
    w = time.perf_counter() - t0

    src.cache.clear()
    t0 = time.perf_counter()
    await _update_ticket(ticket_id=ticket_ids[1 % len(ticket_ids)], status="pupa", resolved_root=tmpdir)
    c = time.perf_counter() - t0
    _print_warm_cold("Update 1", w, c)

    # ── Update 10 ─────────────────────────────────────────────────────────
    batch = ticket_ids[:min(10, len(ticket_ids))]
    t0 = time.perf_counter()
    await _update_ticket(ticket_id=batch, status="worker", resolved_root=tmpdir)
    w = time.perf_counter() - t0

    src.cache.clear()
    t0 = time.perf_counter()
    await _update_ticket(ticket_id=batch, status="finished", resolved_root=tmpdir)
    c = time.perf_counter() - t0
    _print_warm_cold("Update 10", w, c)

    # ── Show 1 ────────────────────────────────────────────────────────────
    mid = ticket_ids[len(ticket_ids) // 2]
    t0 = time.perf_counter()
    await _show_ticket([mid], resolved_root=tmpdir)
    w = time.perf_counter() - t0

    src.cache.clear()
    t0 = time.perf_counter()
    await _show_ticket([mid], resolved_root=tmpdir)
    c = time.perf_counter() - t0
    _print_warm_cold("Show 1", w, c)

    # ── Show 10 ───────────────────────────────────────────────────────────
    show_batch = ticket_ids[:min(10, len(ticket_ids))]
    t0 = time.perf_counter()
    await _show_ticket(show_batch, resolved_root=tmpdir)
    w = time.perf_counter() - t0

    src.cache.clear()
    t0 = time.perf_counter()
    await _show_ticket(show_batch, resolved_root=tmpdir)
    c = time.perf_counter() - t0
    _print_warm_cold("Show 10", w, c)

    # ── Find foo ──────────────────────────────────────────────────────────
    query = f"- ['type={ticket_type}', 'title~^foo$']"
    t0 = time.perf_counter()
    await _execute_freeform_query(query, resolved_root=tmpdir)
    w = time.perf_counter() - t0

    src.cache.clear()
    t0 = time.perf_counter()
    await _execute_freeform_query(query, resolved_root=tmpdir)
    c = time.perf_counter() - t0
    _print_warm_cold("Find foo", w, c)

    # ── Delete 10 ─────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    await _delete_ticket(del_ids_warm, resolved_root=tmpdir)
    w = time.perf_counter() - t0

    src.cache.clear()
    t0 = time.perf_counter()
    await _delete_ticket(del_ids_cold, resolved_root=tmpdir)
    c = time.perf_counter() - t0
    _print_warm_cold("Delete 10", w, c)


# ── Bees benchmark ────────────────────────────────────────────────────────────


async def run_bees(n: int, num_hives: int) -> None:
    _print_section(f"bees n={n}, {num_hives} hive{'s' if num_hives != 1 else ''}")

    tmpdir = make_bench_dir(f"bees_{n}")
    success = False
    try:
        hive_names = setup_env(tmpdir, num_hives=num_hives)

        with repo_root_context(tmpdir):
            # ── Create N bees (first has title "foo") ─────────────────────
            ticket_ids: list[str] = []
            t0 = time.perf_counter()
            for i in range(n):
                hive_name = hive_names[i % len(hive_names)]
                title = "foo" if i == 0 else f"Bench bee {i:04d}"
                r = await _create_ticket(
                    ticket_type="bee", title=title,
                    hive_name=hive_name, resolved_root=tmpdir,
                )
                if r["status"] != "success":
                    raise RuntimeError(f"create failed at i={i}: {r}")
                ticket_ids.append(r["ticket_id"])
            _print_create(n, time.perf_counter() - t0)

            # ── 20 sacrificial bees for delete benchmark (untimed) ────────
            del_ids: list[str] = []
            for j in range(20):
                hive_name = hive_names[j % len(hive_names)]
                r = await _create_ticket(
                    ticket_type="bee", title=f"Del {j}",
                    hive_name=hive_name, resolved_root=tmpdir,
                )
                if r["status"] != "success":
                    raise RuntimeError(f"del-prep create failed: {r}")
                del_ids.append(r["ticket_id"])

            await _bench_ops(ticket_ids, "bee", tmpdir, del_ids[:10], del_ids[10:])

        success = True
    finally:
        if success:
            shutil.rmtree(tmpdir, ignore_errors=True)
        else:
            print(f"  [kept for inspection: {tmpdir}]")


# ── 39k stress benchmark ─────────────────────────────────────────────────────


async def run_stress() -> None:
    """Stress test on the persisted ~39k-bee hive at STRESS_DIR."""
    all_ids = [f"b.{''.join(c)}" for c in itertools.product(CHARSET, repeat=3)]
    n = len(all_ids)
    _print_section(f"bees n={n}, 1 hive (stress)")

    tmpdir = STRESS_DIR
    hive_names = setup_env(tmpdir, num_hives=1)
    hive_dir = tmpdir / hive_names[0]

    # ── Build hive if not already populated ───────────────────────────────
    existing_count = sum(1 for _ in hive_dir.iterdir()) if hive_dir.exists() else 0
    if existing_count >= n:
        print(f"  reusing existing stress hive ({existing_count} bees)")
    else:
        print(f"  writing {n} bees directly to disk...", end="", flush=True)
        t0 = time.perf_counter()
        for seq, ticket_id in enumerate(all_ids):
            write_bee_direct(hive_dir, ticket_id, seq)
        print(f" {fmt_ms(time.perf_counter() - t0)}")

    with repo_root_context(tmpdir):
        # ── Ensure exactly 1 bee has title "foo" ──────────────────────────
        r = await _execute_freeform_query("- ['type=bee', 'title~^foo$']", resolved_root=tmpdir)
        if r["status"] == "success" and r["result_count"] == 0:
            await _update_ticket(ticket_id=all_ids[0], title="foo", resolved_root=tmpdir)
            foo_id = all_ids[0]
            src.cache.clear()
        elif r["status"] == "success" and r["result_count"] > 0:
            foo_id = r["ticket_ids"][0]
        else:
            foo_id = all_ids[0]

        # ── Pick 20 delete targets (excluding the foo bee), will restore ──
        del_candidates = [tid for tid in all_ids if tid != foo_id]
        del_warm = del_candidates[-20:-10]
        del_cold = del_candidates[-10:]

        await _bench_ops(all_ids, "bee", tmpdir, del_warm, del_cold)

        # ── Restore deleted bees so the stress hive stays intact ──────────
        for seq, tid in enumerate(del_warm + del_cold):
            write_bee_direct(hive_dir, tid, 99000 + seq)


# ── t1 benchmark ──────────────────────────────────────────────────────────────


async def run_t1s(n: int, num_hives: int) -> None:
    _print_section(f"t1s n={n}, {num_hives} hive{'s' if num_hives != 1 else ''}")

    tmpdir = make_bench_dir(f"t1s_{n}")
    success = False
    try:
        hive_names = setup_env(
            tmpdir, child_tiers={"t1": ["t1", "t1s"]}, num_hives=num_hives,
        )

        # ── Write parent bees directly (1 per hive, not timed) ────────────
        bee_ids = _gen_ids("b", 3, num_hives)
        bee_hive: dict[str, str] = {}
        for h, hive_name in enumerate(hive_names):
            bee_id = bee_ids[h]
            write_bee_direct(tmpdir / hive_name, bee_id, h)
            bee_hive[bee_id] = hive_name

        with repo_root_context(tmpdir):
            # ── Create N t1s (first has title "foo") ──────────────────────
            t1_ids: list[str] = []
            t0 = time.perf_counter()
            for i in range(n):
                parent_bee = bee_ids[i % num_hives]
                title = "foo" if i == 0 else f"T1 {i:04d}"
                r = await _create_ticket(
                    ticket_type="t1", title=title,
                    hive_name=bee_hive[parent_bee], parent=parent_bee,
                    resolved_root=tmpdir,
                )
                if r["status"] != "success":
                    raise RuntimeError(f"t1 create failed at i={i}: {r}")
                t1_ids.append(r["ticket_id"])
            _print_create(n, time.perf_counter() - t0)

            # ── 20 sacrificial t1s for delete benchmark ───────────────────
            del_ids: list[str] = []
            for j in range(20):
                parent_bee = bee_ids[j % num_hives]
                r = await _create_ticket(
                    ticket_type="t1", title=f"Del {j}",
                    hive_name=bee_hive[parent_bee], parent=parent_bee,
                    resolved_root=tmpdir,
                )
                if r["status"] != "success":
                    raise RuntimeError(f"del-prep t1 create failed: {r}")
                del_ids.append(r["ticket_id"])

            await _bench_ops(t1_ids, "t1", tmpdir, del_ids[:10], del_ids[10:])

        success = True
    finally:
        if success:
            shutil.rmtree(tmpdir, ignore_errors=True)
        else:
            print(f"  [kept for inspection: {tmpdir}]")


# ── t2 benchmark ──────────────────────────────────────────────────────────────


async def run_t2s(n: int, num_hives: int) -> None:
    _print_section(f"t2s n={n}, {num_hives} hive{'s' if num_hives != 1 else ''}")

    tmpdir = make_bench_dir(f"t2s_{n}")
    success = False
    try:
        hive_names = setup_env(
            tmpdir,
            child_tiers={"t1": ["t1", "t1s"], "t2": ["t2", "t2s"]},
            num_hives=num_hives,
        )

        # ── Write parent bees + t1s directly (not timed) ─────────────────
        bee_ids = _gen_ids("b", 3, num_hives)
        _t1_suffixes = list(itertools.islice(itertools.product(CHARSET, repeat=2), 1))
        t1_ids = [f"t1.{bid[2:]}.{''.join(sfx)}" for bid in bee_ids for sfx in _t1_suffixes]

        t1_hive: dict[str, str] = {}
        for h, hive_name in enumerate(hive_names):
            bee_id = bee_ids[h]
            hive_dir = tmpdir / hive_name
            write_bee_direct(hive_dir, bee_id, h)

            t1_id = t1_ids[h]
            write_child_direct(
                hive_dir / bee_id / t1_id, t1_id, "t1",
                f"T1 {h:04d}", h, bee_id,
            )
            t1_hive[t1_id] = hive_name

        with repo_root_context(tmpdir):
            # ── Create N t2s (first has title "foo") ──────────────────────
            t2_ids: list[str] = []
            t0 = time.perf_counter()
            for i in range(n):
                parent_t1 = t1_ids[i % num_hives]
                title = "foo" if i == 0 else f"T2 {i:04d}"
                r = await _create_ticket(
                    ticket_type="t2", title=title,
                    hive_name=t1_hive[parent_t1], parent=parent_t1,
                    resolved_root=tmpdir,
                )
                if r["status"] != "success":
                    raise RuntimeError(f"t2 create failed at i={i}: {r}")
                t2_ids.append(r["ticket_id"])
            _print_create(n, time.perf_counter() - t0)

            # ── 20 sacrificial t2s for delete benchmark ───────────────────
            del_ids: list[str] = []
            for j in range(20):
                parent_t1 = t1_ids[j % num_hives]
                r = await _create_ticket(
                    ticket_type="t2", title=f"Del {j}",
                    hive_name=t1_hive[parent_t1], parent=parent_t1,
                    resolved_root=tmpdir,
                )
                if r["status"] != "success":
                    raise RuntimeError(f"del-prep t2 create failed: {r}")
                del_ids.append(r["ticket_id"])

            await _bench_ops(t2_ids, "t2", tmpdir, del_ids[:10], del_ids[10:])

        success = True
    finally:
        if success:
            shutil.rmtree(tmpdir, ignore_errors=True)
        else:
            print(f"  [kept for inspection: {tmpdir}]")


# ── Main ──────────────────────────────────────────────────────────────────────


async def main(sizes: list[int]) -> None:
    print("=" * 60)
    print("Bees Performance Benchmark")
    print("=" * 60)

    # Bees at each scale
    for n in sizes:
        num_hives = max(1, n // 10)
        await run_bees(n, num_hives)

    # 39k stress hive
    await run_stress()

    # t1s at each scale
    for n in sizes:
        num_hives = max(1, n // 10)
        await run_t1s(n, num_hives)

    # t2s at each scale
    for n in sizes:
        num_hives = max(1, n // 10)
        await run_t2s(n, num_hives)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bees performance benchmark")
    parser.add_argument(
        "--sizes",
        default="10,100,1000",
        help="Comma-separated ticket counts (default: 10,100,1000)",
    )
    parser.add_argument(
        "--stress",
        action="store_true",
        help="Run only the 39k stress test",
    )
    args = parser.parse_args()
    sizes = [int(s) for s in args.sizes.split(",")]

    if args.stress:
        asyncio.run(run_stress())
    else:
        asyncio.run(main(sizes))
