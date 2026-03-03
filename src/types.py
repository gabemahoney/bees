"""Shared type definitions."""

from __future__ import annotations

from typing import Literal

# TicketType supports:
# - "bee": Top-level ticket type
# - str: Dynamic tier types (t1, t2, t3, etc.) based on child_tiers config
TicketType = Literal["bee"] | str
