#!/usr/bin/env python3
"""Print the address the CI bees HTTP server must bind to so that the CI containers can reach it.

The containers reach the host through ``host.docker.internal``, which run_test.sh maps with
``--add-host host.docker.internal:host-gateway``. Where that name leads depends on the Docker setup:

- Linux Docker Engine: the default bridge gateway (e.g. 172.17.0.1), an address of the host's own
  bridge interface. A server bound to 127.0.0.1 is unreachable from the containers.
- Docker Desktop: the bridge lives inside a VM, so its gateway is not an address of the host, and
  traffic to host.docker.internal is forwarded to the host's loopback. 127.0.0.1 is right.

This script reads the JSON output of ``docker network inspect bridge`` on stdin and prints one
address on stdout: the bridge's IPv4 gateway if it is an address of this host, otherwise 127.0.0.1.
It never prints 0.0.0.0, which would expose the server on every network. A one-line reason goes to
stderr. It always exits 0: unreadable input falls back to 127.0.0.1.

Stdlib only: it runs on the host with plain python3.

Usage:
    docker network inspect bridge | python3 ci_bind_host.py
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import sys

LOOPBACK = "127.0.0.1"
# A connection to an address of this host completes at once; one to another host may hang.
CONNECT_TIMEOUT_SECONDS = 0.5


def bridge_gateways(inspect_output: str) -> list[str]:
    """Return the IPAM gateways in ``docker network inspect`` JSON output, in order ([] if none or unreadable)."""
    try:
        networks = json.loads(inspect_output)
        gateways = [config.get("Gateway") for network in networks for config in network["IPAM"]["Config"] or []]
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
        return []
    return [gateway for gateway in gateways if isinstance(gateway, str) and gateway]


def _first_ipv4(gateways: list[str]) -> ipaddress.IPv4Address | None:
    """Return the first gateway that is an IPv4 address (a /prefix suffix is ignored), or None."""
    for gateway in gateways:
        try:
            address = ipaddress.ip_interface(gateway.strip()).ip
        except ValueError:
            continue
        if isinstance(address, ipaddress.IPv4Address):
            return address
    return None


def local_address_error(address: str) -> str | None:
    """Return why ``address`` is not an address of this host, or None if it is.

    Binding alone is no proof: with net.ipv4.ip_nonlocal_bind=1, Linux lets a socket bind any address.
    So this listens on the bound socket and connects to it, which works only for an address of this host.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.bind((address, 0))
            server.listen(1)
            with socket.create_connection(server.getsockname(), timeout=CONNECT_TIMEOUT_SECONDS):
                pass
    except OSError as exc:  # socket.timeout is an OSError on Python 3.9 too
        return str(exc)
    return None


def choose_bind_host(gateways: list[str]) -> tuple[str, str]:
    """Return (bind_host, reason): the first IPv4 bridge gateway if it is an address of this host, else 127.0.0.1."""
    gateway = _first_ipv4(gateways)
    if gateway is None:
        return LOOPBACK, f"bind host {LOOPBACK}: no IPv4 gateway found for the Docker bridge network"
    # The wildcard address would expose the server on every network; multicast and reserved
    # addresses (such as the broadcast address) can be bound but are not a host address.
    if gateway.is_unspecified or gateway.is_multicast or gateway.is_reserved:
        return LOOPBACK, f"bind host {LOOPBACK}: Docker bridge gateway {gateway} is not a unicast host address"
    error = local_address_error(str(gateway))
    if error is not None:
        return LOOPBACK, (
            f"bind host {LOOPBACK}: Docker bridge gateway {gateway} is not an address of this host ({error}), "
            "as with Docker Desktop"
        )
    return str(gateway), f"bind host {gateway}: Docker bridge gateway, an address of this host"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read 'docker network inspect bridge' JSON on stdin and print the CI bees server bind address."
    )
    parser.parse_args(argv)

    host, reason = choose_bind_host(bridge_gateways(sys.stdin.read()))
    print(reason, file=sys.stderr)
    print(host)
    return 0


if __name__ == "__main__":
    sys.exit(main())
