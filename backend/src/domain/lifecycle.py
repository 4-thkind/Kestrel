"""Workflow lifecycle of an issue: what the city is doing about it.

Officers move it forward. Citizens close it: an officer's RESOLVED only becomes
CLOSED when distinct citizens confirm the fix, and "still there" reopens it.
Silence is shown as CLOSED_UNCONFIRMED, never as confirmation.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from domain.evidence import CLEAR_SOURCES, NEGATIVE, POSITIVE, latest_per_source
from domain.policy import iso, parse_iso

STATES = ("OPEN", "VERIFIED", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "REOPENED",
          "CLOSED", "CLOSED_UNCONFIRMED", "REJECTED", "MERGED")
TERMINAL = frozenset({"CLOSED", "CLOSED_UNCONFIRMED", "REJECTED", "MERGED"})
OPEN_STATES = frozenset(STATES) - TERMINAL
CONFIRM_WINDOW = timedelta(days=7)

#: action -> (states it may start from, resulting state)
ACTIONS: dict[str, tuple[frozenset, str]] = {
    "ASSIGN": (frozenset({"OPEN", "VERIFIED", "REOPENED", "ASSIGNED"}), "ASSIGNED"),
    "START": (frozenset({"ASSIGNED"}), "IN_PROGRESS"),
    "RESOLVE": (frozenset({"ASSIGNED", "IN_PROGRESS"}), "RESOLVED"),
    "REJECT": (frozenset({"OPEN", "VERIFIED", "REOPENED", "ASSIGNED"}), "REJECTED"),
    "MERGE": (frozenset({"OPEN", "VERIFIED", "REOPENED"}), "MERGED"),
}


def next_state(current: str, action: str) -> str:
    if action not in ACTIONS:
        raise ValueError("UNSUPPORTED_ACTION")
    allowed, result = ACTIONS[action]
    if current not in allowed:
        raise ValueError("ACTION_NOT_ALLOWED_IN_STATE")
    return result


def auto_transition(workflow: dict, evidence: dict, observations: list[dict], now: datetime) -> tuple[str, str, str] | None:
    """(new state, reason code, at) the community or the clock moves the issue to, or None."""
    state = workflow["state"]
    if state == "RESOLVED":
        resolved = parse_iso(workflow["resolvedAt"])
        after = latest_per_source(observations, resolved, now + timedelta(minutes=2)).values()
        fixed = [o for o in after if o["kind"] in NEGATIVE]
        still = [o for o in after if o["kind"] in POSITIVE]
        if len(still) >= CLEAR_SOURCES:
            return "REOPENED", "CITIZENS_REPORT_STILL_THERE", max(o["observedAt"] for o in still)
        if len(fixed) >= CLEAR_SOURCES:
            return "CLOSED", "CITIZEN_CONFIRMED_FIX", max(o["observedAt"] for o in fixed)
        if now >= resolved + CONFIRM_WINDOW:
            return "CLOSED_UNCONFIRMED", "NO_CONFIRMATION_IN_7_DAYS", iso(resolved + CONFIRM_WINDOW)
        return None
    if state in TERMINAL:
        return None
    if evidence["state"] == "CLEAR_REPORTED":
        return "CLOSED", "CITIZENS_REPORT_FIXED", evidence["latestAt"]
    if state == "OPEN" and evidence["state"] == "CORROBORATED":
        return "VERIFIED", "COMMUNITY_CORROBORATED", evidence["latestAt"]
    return None
