"""Issue categories for `civic-policy-v1`.

Every number is pilot configuration, not an engineering standard. Each category
decides how close two reports must be to count as one issue, how long a report
stays fresh, its severity base, whether it changes routes, and its fix deadline.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

POLICY_VERSION = "civic-policy-v1"


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    label_hi: str
    radius_m: float          # fusion radius: same-category reports closer than this are one issue
    freshness: timedelta     # a report counts as current evidence for this long
    base: int                # severity base points
    routing: str             # "block" (routes avoid it), "advisory" (mentioned only), "none"
    sla_days: int            # deadline for the owning agency, from first report
    owner: str               # likely owning agency; real ownership depends on the road


CATEGORIES: dict[str, Category] = {c.key: c for c in (
    Category("POTHOLE", "Pothole", "गड्ढा", 25, timedelta(days=30), 25, "block", 7,
             "Road-owning agency (municipal corporation or public works department)"),
    Category("WATERLOGGING", "Waterlogging", "जलभराव", 60, timedelta(minutes=30), 35, "block", 1,
             "Drainage / public works department"),
    Category("OPEN_MANHOLE", "Open manhole", "खुला मैनहोल", 15, timedelta(days=7), 40, "block", 2,
             "Water and sewerage utility"),
    Category("BLOCKED_ROAD", "Blocked road", "रास्ता बंद", 40, timedelta(hours=2), 30, "block", 1,
             "Municipal corporation / traffic police"),
    Category("GARBAGE_DUMP", "Garbage dump", "कूड़े का ढेर", 40, timedelta(days=7), 15, "none", 3,
             "Municipal sanitation department"),
    Category("STREETLIGHT_OUT", "Streetlight out", "स्ट्रीटलाइट बंद", 20, timedelta(days=7), 20, "advisory", 3,
             "Road-owning agency / power distribution company"),
    Category("OTHER", "Other civic issue", "अन्य समस्या", 25, timedelta(days=7), 10, "none", 7,
             "Ward office triage"),
)}

#: Report detail flags a citizen may claim. Claims, not measurements.
DETAILS = frozenset({"deep", "wide", "near_school", "near_hospital", "major_road", "night_hazard", "vehicles_stuck"})


def category(key: str) -> Category:
    return CATEGORIES[key]
