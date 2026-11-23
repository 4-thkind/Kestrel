"""Duplicate fusion: a new report joins the nearest open issue of the same
category inside that category's radius, or starts a new issue."""
from __future__ import annotations

from domain.categories import CATEGORIES
from domain.geometry import distance_m

#: A citizen who explicitly picks an existing issue may be this many radii away (GPS drift).
PICK_TOLERANCE = 2.0


def distance(issue: dict, lat: float, lon: float) -> float:
    return distance_m([issue["lon"], issue["lat"]], [lon, lat])


def find_match(issues: list[dict], category: str, lat: float, lon: float, open_states: frozenset) -> dict | None:
    """Nearest open same-category issue within the category radius."""
    radius = CATEGORIES[category].radius_m
    near = [(distance(i, lat, lon), i) for i in issues
            if i["category"] == category and i["workflow"]["state"] in open_states]
    near = [(d, i) for d, i in near if d <= radius]
    return min(near, key=lambda t: t[0])[1] if near else None


def can_join(issue: dict, category: str, lat: float, lon: float, open_states: frozenset) -> bool:
    """Whether a report the citizen attached to `issue` by hand may join it."""
    return (issue["category"] == category and issue["workflow"]["state"] in open_states
            and distance(issue, lat, lon) <= CATEGORIES[category].radius_m * PICK_TOLERANCE)


def recentre(issue: dict) -> None:
    """Centre = mean of each distinct source's latest located report, so one phone
    reporting many times cannot drag the pin."""
    points: dict[str, tuple[float, float]] = {}
    for o in sorted(issue["observations"], key=lambda o: o["observedAt"]):
        if o["kind"] == "REPORT" and o.get("lat") is not None:
            points[o["sourceKey"]] = (o["lat"], o["lon"])
    if points:
        issue["lat"] = round(sum(p[0] for p in points.values()) / len(points), 6)
        issue["lon"] = round(sum(p[1] for p in points.values()) / len(points), 6)
