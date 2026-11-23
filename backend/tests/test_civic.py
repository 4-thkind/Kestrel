"""Civic issues: fusion, community verification, severity, lifecycle, officer
workflow, scorecards, route hazards, seed data. stdlib only, injected clock."""
from __future__ import annotations

import base64
import sys
import unittest
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from test_scenarios import ADMIN, CORRIDOR, PAIR, make, who  # noqa: E402

from domain import routes as route_domain  # noqa: E402
from domain.categories import CATEGORIES  # noqa: E402
from domain.extract import detect_category, detect_details  # noqa: E402
from domain.policy import iso  # noqa: E402
from domain.validation import ApiError  # noqa: E402
from seed import ISSUES, seed_demo  # noqa: E402
from service import Principal  # noqa: E402

LAJPAT = (28.5677, 77.2433)          # inside sample ward W-LN
M_PER_DEG = 111_320
JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 200).decode()


def officer(ward: str = "W-LN") -> Principal:
    return Principal("officer", f"demo-officer-{ward}", [ward])


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.svc, self.clock = make()
        self.civic = self.svc.civic

    def body(self, category="POTHOLE", north_m=0.0, minutes_ago=0.0, event_id=None, **extra) -> dict:
        return {"schemaVersion": "1.0", "eventId": event_id or str(uuid.uuid4()), "category": category,
                "observedAt": iso(self.clock() - timedelta(minutes=minutes_ago)),
                "location": {"lat": LAJPAT[0] + north_m / M_PER_DEG, "lon": LAJPAT[1]},
                "clientMode": self.svc.cfg.client_mode, **extra}

    def report(self, name: str, **kw) -> tuple[int, dict]:
        return self.civic.report(self.body(**kw), who(name))

    def vote(self, issue_id: str, name: str, kind: str) -> tuple[int, dict]:
        return self.civic.vote(issue_id, {"schemaVersion": "1.0", "eventId": str(uuid.uuid4()), "kind": kind,
                                          "observedAt": iso(self.clock()), "clientMode": self.svc.cfg.client_mode},
                               who(name))

    def act(self, issue_id: str, action: str, principal=None, **extra) -> dict:
        rev = self.civic.issue(issue_id)["revision"]
        return self.civic.transition(issue_id, {"action": action, "inspectedRevision": rev, **extra},
                                     principal or officer())

    def to_resolved(self, issue_id: str) -> None:
        self.act(issue_id, "ASSIGN", assignee="Road maintenance division")
        self.act(issue_id, "START")
        self.act(issue_id, "RESOLVE", note="Patched and rolled.")


class Fusion(Base):
    def test_nearby_same_category_joins_one_issue(self):
        s1, r1 = self.report("a")
        s2, r2 = self.report("b", north_m=12)
        self.assertEqual((s1, s2), (201, 200))
        self.assertEqual(r1["issueId"], r2["issueId"])
        self.assertTrue(r2["joined"])
        self.assertEqual((r2["reports"], r2["sources"], r2["evidenceState"]), (2, 2, "CORROBORATED"))
        self.assertEqual(r2["workflowState"], "VERIFIED")

    def test_far_or_other_category_stays_separate(self):
        _, a = self.report("a")
        _, far = self.report("b", north_m=60)                       # beyond the 25 m pothole radius
        _, other = self.report("c", category="GARBAGE_DUMP")
        self.assertEqual(len({a["issueId"], far["issueId"], other["issueId"]}), 3)

    def test_category_radius_differs(self):
        _, a = self.report("a", category="WATERLOGGING")
        _, b = self.report("b", category="WATERLOGGING", north_m=50)  # inside 60 m
        self.assertEqual(a["issueId"], b["issueId"])

    def test_same_source_counts_once(self):
        self.report("a")
        _, r = self.report("a", north_m=5)
        self.assertEqual((r["reports"], r["sources"], r["evidenceState"]), (2, 1, "REPORTED"))

    def test_centre_is_mean_of_distinct_sources(self):
        self.report("a")
        _, r = self.report("b", north_m=20)
        lat = self.civic.issue(r["issueId"])["lat"]
        self.assertAlmostEqual(lat, LAJPAT[0] + 10 / M_PER_DEG, places=5)

    def test_picked_issue_is_joined_or_refused(self):
        _, a = self.report("a")
        _, b = self.report("b", north_m=40, issueId=a["issueId"])   # within 2x radius when picked by hand
        self.assertEqual(b["issueId"], a["issueId"])
        with self.assertRaises(ApiError) as e:
            self.report("c", category="GARBAGE_DUMP", issueId=a["issueId"])
        self.assertEqual(e.exception.code, "CANNOT_JOIN_ISSUE")

    def test_retry_is_not_a_witness_and_reuse_is_409(self):
        body = self.body()
        s1, r1 = self.civic.report(body, who("a"))
        s2, r2 = self.civic.report(body, who("a"))
        self.assertEqual((s1, s2, r2["duplicate"], r2["issueId"]), (201, 200, True, r1["issueId"]))
        self.assertEqual(self.civic.issue(r1["issueId"])["reports"], 1)
        with self.assertRaises(ApiError) as e:
            self.civic.report({**body, "description": "changed"}, who("a"))
        self.assertEqual(e.exception.status, 409)

    def test_validation(self):
        cases = [({"category": "UFO"}, "UNSUPPORTED_CATEGORY"),
                 ({"verified": True}, "UNKNOWN_FIELDS"),
                 ({"location": {"lat": 19.07, "lon": 72.87}}, "OUTSIDE_COVERAGE"),
                 ({"details": ["very_bad"]}, "INVALID_DETAILS"),
                 ({"photo": {"contentType": "image/jpeg", "data": base64.b64encode(b"GIF89a").decode()}}, "INVALID_PHOTO")]
        for extra, code in cases:
            with self.subTest(code=code), self.assertRaises(ApiError) as e:
                self.civic.report({**self.body(), **extra}, who("a"))
            self.assertEqual(e.exception.code, code)
        with self.assertRaises(ApiError) as e:
            self.civic.report(self.body(), Principal())
        self.assertEqual(e.exception.status, 401)

    def test_photo_is_stored_and_served_in_demo(self):
        _, r = self.report("a", photo={"contentType": "image/jpeg", "data": JPEG})
        detail = self.civic.issue(r["issueId"])
        url = detail["observations"][0]["photoUrl"]
        self.assertEqual(detail["photos"], 1)
        self.assertEqual(self.civic.photo(url.rsplit("/", 1)[1])["data"], JPEG)


class Severity(Base):
    def test_parts_add_up_and_cap(self):
        names = "abcdef"
        for i, n in enumerate(names):
            r = self.report(n, details=["deep", "major_road"] if i == 0 else [],
                            photo={"contentType": "image/jpeg", "data": JPEG} if i == 1 else None)[1]
        sev = self.civic.issue(r["issueId"])["severity"]
        self.assertEqual({p["code"]: p["points"] for p in sev["parts"]},
                         {"CATEGORY": 25, "DEEP": 10, "COMMUNITY": 30, "PHOTO": 5, "MAJOR_ROAD": 10})
        self.assertEqual((sev["score"], sev["priority"]), (80, "P1"))

    def test_single_report_is_low_priority(self):
        _, r = self.report("a", category="GARBAGE_DUMP")
        self.assertEqual((r["score"], r["priority"]), (15, "P3"))

    def test_overdue_adds_points(self):
        _, r = self.report("a", category="GARBAGE_DUMP")
        self.clock.advance(60 * 24 * 5)                           # SLA 3 days -> 2 days overdue
        self.report("a", category="GARBAGE_DUMP")                 # keep evidence fresh
        sev = self.civic.issue(r["issueId"])["severity"]
        self.assertIn({"code": "OVERDUE", "label": "2 days past deadline", "points": 2}, sev["parts"])


class Evidence(Base):
    def test_two_fixed_votes_close_before_the_city_acts(self):
        _, r = self.report("a")
        self.report("b")
        self.clock.advance(10)
        self.vote(r["issueId"], "c", "FIXED")
        self.assertEqual(self.civic.issue(r["issueId"])["evidenceState"], "CONFLICTED")
        _, v = self.vote(r["issueId"], "d", "FIXED")
        self.assertEqual((v["evidenceState"], v["workflowState"]), ("CLEAR_REPORTED", "CLOSED"))
        self.assertEqual(self.civic.scorecard("W-LN")["closedByCitizensOnly"], 1)

    def test_unchecked_issue_goes_stale_not_green(self):
        _, r = self.report("a", category="WATERLOGGING")
        self.clock.advance(45)                                     # past the 30 min freshness
        d = self.civic.issue(r["issueId"])
        self.assertEqual((d["evidenceState"], d["workflowState"]), ("STALE", "OPEN"))
        self.assertTrue(d["blocksRoute"], "stale water stays avoided")

    def test_votes_on_closed_issue_are_refused(self):
        _, r = self.report("a")
        self.act(r["issueId"], "REJECT", note="Private property")
        with self.assertRaises(ApiError) as e:
            self.vote(r["issueId"], "b", "STILL_THERE")
        self.assertEqual(e.exception.code, "ISSUE_CLOSED")


class Lifecycle(Base):
    def test_resolution_needs_citizen_confirmation(self):
        _, r = self.report("a")
        self.report("b")
        self.to_resolved(r["issueId"])
        self.assertEqual(self.civic.issue(r["issueId"])["workflowState"], "RESOLVED")
        self.clock.advance(60)
        self.vote(r["issueId"], "a", "FIXED")
        self.assertEqual(self.civic.issue(r["issueId"])["workflowState"], "RESOLVED", "one vote is not enough")
        _, v = self.vote(r["issueId"], "b", "FIXED")
        self.assertEqual(v["workflowState"], "CLOSED")
        card = self.civic.scorecard("W-LN")
        self.assertEqual((card["citizenConfirmedFixes"], card["confirmedFixRate"]), (1, 1.0))

    def test_deadline_clock_stops_when_resolved(self):
        _, r = self.report("a", category="GARBAGE_DUMP")
        self.clock.advance(60 * 24 * 2)
        self.to_resolved(r["issueId"])
        self.clock.advance(60 * 24 * 3)                               # past the 3-day deadline
        self.assertEqual(self.civic.issue(r["issueId"])["overdueDays"], 0)

    def test_still_there_reopens(self):
        _, r = self.report("a")
        self.to_resolved(r["issueId"])
        self.clock.advance(60)
        self.vote(r["issueId"], "a", "STILL_THERE")
        _, v = self.vote(r["issueId"], "c", "STILL_THERE")
        self.assertEqual(v["workflowState"], "REOPENED")
        self.assertEqual(self.civic.issue(r["issueId"])["workflow"]["reopenCount"], 1)
        self.act(r["issueId"], "ASSIGN", assignee="Second crew")        # can be re-assigned

    def test_silence_is_closed_unconfirmed(self):
        _, r = self.report("a")
        self.to_resolved(r["issueId"])
        self.clock.advance(60 * 24 * 8)
        d = self.civic.issue(r["issueId"])
        self.assertEqual(d["workflowState"], "CLOSED_UNCONFIRMED")
        self.assertEqual(d["timeline"][-1]["action"], "CLOSED_UNCONFIRMED")

    def test_illegal_actions_and_permissions(self):
        _, r = self.report("a")
        iid = r["issueId"]
        with self.assertRaises(ApiError) as e:
            self.act(iid, "RESOLVE", note="done")                        # not assigned yet
        self.assertEqual(e.exception.code, "ACTION_NOT_ALLOWED_IN_STATE")
        with self.assertRaises(ApiError) as e:
            self.act(iid, "ASSIGN", principal=officer("W-KB"), assignee="x team")
        self.assertEqual(e.exception.status, 403)
        with self.assertRaises(ApiError) as e:
            self.act(iid, "ASSIGN", principal=who("a"), assignee="x team")
        self.assertEqual(e.exception.status, 403)
        with self.assertRaises(ApiError) as e:
            self.act(iid, "REJECT")                                      # needs a public note
        self.assertEqual(e.exception.code, "NOTE_REQUIRED")
        self.act(iid, "ASSIGN", principal=ADMIN, assignee="Road maintenance division")

    def test_stale_revision_is_rejected(self):
        _, r = self.report("a")
        rev = self.civic.issue(r["issueId"])["revision"]
        self.report("b")                                                  # new evidence arrives
        with self.assertRaises(ApiError) as e:
            self.civic.transition(r["issueId"], {"action": "ASSIGN", "assignee": "Team A",
                                                 "inspectedRevision": rev}, officer())
        self.assertEqual(e.exception.code, "STALE_REVISION")

    def test_merge_moves_reports(self):
        _, a = self.report("a")
        _, b = self.report("b", north_m=40)                               # separate issue, same pothole
        self.act(b["issueId"], "MERGE", targetIssueId=a["issueId"])
        target = self.civic.issue(a["issueId"])
        self.assertEqual((target["reports"], target["sources"]), (2, 2))
        self.assertEqual(self.civic.issue(b["issueId"])["workflow"]["mergedInto"], a["issueId"])

    def test_timeline_is_public_and_pseudonymous(self):
        _, r = self.report("a", description="Bada gaddha")
        self.report("b")
        self.act(r["issueId"], "ASSIGN", assignee="Road maintenance division")
        tl = self.civic.issue(r["issueId"])["timeline"]
        self.assertEqual([e["action"] for e in tl], ["REPORTED", "JOINED", "VERIFIED", "ASSIGN"])
        self.assertEqual([e["source"] for e in tl[:2]], ["Source 1", "Source 2"])
        self.assertNotIn("demo-a", str(tl))


class Queue(Base):
    def test_queue_is_ward_scoped_and_priority_sorted(self):
        self.report("a", category="GARBAGE_DUMP")
        for n in "abc":
            self.report(n, category="OPEN_MANHOLE", north_m=200)
        q = self.civic.queue("W-LN", officer())
        self.assertEqual([i["category"] for i in q["issues"]], ["OPEN_MANHOLE", "GARBAGE_DUMP"])
        with self.assertRaises(ApiError):
            self.civic.queue("W-LN", officer("W-KB"))

    def test_near_query_lists_candidates_for_dedupe(self):
        self.report("a")
        found = self.civic.list_issues({"near": f"{LAJPAT[0] + 30 / M_PER_DEG},{LAJPAT[1]}"})["issues"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["distanceM"], 30)


class Routing(Base):
    def test_open_hazard_blocks_routes_through_it(self):
        # an open manhole reported on candidate A of the reviewed corridor
        corridor = self.svc.corridor
        pair = next(p for p in corridor["pairs"] if p["id"] == PAIR)
        a = next(c for c in pair["candidates"] if "MINTO" in c["id"] or c is pair["candidates"][0])
        lon, lat = a["geometry"]["coordinates"][len(a["geometry"]["coordinates"]) // 3]
        for n in "ab":
            self.civic.report({**self.body(category="OPEN_MANHOLE"), "location": {"lat": lat, "lon": lon}}, who(n))
        d = self.svc.compare({"corridorId": CORRIDOR, "routePairId": PAIR})
        self.assertNotEqual(d["selectedRouteId"], a["id"])
        self.assertEqual([i["category"] for i in d["avoidedIssues"]], ["OPEN_MANHOLE"])

    def test_minor_pothole_and_garbage_do_not_block(self):
        _, p = self.report("a")
        _, g = self.report("b", category="GARBAGE_DUMP")
        features, _, _ = self.civic.route_hazards(self.clock())
        self.assertEqual(features, [])

    def test_side_anchors_are_either_side(self):
        line = [[77.0, 28.6], [77.01, 28.6]]                               # east-west road
        left, right = route_domain.side_anchors(line, [77.005, 28.6])
        self.assertGreater(left[1], 28.6)
        self.assertLess(right[1], 28.6)


class Drafts(unittest.TestCase):
    def test_hinglish_categories(self):
        cases = {"flyover ke neeche bada gaddha hai, bahut gehra": ("POTHOLE", ["deep", "major_road"]),
                 "gali mein kooda dher pada hai": ("GARBAGE_DUMP", []),
                 "light nahi jal rahi raat ko andhera": ("STREETLIGHT_OUT", ["night_hazard"]),
                 "manhole ka dhakkan gayab hai school ke paas": ("OPEN_MANHOLE", ["near_school"]),
                 "ped gira hai rasta band": ("BLOCKED_ROAD", []),
                 "कूड़े का ढेर लगा है": ("GARBAGE_DUMP", []),
                 "hello": (None, [])}
        for text, (cat, details) in cases.items():
            with self.subTest(text=text):
                self.assertEqual((detect_category(text), detect_details(text)), (cat, details))


class Seed(unittest.TestCase):
    def test_seed_covers_wards_and_states(self):
        svc, _ = make()
        self.assertEqual(seed_demo(svc), len(ISSUES))
        issues = svc.civic.list_issues({"status": "all"})["issues"]
        self.assertEqual({i["wardId"] for i in issues}, {w["id"] for w in svc.civic.wards})
        states = {i["workflowState"] for i in issues}
        self.assertTrue({"VERIFIED", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED", "REOPENED",
                         "CLOSED_UNCONFIRMED", "REJECTED"} <= states, states)
        self.assertTrue(all(i["provenance"] == "SYNTHETIC_DEMO" for i in issues))
        self.assertTrue({i["category"] for i in issues} >= set(CATEGORIES))

    def test_seed_refused_outside_demo(self):
        svc, _ = make("live-pilot")
        with self.assertRaises(RuntimeError):
            seed_demo(svc)


if __name__ == "__main__":
    unittest.main()
