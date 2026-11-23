"""Civic issues: reports, duplicate fusion, community votes, officer workflow,
ward queues and scorecards. Transport- and storage-independent like service.py.

Every write goes through one path (`_write`): validate, pseudonymise the source,
check idempotency and rate limits, apply the change, let the community/clock
rules move the workflow, and commit guarded by the issue revision.
"""
from __future__ import annotations

import base64
import binascii
import json
import math
import re
import statistics
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Callable

from domain import fusion, lifecycle, severity
from domain.categories import CATEGORIES, DETAILS, POLICY_VERSION
from domain.evidence import evaluate_issue
from domain.geometry import DELHI_BBOX, distance_m
from domain.policy import iso, parse_iso
from domain.validation import UUID_RE, ApiError, payload_hash
from storage.local import DuplicateEvent, RevisionConflict

if TYPE_CHECKING:
    from service import Principal, Service

MAX_PHOTO_BYTES = 300_000
MAX_TEXT = 1_000
MAX_AGE = timedelta(days=7)
FUTURE_TOLERANCE = timedelta(minutes=2)
MAX_EMBEDDED_OBSERVATIONS = 300
ISSUE_RE = re.compile(r"^KS-[0-9A-F]{6}$")
PHOTO_RE = re.compile(r"^PH-[0-9a-f]{16}$")
WARD_RE = re.compile(r"^W-[A-Z]{2}$")
VOTE_KINDS = ("STILL_THERE", "FIXED")
#: Waterlogging and open manholes stay avoided even when nobody re-checked them.
STALE_STILL_BLOCKS = frozenset({"WATERLOGGING", "OPEN_MANHOLE"})
TIMELINE_LABEL = {
    "REPORTED": "Reported", "JOINED": "Another report joined", "STILL_THERE": "Still there",
    "FIXED": "Reported fixed", "ASSIGN": "Assigned", "START": "Work started", "RESOLVE": "Marked resolved",
    "REJECT": "Rejected", "MERGE": "Merged as duplicate", "MERGED_IN": "Duplicate merged in",
    "VERIFIED": "Verified by the community", "CLOSED": "Closed", "REOPENED": "Reopened",
    "CLOSED_UNCONFIRMED": "Closed without citizen confirmation",
}


def _finite(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _bad(code: str, message: str) -> ApiError:
    return ApiError(422, code, message)


class Civic:
    def __init__(self, svc: "Service", wards: list[dict]) -> None:
        self.svc, self.store, self.wards = svc, svc.store, wards
        self.ward_ids = {w["id"] for w in wards}

    # ------------------------------------------------------------ helpers
    @property
    def ns(self) -> str:
        return self.svc.cfg.namespace

    def ward_for(self, lat: float, lon: float) -> str:
        best = min(((distance_m(w["centre"], [lon, lat]), w) for w in self.wards), key=lambda t: t[0], default=None)
        return best[1]["id"] if best and best[0] <= best[1]["radiusM"] else "UNMAPPED"

    def _ward(self, ward_id: str | None) -> dict:
        ward = next((w for w in self.wards if w["id"] == ward_id), None)
        if ward is None:
            raise ApiError(404, "UNKNOWN_WARD", "No such ward.")
        return ward

    def _load(self, issue_id: str) -> dict:
        if not isinstance(issue_id, str) or not ISSUE_RE.match(issue_id):
            raise ApiError(404, "UNKNOWN_ISSUE", "No such issue.")
        issue = self.store.get_issue(self.ns, issue_id)
        if issue is None:
            raise ApiError(404, "UNKNOWN_ISSUE", "No such issue.")
        return issue

    @staticmethod
    def _time(value: object, now: datetime) -> str:
        try:
            at = parse_iso(value) if isinstance(value, str) else None
        except ValueError:
            at = None
        if at is None:
            raise _bad("INVALID_TIME", "observedAt must be an ISO 8601 UTC timestamp.")
        if at > now + FUTURE_TOLERANCE:
            raise _bad("TIME_IN_FUTURE", "observedAt is later than the server clock allows.")
        if at < now - MAX_AGE:
            raise _bad("TIME_TOO_OLD", "observedAt is too old to accept.")
        return iso(at)

    @staticmethod
    def _photo(raw: object, now: datetime) -> dict | None:
        """{"contentType", "data": base64} -> stored photo record, or None."""
        if raw is None:
            return None
        if not isinstance(raw, dict) or set(raw) - {"contentType", "data"} or \
                raw.get("contentType") not in ("image/jpeg", "image/webp") or not isinstance(raw.get("data"), str):
            raise _bad("INVALID_PHOTO", "photo must be {contentType: image/jpeg|image/webp, data: base64}.")
        try:
            data = base64.b64decode(raw["data"], validate=True)
        except (binascii.Error, ValueError):
            raise _bad("INVALID_PHOTO", "photo data is not valid base64.") from None
        if len(data) > MAX_PHOTO_BYTES:
            raise _bad("PHOTO_TOO_LARGE", f"Photos up to {MAX_PHOTO_BYTES // 1000} KB. Resize before sending.")
        is_jpeg = data[:3] == b"\xff\xd8\xff"
        is_webp = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        if not (is_jpeg if raw["contentType"] == "image/jpeg" else is_webp):
            raise _bad("INVALID_PHOTO", "photo bytes do not match contentType.")
        return {"photoId": "PH-" + uuid.uuid4().hex[:16], "contentType": raw["contentType"],
                "data": raw["data"], "createdAt": iso(now)}

    def _location(self, raw: object, required: bool) -> tuple[float, float] | None:
        if raw is None and not required:
            return None
        if not isinstance(raw, dict) or set(raw) - {"lat", "lon", "accuracyM", "source"}:
            raise _bad("INVALID_LOCATION", "location needs lat and lon.")
        lat, lon = raw.get("lat"), raw.get("lon")
        if not (_finite(lat) and _finite(lon)):
            raise _bad("INVALID_LOCATION", "location needs finite lat and lon.")
        if not (DELHI_BBOX[0] <= lon <= DELHI_BBOX[2] and DELHI_BBOX[1] <= lat <= DELHI_BBOX[3]):
            raise _bad("OUTSIDE_COVERAGE", "Kestrel's pilot covers Delhi NCR only.")
        acc = raw.get("accuracyM")
        if acc is not None and (not _finite(acc) or acc < 0):
            raise _bad("INVALID_LOCATION", "accuracyM must be a non-negative number.")
        return round(lat, 6), round(lon, 6)

    def _common(self, body: object, allowed: set[str], now: datetime) -> dict:
        if not isinstance(body, dict):
            raise ApiError(400, "INVALID_JSON", "Request body must be a JSON object.")
        extra = set(body) - allowed
        if extra:
            raise _bad("UNKNOWN_FIELDS", "Unsupported fields: " + ", ".join(sorted(extra)))
        if body.get("schemaVersion") != "1.0":
            raise _bad("UNSUPPORTED_SCHEMA", "schemaVersion must be \"1.0\".")
        if not isinstance(body.get("eventId"), str) or not UUID_RE.match(body["eventId"]):
            raise _bad("INVALID_EVENT_ID", "eventId must be a lowercase UUID.")
        if body.get("clientMode") != self.svc.cfg.client_mode:
            raise ApiError(409, "MODE_MISMATCH", f"This server accepts {self.svc.cfg.client_mode} reports only.")
        description = body.get("description")
        if description is not None and (not isinstance(description, str) or len(description) > MAX_TEXT):
            raise _bad("INVALID_DESCRIPTION", f"description must be text up to {MAX_TEXT} characters.")
        details = body.get("details") or []
        if not isinstance(details, list) or len(details) > len(DETAILS) or not set(details) <= DETAILS:
            raise _bad("INVALID_DETAILS", "details must be a list of: " + ", ".join(sorted(DETAILS)))
        return {"eventId": body["eventId"], "observedAt": self._time(body.get("observedAt"), now),
                "description": description.strip() if description else None, "details": sorted(set(details))}

    # ------------------------------------------------------------ reading
    def view(self, issue: dict, now: datetime) -> dict:
        """Issue as of `now`: evidence, any clock-driven workflow step, severity, routing."""
        issue = json.loads(json.dumps(issue))
        cat = CATEGORIES[issue["category"]]
        self._advance(issue, now, persist=False)
        evidence = evaluate_issue(issue["observations"], now, cat)
        details = {d for o in issue["observations"] if o["kind"] != "FIXED" for d in o.get("details", [])}
        open_ = issue["workflow"]["state"] in lifecycle.OPEN_STATES
        # the deadline clock stops once the ward marks it resolved; citizens then confirm or reopen
        clock_runs = open_ and issue["workflow"]["state"] != "RESOLVED"
        overdue = max(0, (now - parse_iso(issue["dueAt"])).days) if clock_runs and now > parse_iso(issue["dueAt"]) else 0
        sev = severity.score(cat, evidence, details, overdue)
        blocks = (open_ and evidence["active"] and cat.routing == "block"
                  and (cat.key != "POTHOLE" or sev["priority"] == "P1")
                  and (evidence["state"] != "STALE" or cat.key in STALE_STILL_BLOCKS))
        return {**issue, "evidence": evidence, "severity": sev, "details": sorted(details),
                "overdueDays": overdue, "blocksRoute": blocks, "advisory": open_ and evidence["active"]
                and cat.routing == "advisory"}

    def _summary(self, v: dict) -> dict:
        cat = CATEGORIES[v["category"]]
        return {
            "issueId": v["issueId"], "category": v["category"], "label": cat.label, "labelHi": cat.label_hi,
            "place": v.get("place"), "lat": v["lat"], "lon": v["lon"], "wardId": v["wardId"],
            "evidenceState": v["evidence"]["state"], "workflowState": v["workflow"]["state"],
            "score": v["severity"]["score"], "priority": v["severity"]["priority"],
            "reports": v["evidence"]["totalReports"], "sources": v["evidence"]["totalSources"],
            "photos": v["evidence"]["photos"], "openedAt": v["openedAt"], "dueAt": v["dueAt"],
            "overdueDays": v["overdueDays"], "blocksRoute": v["blocksRoute"], "updatedAt": v["updatedAt"],
            "provenance": v["provenance"],
        }

    def _views(self, now: datetime) -> list[dict]:
        return [self.view(i, now) for i in self.store.list_issues(self.ns)]

    def list_issues(self, q: dict) -> dict:
        now = self.svc.now()
        views = self._views(now)
        status = q.get("status", "open")
        if status not in ("open", "closed", "all"):
            raise _bad("INVALID_STATUS", "status must be open, closed or all.")
        if status != "all":
            want_open = status == "open"
            views = [v for v in views if (v["workflow"]["state"] in lifecycle.OPEN_STATES) == want_open]
        if q.get("category"):
            if q["category"] not in CATEGORIES:
                raise _bad("UNSUPPORTED_CATEGORY", "Unknown category.")
            views = [v for v in views if v["category"] == q["category"]]
        if q.get("ward"):
            views = [v for v in views if v["wardId"] == q["ward"]]
        if q.get("bbox"):
            try:
                w, s, e, n = (float(x) for x in q["bbox"].split(","))
            except ValueError:
                raise _bad("INVALID_BBOX", "bbox is minLon,minLat,maxLon,maxLat.") from None
            views = [v for v in views if w <= v["lon"] <= e and s <= v["lat"] <= n]
        near = None
        if q.get("near"):
            try:
                lat, lon = (float(x) for x in q["near"].split(","))
            except ValueError:
                raise _bad("INVALID_NEAR", "near is lat,lon.") from None
            near = (lat, lon)
            # "Is it one of these?": same-category issues a citizen could be duplicating
            views = [v for v in views if fusion.distance(v, lat, lon)
                     <= CATEGORIES[v["category"]].radius_m * fusion.PICK_TOLERANCE * 2]
        items = [self._summary(v) for v in views]
        if near:
            for item in items:
                item["distanceM"] = round(distance_m([item["lon"], item["lat"]], [near[1], near[0]]))
            items.sort(key=lambda i: i["distanceM"])
        else:
            items.sort(key=lambda i: (-i["score"], i["openedAt"]))
        return {"generatedAt": iso(now), "policyVersion": POLICY_VERSION, "count": len(items),
                "issues": items[:500], "provenance": self.svc.cfg.provenance}

    def issue(self, issue_id: str) -> dict:
        now = self.svc.now()
        v = self.view(self._load(issue_id), now)
        labels: dict[str, str] = {}

        def label(key: str | None) -> str | None:
            return labels.setdefault(key, f"Source {len(labels) + 1}") if key else None

        cat = CATEGORIES[v["category"]]
        demo = self.svc.cfg.is_demo
        observations = [{
            "kind": o["kind"], "observedAt": o["observedAt"], "source": label(o["sourceKey"]),
            "details": o.get("details", []), "photoUrl": f"/v1/photos/{o['photoId']}" if o.get("photoId") else None,
            # free text may hold personal details; only synthetic demo text is shown publicly
            "description": o.get("description") if demo else None,
        } for o in sorted(v["observations"], key=lambda o: o["observedAt"])]
        timeline = [{**{k: e[k] for k in ("at", "actor", "action", "note") if k in e},
                     "label": TIMELINE_LABEL.get(e["action"], e["action"]), "source": label(e.get("source")),
                     "photoUrl": f"/v1/photos/{e['photoId']}" if e.get("photoId") else None}
                    for e in sorted(v["timeline"], key=lambda e: e["at"])]
        ward = next((w for w in self.wards if w["id"] == v["wardId"]), None)
        return {**self._summary(v), "revision": v["revision"], "categoryInfo": {
                    "label": cat.label, "labelHi": cat.label_hi, "owner": cat.owner, "slaDays": cat.sla_days,
                    "routing": cat.routing, "freshnessHours": round(cat.freshness.total_seconds() / 3600, 1),
                    "radiusM": cat.radius_m},
                "ward": ward and {k: ward[k] for k in ("id", "name", "nameHi", "agency")},
                "evidence": v["evidence"], "severity": v["severity"], "details": v["details"],
                "workflow": {k: v["workflow"].get(k) for k in ("state", "since", "assignee", "resolvedAt",
                                                                "rejectReason", "mergedInto", "reopenCount")},
                "observations": observations[-100:], "timeline": timeline, "policyVersion": POLICY_VERSION,
                "generatedAt": iso(now)}

    def photo(self, photo_id: str) -> dict:
        if not PHOTO_RE.match(photo_id or ""):
            raise ApiError(404, "UNKNOWN_PHOTO", "No such photo.")
        photo = self.store.get_photo(self.ns, photo_id)
        # shortcut: outside demo mode photos stay private until a review/blur pipeline exists
        if photo is None or not self.svc.cfg.is_demo:
            raise ApiError(404, "UNKNOWN_PHOTO", "No such photo.")
        return photo

    # ------------------------------------------------------------ writing
    def _advance(self, issue: dict, now: datetime, persist: bool = True) -> None:
        """Apply community / clock workflow steps (at most a few in a row)."""
        cat = CATEGORIES[issue["category"]]
        for _ in range(3):
            evidence = evaluate_issue(issue["observations"], now, cat)
            step = lifecycle.auto_transition(issue["workflow"], evidence, issue["observations"], now)
            if step is None:
                return
            state, reason, at = step
            wf = issue["workflow"]
            if state == "REOPENED":
                wf["reopenCount"] = wf.get("reopenCount", 0) + 1
                wf["resolvedAt"] = None
            if state == "CLOSED" and reason == "CITIZEN_CONFIRMED_FIX":
                wf["confirmedFix"] = True
            wf["state"], wf["since"] = state, at or iso(now)
            issue["timeline"].append({"at": at or iso(now), "actor": "system" if state == "CLOSED_UNCONFIRMED"
                                      else "community", "action": state, "note": reason})

    def _new_issue(self, category: str, lat: float, lon: float, place: str | None, now_iso: str,
                   observed_at: str) -> dict:
        cat = CATEGORIES[category]
        return {
            "issueId": "KS-" + uuid.uuid4().hex[:6].upper(), "category": category, "lat": lat, "lon": lon,
            "wardId": self.ward_for(lat, lon), "place": place, "createdAt": now_iso, "openedAt": observed_at,
            "dueAt": iso(parse_iso(observed_at) + timedelta(days=cat.sla_days)), "updatedAt": now_iso,
            "revision": 0, "workflow": {"state": "OPEN", "since": observed_at, "reopenCount": 0},
            "observations": [], "timeline": [], "provenance": self.svc.cfg.provenance,
        }

    def _write(self, principal: "Principal", body: object, digest_of: dict, mutate: Callable[[datetime, str], tuple[dict, int]],
               photo: dict | None) -> tuple[int, dict]:
        """Idempotent, rate-limited, revision-guarded write of one issue."""
        subject = self.svc._require_contributor(principal)
        now = self.svc.now()
        source = self.svc._source_key(subject, now)
        digest = payload_hash(digest_of)
        previous = self.store.get_idempotency(self.ns, source, digest_of["eventId"])
        if previous:
            return self.svc._replay(previous, digest)
        from service import RATE_PER_DAY, RATE_PER_MINUTE
        if self.store.count_recent(self.ns, source, iso(now - timedelta(minutes=1))) >= RATE_PER_MINUTE or \
                self.store.count_recent(self.ns, source, iso(now - timedelta(days=1))) >= RATE_PER_DAY:
            raise ApiError(429, "RATE_LIMITED", "Too many reports from this contributor. Try later.", True)
        for _ in range(3):
            issue, status = mutate(now, source)
            expected = issue["revision"]
            issue["revision"] += 1
            issue["updatedAt"] = iso(now)
            issue["observations"] = issue["observations"][-MAX_EMBEDDED_OBSERVATIONS:]
            self._advance(issue, now)
            v = self.view(issue, now)
            response = {"eventId": digest_of["eventId"], "duplicate": False, "issueId": issue["issueId"],
                        "joined": status == 200, "revision": issue["revision"], "receivedAt": iso(now),
                        "evidenceState": v["evidence"]["state"], "workflowState": v["workflow"]["state"],
                        "priority": v["severity"]["priority"], "score": v["severity"]["score"],
                        "reports": v["evidence"]["totalReports"], "sources": v["evidence"]["totalSources"],
                        "provenance": self.svc.cfg.provenance}
            idem = {"sourceKey": source, "eventId": digest_of["eventId"], "payloadHash": digest,
                    "createdAt": iso(now), "result": response, "status": status}
            try:
                self.store.commit_issue(self.ns, issue, expected, idempotency=idem, photo=photo)
                return status, response
            except DuplicateEvent:
                return self.svc._replay(self.store.get_idempotency(self.ns, source, digest_of["eventId"]), digest)
            except RevisionConflict:
                continue
        raise ApiError(409, "REVISION_CONFLICT", "The issue changed concurrently. Retry.", True)

    def report(self, body: object, principal: "Principal") -> tuple[int, dict]:
        now = self.svc.now()
        clean = self._common(body, {"schemaVersion", "eventId", "category", "observedAt", "location", "description",
                                    "details", "photo", "issueId", "place", "clientMode"}, now)
        category = body.get("category")
        if category not in CATEGORIES:
            raise _bad("UNSUPPORTED_CATEGORY", "category must be one of " + ", ".join(CATEGORIES) + ".")
        lat, lon = self._location(body.get("location"), required=True)
        place = body.get("place")
        if place is not None and (not isinstance(place, str) or len(place) > 120):
            raise _bad("INVALID_PLACE", "place must be text up to 120 characters.")
        picked = body.get("issueId")
        if picked is not None and (not isinstance(picked, str) or not ISSUE_RE.match(picked)):
            raise _bad("UNKNOWN_ISSUE", "issueId is not a Kestrel issue id.")
        photo = self._photo(body.get("photo"), now)
        digest_of = {**clean, "kind": "REPORT", "category": category, "lat": lat, "lon": lon, "place": place,
                     "issueId": picked, "photo": (body.get("photo") or {}).get("data", "")[:64]}

        def mutate(now: datetime, source: str) -> tuple[dict, int]:
            target = None
            if picked:
                target = self.store.get_issue(self.ns, picked)
                if target is None or not fusion.can_join(target, category, lat, lon, lifecycle.OPEN_STATES):
                    raise _bad("CANNOT_JOIN_ISSUE", "That issue is closed, a different category, or too far away.")
            target = target or fusion.find_match(self.store.list_issues(self.ns), category, lat, lon,
                                                 lifecycle.OPEN_STATES)
            joined = target is not None
            issue = target or self._new_issue(category, lat, lon, place and place.strip(), iso(now), clean["observedAt"])
            first_from_source = all(o["sourceKey"] != source for o in issue["observations"])
            issue["observations"].append({"eventId": clean["eventId"], "sourceKey": source, "kind": "REPORT",
                                          "observedAt": clean["observedAt"], "receivedAt": iso(now), "lat": lat,
                                          "lon": lon, "description": clean["description"], "details": clean["details"],
                                          "photoId": photo and photo["photoId"]})
            issue["openedAt"] = min(issue["openedAt"], clean["observedAt"])
            if not issue.get("place") and place:
                issue["place"] = place.strip()
            fusion.recentre(issue)
            issue["timeline"].append({"at": clean["observedAt"], "actor": "citizen", "source": source,
                                      "action": "JOINED" if joined else "REPORTED",
                                      "note": None if first_from_source or not joined else "same source again, counted once",
                                      "photoId": photo and photo["photoId"]})
            return issue, 200 if joined else 201

        return self._write(principal, body, digest_of, mutate, photo)

    def vote(self, issue_id: str, body: object, principal: "Principal") -> tuple[int, dict]:
        self._load(issue_id)
        now = self.svc.now()
        clean = self._common(body, {"schemaVersion", "eventId", "kind", "observedAt", "location", "description",
                                    "details", "photo", "clientMode"}, now)
        kind = body.get("kind")
        if kind not in VOTE_KINDS:
            raise _bad("UNSUPPORTED_KIND", "kind must be STILL_THERE or FIXED.")
        loc = self._location(body.get("location"), required=False)
        photo = self._photo(body.get("photo"), now)
        digest_of = {**clean, "kind": kind, "issueId": issue_id, "loc": loc,
                     "photo": (body.get("photo") or {}).get("data", "")[:64]}

        def mutate(now: datetime, source: str) -> tuple[dict, int]:
            issue = self._load(issue_id)
            if issue["workflow"]["state"] in lifecycle.TERMINAL:
                raise ApiError(409, "ISSUE_CLOSED", "This issue is closed. Report it again if the problem is back.")
            issue["observations"].append({"eventId": clean["eventId"], "sourceKey": source, "kind": kind,
                                          "observedAt": clean["observedAt"], "receivedAt": iso(now),
                                          "lat": loc and loc[0], "lon": loc and loc[1],
                                          "description": clean["description"], "details": clean["details"],
                                          "photoId": photo and photo["photoId"]})
            issue["timeline"].append({"at": clean["observedAt"], "actor": "citizen", "source": source,
                                      "action": kind, "photoId": photo and photo["photoId"]})
            return issue, 200

        return self._write(principal, body, digest_of, mutate, photo)

    # ------------------------------------------------------------ officers
    def _require_officer(self, principal: "Principal", ward_id: str) -> str:
        if self.svc.cfg.is_demo and principal.kind == "demo-admin":
            return "Demo administrator"
        if principal.kind == "officer" and ward_id in principal.groups:
            return "Ward officer"
        if principal.kind in ("officer", "demo", "jwt"):
            raise ApiError(403, "WARD_OFFICER_REQUIRED", "Only this ward's officer can do that.")
        raise ApiError(401, "AUTH_REQUIRED", "Sign in as a ward officer.")

    def transition(self, issue_id: str, body: object, principal: "Principal") -> dict:
        issue = self._load(issue_id)
        role = self._require_officer(principal, issue["wardId"])
        if not isinstance(body, dict) or set(body) - {"action", "note", "assignee", "afterPhoto",
                                                      "targetIssueId", "inspectedRevision"}:
            raise _bad("INVALID_TRANSITION", "Unsupported fields.")
        action, note = body.get("action"), body.get("note")
        if note is not None and (not isinstance(note, str) or len(note) > 500):
            raise _bad("INVALID_NOTE", "note must be text up to 500 characters.")
        if action in ("REJECT", "RESOLVE") and (not note or len(note.strip()) < 3):
            raise _bad("NOTE_REQUIRED", "Resolving or rejecting needs a public note (3-500 characters).")
        assignee = body.get("assignee")
        if action == "ASSIGN" and (not isinstance(assignee, str) or not 2 <= len(assignee.strip()) <= 80):
            raise _bad("ASSIGNEE_REQUIRED", "Name the team or agency (2-80 characters).")
        now = self.svc.now()
        photo = self._photo(body.get("afterPhoto"), now) if action == "RESOLVE" else None
        if action == "RESOLVE" and photo is None and not self.svc.cfg.is_demo:
            raise _bad("AFTER_PHOTO_REQUIRED", "Attach a photo of the fixed site.")
        self._advance(issue, now)
        if body.get("inspectedRevision") != issue["revision"]:
            raise ApiError(409, "STALE_REVISION", "New reports arrived since you opened this issue. Re-check.")
        try:
            new_state = lifecycle.next_state(issue["workflow"]["state"], action)
        except ValueError as exc:
            raise _bad(str(exc), f"{action} is not possible while the issue is {issue['workflow']['state']}.") from None

        target = None
        if action == "MERGE":
            target = self._load(body.get("targetIssueId") or "")
            if target["issueId"] == issue_id or target["category"] != issue["category"] or \
                    target["workflow"]["state"] in lifecycle.TERMINAL or \
                    fusion.distance(target, issue["lat"], issue["lon"]) > CATEGORIES[issue["category"]].radius_m * 4:
                raise _bad("CANNOT_MERGE", "Merge into an open issue of the same category nearby.")
        wf = issue["workflow"]
        wf["state"], wf["since"] = new_state, iso(now)
        if action == "ASSIGN":
            wf["assignee"] = assignee.strip()
        if action == "RESOLVE":
            wf["resolvedAt"] = iso(now)
            wf["everResolved"] = True
        if action == "REJECT":
            wf["rejectReason"] = note.strip()
        entry = {"at": iso(now), "actor": "officer", "action": action, "note": (note or "").strip() or
                 (f"Assigned to {assignee.strip()}" if action == "ASSIGN" else None),
                 "photoId": photo and photo["photoId"]}
        if action == "RESOLVE" and photo is None:
            entry["note"] = (entry["note"] or "") + " (no after-photo attached)"
        if action == "MERGE":
            wf["mergedInto"] = target["issueId"]
            entry["note"] = f"Duplicate of {target['issueId']}" + (f": {note.strip()}" if note else "")
        issue["timeline"].append(entry)
        expected = issue["revision"]
        issue["revision"] += 1
        issue["updatedAt"] = iso(now)

        if target is not None:
            # shortcut: two commits, not one transaction. A crash in between leaves the
            # reports in both issues (deduplicated by eventId on the next merge); fine for a pilot.
            known = {o["eventId"] for o in target["observations"]}
            target["observations"] += [o for o in issue["observations"] if o["eventId"] not in known]
            target["openedAt"] = min(target["openedAt"], issue["openedAt"])
            target["timeline"].append({"at": iso(now), "actor": "officer", "action": "MERGED_IN",
                                       "note": f"Reports from {issue_id} merged in"})
            fusion.recentre(target)
            t_expected = target["revision"]
            target["revision"] += 1
            target["updatedAt"] = iso(now)
            self._advance(target, now)
            try:
                self.store.commit_issue(self.ns, target, t_expected)
            except RevisionConflict:
                raise ApiError(409, "STALE_REVISION", "The target issue changed. Re-check.") from None
        try:
            self.store.commit_issue(self.ns, issue, expected, photo=photo)
        except RevisionConflict:
            raise ApiError(409, "STALE_REVISION", "New reports arrived while saving. Re-check.") from None
        result = self.issue(issue_id)
        result["actedAs"] = role
        return result

    def queue(self, ward_id: str, principal: "Principal") -> dict:
        ward = self._ward(ward_id)
        self._require_officer(principal, ward_id)
        now = self.svc.now()
        views = [v for v in self._views(now) if v["wardId"] == ward_id and v["workflow"]["state"] in lifecycle.OPEN_STATES]
        order = {"P1": 0, "P2": 1, "P3": 2}
        items = sorted((self._summary(v) | {"revision": v["revision"]} for v in views),
                       key=lambda i: (order[i["priority"]], -i["overdueDays"], i["openedAt"]))
        return {"ward": ward, "generatedAt": iso(now), "issues": items}

    # ------------------------------------------------------------ scorecards
    def _scorecard(self, ward: dict, views: list[dict], now: datetime) -> dict:
        mine = [v for v in views if v["wardId"] == ward["id"]]
        open_ = [v for v in mine if v["workflow"]["state"] in lifecycle.OPEN_STATES]
        resolved_days = [(parse_iso(v["workflow"]["resolvedAt"]) - parse_iso(v["openedAt"])).total_seconds() / 86400
                         for v in mine if v["workflow"].get("resolvedAt")]
        confirmed = sum(1 for v in mine if v["workflow"].get("confirmedFix"))
        unconfirmed = sum(1 for v in mine if v["workflow"]["state"] == "CLOSED_UNCONFIRMED")
        reopens = sum(v["workflow"].get("reopenCount", 0) for v in mine)
        judged = confirmed + unconfirmed + reopens
        return {
            "ward": {k: ward[k] for k in ("id", "name", "nameHi", "agency")},
            "totalIssues": len(mine), "openIssues": len(open_),
            "openByPriority": {p: sum(1 for v in open_ if v["severity"]["priority"] == p) for p in ("P1", "P2", "P3")},
            "overdue": sum(1 for v in open_ if v["overdueDays"] > 0),
            "medianDaysToResolve": round(statistics.median(resolved_days), 1) if resolved_days else None,
            "citizenConfirmedFixes": confirmed, "closedUnconfirmed": unconfirmed, "reopens": reopens,
            "confirmedFixRate": round(confirmed / judged, 2) if judged else None,
            "closedByCitizensOnly": sum(1 for v in mine if v["workflow"]["state"] == "CLOSED"
                                        and not v["workflow"].get("everResolved")),
            "byCategory": {c: sum(1 for v in open_ if v["category"] == c) for c in CATEGORIES},
        }

    def wards_view(self) -> dict:
        now = self.svc.now()
        views = self._views(now)
        return {"generatedAt": iso(now), "note": "Sample ward areas, not official boundaries.",
                "wards": [{**w, "scorecard": self._scorecard(w, views, now)} for w in self.wards]}

    def scorecard(self, ward_id: str) -> dict:
        ward = self._ward(ward_id)
        now = self.svc.now()
        return {"generatedAt": iso(now), **self._scorecard(ward, self._views(now), now)}

    # ------------------------------------------------------------ routing
    def route_hazards(self, now: datetime) -> tuple[list[dict], dict, list[dict]]:
        """Open issues that block routes, as hotspot-shaped features the route validator
        already understands: (features, states, summaries)."""
        features, states, summaries = [], {}, []
        for v in self._views(now):
            if not v["blocksRoute"]:
                continue
            r = max(20.0, CATEGORIES[v["category"]].radius_m)
            lat0 = v["lat"]
            ring = [[round(v["lon"] + r * math.cos(a) / (111_320 * math.cos(math.radians(lat0))), 7),
                     round(lat0 + r * math.sin(a) / 111_320, 7)]
                    for a in (k * math.pi / 4 for k in range(8))]
            ring.append(ring[0])
            features.append({"type": "Feature", "id": v["issueId"],
                             "geometry": {"type": "Polygon", "coordinates": [ring]},
                             "properties": {"id": v["issueId"], "displayName": CATEGORIES[v["category"]].label,
                                            "roadLevel": "surface", "centroid": [v["lon"], v["lat"]],
                                            "bypassAnchors": []}})
            states[v["issueId"]] = {"state": v["evidence"]["state"], "reasonCode": v["evidence"]["reasonCode"],
                                    "restricts": True, "nextTransitionAt": None}
            summaries.append(self._summary(v))
        return features, states, summaries
