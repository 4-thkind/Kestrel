"""Evidence state for one civic issue, from citizens' reports and votes.

Same principles as the original water policy, applied per category:
each source counts once (its latest fresh decisive observation), freshness
comes from `observedAt`, and an issue nobody re-checked never turns green
on its own. Only distinct sources saying "fixed" can clear it.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from domain.categories import Category
from domain.policy import iso, parse_iso

POSITIVE = frozenset({"REPORT", "STILL_THERE"})
NEGATIVE = frozenset({"FIXED"})
KINDS = POSITIVE | NEGATIVE
FUTURE_TOLERANCE = timedelta(minutes=2)
#: Distinct sources needed to clear an issue (and to confirm an officer's fix).
CLEAR_SOURCES = 2
#: States that still describe a problem on the ground.
ACTIVE = frozenset({"REPORTED", "CORROBORATED", "CONFLICTED", "STALE"})


def _at(o: dict) -> datetime:
    return parse_iso(o["observedAt"])


def latest_per_source(observations: list[dict], since: datetime | None, until: datetime) -> dict[str, dict]:
    """sourceKey -> that source's latest decisive observation in (since, until]."""
    latest: dict[str, dict] = {}
    for o in sorted(observations, key=_at):
        if o["kind"] not in KINDS or _at(o) > until or (since is not None and _at(o) <= since):
            continue
        latest[o["sourceKey"]] = o
    return latest


def evaluate_issue(observations: list[dict], now: datetime, cat: Category) -> dict:
    horizon = now + FUTURE_TOLERANCE
    usable = [o for o in observations if _at(o) <= horizon]
    latest = latest_per_source(usable, now - cat.freshness, horizon)
    pos = [o for o in latest.values() if o["kind"] in POSITIVE]
    neg = [o for o in latest.values() if o["kind"] in NEGATIVE]
    ever_positive = any(o["kind"] in POSITIVE for o in usable)

    if len(neg) >= CLEAR_SOURCES and (not pos or min(map(_at, neg)) > max(map(_at, pos))):
        state, reason = "CLEAR_REPORTED", "DISTINCT_SOURCES_REPORT_FIXED"
    elif pos and any(_at(n) > min(map(_at, pos)) for n in neg):
        state, reason = "CONFLICTED", "FIXED_VOTE_AFTER_REPORT"
    elif len(pos) >= 2:
        state, reason = "CORROBORATED", "DISTINCT_SOURCES_AGREE"
    elif pos:
        state, reason = "REPORTED", "SINGLE_FRESH_REPORT"
    elif ever_positive:
        # absence of fresh reports is not evidence of a fix
        state, reason = "STALE", "NOT_RECHECKED_RECENTLY"
    else:
        state, reason = "UNKNOWN", "NO_REPORTS"

    last_pos = max((_at(o) for o in usable if o["kind"] in POSITIVE), default=None)
    return {
        "state": state,
        "reasonCode": reason,
        "active": state in ACTIVE,
        "positiveSources": len(pos),
        "negativeSources": len(neg),
        "totalSources": len({o["sourceKey"] for o in usable}),
        "totalReports": sum(1 for o in usable if o["kind"] == "REPORT"),
        "photos": sum(1 for o in usable if o.get("photoId")),
        "lastPositiveAt": iso(last_pos) if last_pos else None,
        "latestAt": iso(max(map(_at, usable))) if usable else None,
    }
