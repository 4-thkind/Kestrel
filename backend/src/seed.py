"""Synthetic demo data: realistic civic issues across eight sample Delhi wards.

Every issue is built with the same evidence, fusion and lifecycle code real
reports use, at times in the past, and stored with provenance SYNTHETIC_DEMO.
Places are real localities and roads; pins are approximate (sample data).
"""
from __future__ import annotations

import math
import random
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from domain import fusion
from domain.policy import iso

if TYPE_CHECKING:
    from service import Service

SAY = {
    "POTHOLE": ["Bada gaddha hai, bike wale gir rahe hain", "Deep pothole in the left lane",
                "Gaddha hai, raat ko dikhta nahi", "Road toota hua hai, scooter ka tyre phat gaya",
                "Pothole growing every week near the turn"],
    "WATERLOGGING": ["Ghutne tak paani bhara hai", "Water on the road after rain, autos stuck",
                     "Underpass mein paani bhar gaya"],
    "OPEN_MANHOLE": ["Manhole ka dhakkan gayab hai", "Open manhole on footpath, very dangerous",
                     "Gutter khula pada hai, bachche yahan se jaate hain"],
    "BLOCKED_ROAD": ["Ped gira hai, aadha rasta band", "Construction malba road par pada hai",
                     "Barricade lagi hai bina diversion ke"],
    "GARBAGE_DUMP": ["Kooda 4 din se nahi utha", "Overflowing dhalao, smell is terrible",
                     "Kachra road par phaila hai, kutte faila rahe hain", "Garbage dumped next to the park wall"],
    "STREETLIGHT_OUT": ["Street light 1 hafte se band hai", "Poori gali mein andhera hai raat ko",
                        "Three poles dark, women avoid this stretch at night"],
    "OTHER": ["Footpath tiles tooti hui hain", "Broken divider railing"],
}

#: (ward, category, place, sources, first report days ago, flow, details)
ISSUES = [
    ("W-CP", "POTHOLE", "Barakhamba Road near Statesman House", 9, 11, "assigned", ["deep", "major_road"]),
    ("W-CP", "STREETLIGHT_OUT", "Janpath, near Palika Bazaar gate 3", 4, 6, "progress", []),
    ("W-CP", "GARBAGE_DUMP", "Panchkuian Road service lane", 3, 4, "confirmed", []),
    ("W-CP", "OPEN_MANHOLE", "Outer Circle, Block N footpath", 6, 2, "open", ["major_road"]),
    ("W-CP", "BLOCKED_ROAD", "Baba Kharak Singh Marg", 2, 0.04, "open", ["major_road"]),
    ("W-KB", "POTHOLE", "Ajmal Khan Road, near Gaffar Market", 12, 19, "reopened", ["deep", "major_road"]),
    ("W-KB", "GARBAGE_DUMP", "Arya Samaj Road dhalao", 7, 9, "open", []),
    ("W-KB", "STREETLIGHT_OUT", "Beadonpura lane 7", 2, 13, "unconfirmed", ["night_hazard"]),
    ("W-KB", "POTHOLE", "Pusa Road near Rajendra Place metro", 5, 5, "verified", ["major_road"]),
    ("W-KB", "OTHER", "Guru Ravidas Marg footpath", 1, 3, "rejected", []),
    ("W-CC", "GARBAGE_DUMP", "Nai Sarak, near the book market", 10, 8, "progress", []),
    ("W-CC", "OPEN_MANHOLE", "Esplanade Road, opposite the parking", 4, 3, "assigned", []),
    ("W-CC", "POTHOLE", "Chandni Chowk main road near Fatehpuri", 6, 15, "confirmed", ["deep"]),
    ("W-CC", "BLOCKED_ROAD", "Kinari Bazaar entrance", 3, 0.06, "open", []),
    ("W-LN", "POTHOLE", "Ring Road near Moolchand flyover ramp", 14, 9, "assigned", ["deep", "major_road"]),
    ("W-LN", "WATERLOGGING", "Ring Road underpass near Lajpat Nagar", 3, 0.01, "open", ["major_road", "vehicles_stuck"]),
    ("W-LN", "GARBAGE_DUMP", "Central Market back lane", 5, 6, "open", []),
    ("W-LN", "STREETLIGHT_OUT", "Amar Colony main road", 3, 10, "resolved", ["night_hazard"]),
    ("W-LN", "OPEN_MANHOLE", "Lajpat Nagar 4, near the school gate", 5, 1, "open", ["near_school"]),
    ("W-MV", "POTHOLE", "NH-24 service road near Akshardham", 8, 21, "progress", ["major_road", "deep"]),
    ("W-MV", "GARBAGE_DUMP", "Pocket 2 park boundary", 4, 12, "confirmed", []),
    ("W-MV", "STREETLIGHT_OUT", "Chilla Village road", 6, 8, "open", ["night_hazard"]),
    ("W-MV", "POTHOLE", "Samachar Apartments road", 2, 4, "open", []),
    ("W-MV", "WATERLOGGING", "Mayur Vihar Phase 1 metro underpass", 2, 0.02, "open", []),
    ("W-RH", "POTHOLE", "Outer Ring Road near Rohini East metro", 11, 14, "assigned", ["deep", "major_road"]),
    ("W-RH", "GARBAGE_DUMP", "Sector 7 market road", 6, 7, "open", []),
    ("W-RH", "OPEN_MANHOLE", "Sector 8 DDA park road", 3, 2, "progress", []),
    ("W-RH", "STREETLIGHT_OUT", "Sector 7 pocket D", 1, 2, "open", []),
    ("W-RH", "POTHOLE", "Sector 9 main road", 3, 25, "unconfirmed", []),
    ("W-DW", "POTHOLE", "Sector 10 metro station road", 7, 10, "verified", ["major_road"]),
    ("W-DW", "GARBAGE_DUMP", "Sector 11 market service lane", 3, 5, "resolved", []),
    ("W-DW", "STREETLIGHT_OUT", "Palam-Dabri road stretch", 5, 16, "reopened", ["night_hazard", "major_road"]),
    ("W-DW", "BLOCKED_ROAD", "Sector 12 road, fallen neem tree", 4, 0.05, "open", []),
    ("W-DW", "OTHER", "Sector 10 park railing", 2, 9, "confirmed", []),
    ("W-SK", "POTHOLE", "Press Enclave Marg near Saket metro", 10, 12, "progress", ["deep", "major_road"]),
    ("W-SK", "OPEN_MANHOLE", "MB Road, near Max hospital", 6, 1, "assigned", ["near_hospital", "major_road"]),
    ("W-SK", "GARBAGE_DUMP", "Sheikh Sarai crossing", 4, 6, "open", []),
    ("W-SK", "STREETLIGHT_OUT", "Saket J Block lane", 2, 7, "confirmed", []),
    ("W-SK", "POTHOLE", "District Centre service road", 1, 1, "open", []),
]

TEAMS = {
    "POTHOLE": "Road maintenance division", "WATERLOGGING": "Drainage team", "OPEN_MANHOLE": "Sewer maintenance team",
    "BLOCKED_ROAD": "Horticulture and malba removal team", "GARBAGE_DUMP": "Sanitation team",
    "STREETLIGHT_OUT": "Electrical maintenance team", "OTHER": "Ward civil team",
}


def _offset(lon: float, lat: float, rng: random.Random, max_m: float) -> tuple[float, float]:
    d, a = max_m * math.sqrt(rng.random()), rng.uniform(0, 2 * math.pi)
    return (round(lon + d * math.cos(a) / (111_320 * math.cos(math.radians(lat))), 6),
            round(lat + d * math.sin(a) / 111_320, 6))


def seed_demo(svc: "Service", seed: int = 42) -> int:
    """Write the sample issues into the demo namespace. Returns how many were written."""
    if not svc.cfg.is_demo:
        raise RuntimeError("seed data is for demo namespaces only")
    civic, rng, now = svc.civic, random.Random(seed), svc.now()
    wards = {w["id"]: w for w in civic.wards}
    person = 0

    def source() -> str:
        nonlocal person
        person += 1
        return svc._source_key(f"demo-seed-{person}", now)

    def obs(issue: dict, kind: str, at: datetime, src: str, lat: float, lon: float, details: list[str]) -> None:
        cat = issue["category"]
        issue["observations"].append({
            "eventId": str(uuid.UUID(int=rng.getrandbits(128))), "sourceKey": src, "kind": kind,
            "observedAt": iso(at), "receivedAt": iso(at), "lat": lat, "lon": lon,
            "description": rng.choice(SAY[cat]) if kind == "REPORT" else None,
            "details": details if kind == "REPORT" else [], "photoId": None})
        action = kind if kind != "REPORT" else ("REPORTED" if len(issue["observations"]) == 1 else "JOINED")
        issue["timeline"].append({"at": iso(at), "actor": "citizen", "source": src, "action": action})

    def officer(issue: dict, action: str, at: datetime, note: str | None = None) -> None:
        wf = issue["workflow"]
        wf["state"] = {"ASSIGN": "ASSIGNED", "START": "IN_PROGRESS", "RESOLVE": "RESOLVED", "REJECT": "REJECTED"}[action]
        wf["since"] = iso(at)
        if action == "ASSIGN":
            wf["assignee"] = TEAMS[issue["category"]]
            note = f"Assigned to {wf['assignee']}"
        if action == "RESOLVE":
            wf["resolvedAt"], wf["everResolved"] = iso(at), True
        if action == "REJECT":
            wf["rejectReason"] = note
        issue["timeline"].append({"at": iso(at), "actor": "officer", "action": action, "note": note})

    written = 0
    for ward_id, cat, place, sources, age_days, flow, details in ISSUES:
        ward = wards[ward_id]
        lon, lat = _offset(*ward["centre"], rng, ward["radiusM"] * 0.6)
        first = now - timedelta(days=age_days)
        issue = civic._new_issue(cat, lat, lon, place, iso(first), iso(first))
        issue["wardId"] = ward_id
        issue["provenance"] = "SYNTHETIC_DEMO"
        reporters = [source() for _ in range(sources)]
        span = max(timedelta(minutes=5), (now - first) * 0.5)
        for i, src in enumerate(reporters):
            at = first + span * (i / max(1, sources - 1)) if i else first
            plon, plat = _offset(lon, lat, rng, 8)
            obs(issue, "REPORT", at, src, plat, plon, details if i < 2 else [])
        fusion.recentre(issue)
        civic._advance(issue, first + span)

        t = first + span
        if flow in ("assigned", "progress", "resolved", "confirmed", "reopened", "unconfirmed"):
            officer(issue, "ASSIGN", t + timedelta(hours=6))
        if flow in ("progress", "resolved", "confirmed", "reopened", "unconfirmed"):
            officer(issue, "START", t + timedelta(hours=20))
        if flow in ("resolved", "confirmed", "reopened", "unconfirmed"):
            resolved = now - timedelta(days=8) if flow == "unconfirmed" else \
                min(now - timedelta(hours=3), t + timedelta(days=1))
            officer(issue, "RESOLVE", resolved, "Work completed by the field team.")
            if flow in ("confirmed", "reopened"):
                kind = "FIXED" if flow == "confirmed" else "STILL_THERE"
                for src in reporters[:1] + [source()]:
                    resolved += timedelta(hours=1)
                    obs(issue, kind, min(resolved, now - timedelta(minutes=30)), src, lat, lon, [])
        if flow == "rejected":
            officer(issue, "REJECT", t + timedelta(hours=4), "Private property inside a housing society; "
                                                              "referred to the RWA.")
        civic._advance(issue, now)
        issue["revision"] = 1
        issue["updatedAt"] = max(e["at"] for e in issue["timeline"])
        svc.store.commit_issue(svc.cfg.namespace, issue, 0)
        written += 1
    return written
