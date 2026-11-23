"""Severity: a transparent sum of named parts, capped at 100. The issue page
shows every part, so an officer or a citizen can see why something is P1."""
from __future__ import annotations

from domain.categories import Category

COMMUNITY_PER_SOURCE, COMMUNITY_MAX = 8, 30
OVERDUE_MAX = 15


def score(cat: Category, evidence: dict, details: set[str], overdue_days: int) -> dict:
    parts = [{"code": "CATEGORY", "label": f"{cat.label} base", "points": cat.base}]
    if cat.key == "POTHOLE" and "deep" in details:
        parts.append({"code": "DEEP", "label": "Reported deep", "points": 10})
    confirming = max(0, evidence["positiveSources"] - 1)
    if confirming:
        parts.append({"code": "COMMUNITY", "label": f"{confirming} more people confirm",
                      "points": min(COMMUNITY_MAX, COMMUNITY_PER_SOURCE * confirming)})
    if evidence["photos"]:
        parts.append({"code": "PHOTO", "label": "Photo evidence", "points": 5})
    if "major_road" in details:
        parts.append({"code": "MAJOR_ROAD", "label": "On a major road", "points": 10})
    if details & {"near_school", "near_hospital"}:
        parts.append({"code": "SENSITIVE_SITE", "label": "Near a school or hospital", "points": 10})
    if overdue_days > 0:
        parts.append({"code": "OVERDUE", "label": f"{overdue_days} days past deadline",
                      "points": min(OVERDUE_MAX, overdue_days)})
    total = min(100, sum(p["points"] for p in parts))
    return {"score": total, "priority": "P1" if total >= 70 else "P2" if total >= 40 else "P3", "parts": parts}
