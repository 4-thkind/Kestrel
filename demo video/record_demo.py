"""Record the Kestrel product demo: the real app, driven in Chrome, framed in a 1080p stage with captions and voice.

    python backend/local_server.py                      (after: cd app && npm run build)
    python "demo video/record_demo.py"                  -> demo video/Kestrel-demo.mp4
    python "demo video/record_demo.py" --dry            -> quick run, screenshots only (checks the flow)

How it works: stage.html holds the app in an iframe (phone frame, or a laptop frame for the officer).
Playwright drives the real app while Chrome's screencast captures every painted frame with its timestamp.
Each segment's narration is synthesised first, so the actions are paced to the voice; the audio clips are
then placed at the exact times their segments started, over a ducked music bed.
Everything shown is the real app against the local server with the synthetic demo seed.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import mimetypes
import shutil
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kit  # noqa: E402

API = "http://127.0.0.1:8787"
BUILD = HERE / "build"
PHOTOS = HERE / "assets" / "photos"
NARR = "en-US-AndrewMultilingualNeural"   # narrator
CITIZEN = "en-US-AvaMultilingualNeural"   # Riya, the citizen


def api(path: str, body: dict | None = None, headers: dict | None = None) -> dict:
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json", **(headers or {})}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


# --------------------------------------------------------------------------------------------- script
SEGMENTS = [
    dict(id="intro", card=True, parts=[(NARR, "Meet Riya. Her route to college floods every monsoon, and complaining never changed anything. This is Kestrel.")]),
    dict(id="home", n=1, chapter="The city, live", title="One pin per <em>problem</em>,<br>not per complaint",
         sub="Duplicate reports are fused into a single issue and ranked by a severity score anyone can read.",
         pills=["31 open issues", "8 sample wards", "!P1 · P2 · P3"],
         parts=[(NARR, "Delhi, right now. One pin per problem, not per complaint, ranked by how urgent it really is.")]),
    dict(id="say", n=2, chapter="Report in seconds", title="Say it the way<br>you'd <em>say it</em>",
         sub="Typed or spoken, in English, Hindi or Hinglish. Kestrel fills the form for you.",
         pills=["Voice input", "Plain language", "Category + details"],
         parts=[(NARR, "Riya just says what she sees."), (CITIZEN, "Knee-deep water in the Ring Road underpass, vehicles are stuck."), (NARR, "Kestrel fills in the form.")]),
    dict(id="where", n=3, chapter="Where is it?", title="Pinned from <em>GPS</em>",
         sub="Accurate to a few metres. Tap the map to adjust.",
         parts=[(NARR, "GPS sets the spot.")]),
    dict(id="junk", n=4, chapter="Kestrel Vision", title="Our own model,<br><em>on the phone</em>",
         sub="A 13.7 MB model reads the photo inside the browser. Nothing is uploaded for this check.",
         pills=["!Runs on-device", "Rejects junk photos", "Privacy nudge"],
         parts=[(NARR, "Wrong photo? Kestrel Vision, our own AI running on the phone, rejects the selfie.")]),
    dict(id="water", n=4, chapter="Kestrel Vision", title="It <em>agrees</em>:<br>waterlogging",
         sub="Tested on 431 hand-checked photos it never saw: 84.5% right, 94% when it is confident enough to pre-fill.",
         pills=["84.5% on unseen photos", "!94% when confident"],
         parts=[(NARR, "The right one? Waterlogging, very likely. Nothing was uploaded.")]),
    dict(id="dupes", n=5, chapter="No duplicates", title="Is it <em>one of these</em>?",
         sub="Same category, within that category's radius: join the existing issue instead of filing a new one.",
         pills=["60 m radius for waterlogging", "Each person counts once"],
         parts=[(NARR, "Three people already reported this, so she joins that issue instead of filing a duplicate.")]),
    dict(id="sent", n=5, chapter="No duplicates", title="Your voice <em>adds weight</em>",
         sub="More independent people confirming raises the priority. The report goes through a durable outbox, sent exactly once.",
         parts=[(NARR, "Her voice raises its priority.")]),
    dict(id="issue", n=6, chapter="Public tracking", title="Every step,<br><em>in public</em>",
         sub="Who owns it, where it is in the workflow, why it ranks this urgent, and a full timeline.",
         pills=["Transparent score", "Public timeline", "Share on WhatsApp"],
         parts=[(NARR, "Every issue gets a public page: who owns it, every step so far, and exactly why it's this urgent.")]),
    dict(id="wards", n=7, chapter="Ward scorecards", title="Which ward<br><em>actually fixes</em> things?",
         sub="A fix counts only when citizens confirm it. Reopens and overdue issues count against the ward.",
         pills=["A to F grades", "Citizen-confirmed fixes"],
         parts=[(NARR, "Wards get public grades, based only on fixes that citizens confirm.")]),
    dict(id="officer", n=8, chapter="Ward officer", title="One clean,<br><em>ranked</em> queue",
         sub="Deduplicated and sorted by priority. Every action lands on the public timeline.",
         pills=["Assign", "Start", "Resolve", "Merge"],
         transition="<img src='assets/logo-mark.png' alt=''><h2>Meanwhile, at the <em>ward office</em></h2><p class='tag'>The officer's console</p>",
         parts=[(NARR, "The ward officer sees one ranked queue. Fourteen reports, one task.")]),
    dict(id="fake", n=9, chapter="Proof of fix", title="A fake fix<br><em>can't hide</em>",
         sub="Kestrel Vision checks the after-photo. The same check runs on every citizen's phone.",
         pills=["!93% accurate after-photo check"],
         parts=[(NARR, "A fake after-photo? Kestrel Vision flags it, and the same check runs on every citizen's phone.")]),
    dict(id="real", n=9, chapter="Proof of fix", title="A real fix,<br><em>on the record</em>",
         sub="Genuine after-photo, public note, and the timeline updates instantly.",
         parts=[(NARR, "A real fix goes straight onto the public timeline.")]),
    dict(id="confirm", n=10, chapter="Citizens close it", title="Resolved is<br><em>not closed</em>",
         sub="Two citizens confirming the fix closes it. Two saying 'still there' reopen it.",
         pills=["Two confirmations", "Reopens count against the ward"],
         transition="<img src='assets/logo-mark.png' alt=''><h2>Back on the <em>street</em></h2><p class='tag'>Citizens have the last word</p>",
         parts=[(NARR, "But it only closes when two citizens confirm. One. Two. Closed.")]),
    dict(id="plan", n=11, chapter="Ride mode", title="A route that<br><em>knows the city</em>",
         sub="Every route is checked against the hazards citizens have reported: waterlogging, open manholes, blocked roads, deep potholes.",
         pills=["Two-wheeler, car, auto", "Hazard-aware routing"],
         transition="<img src='assets/logo-mark.png' alt=''><h2>Reports keep people <em>safe</em></h2><p class='tag'>Ride mode</p>",
         parts=[(NARR, "Reports also keep people safe. In ride mode, Kestrel checks her route against every hazard citizens have reported.")]),
    dict(id="why", n=11, chapter="Ride mode", title="Every route,<br><em>explained</em>",
         sub="Fresh reports, how many different people, how old they are. No reports means unknown, never safe.",
         pills=["Evidence, not guesses", "Stale never shows green"],
         parts=[(NARR, "Why this route shows the evidence. No reports means unknown, never safe.")]),
    dict(id="reroute", n=12, chapter="Live rerouting", title="The city reports,<br><em>the route changes</em>",
         sub="Two other riders report water at the Minto Bridge underpass. Her route updates on its own, with the reason.",
         pills=["!Live updates", "Two independent sources"],
         parts=[(NARR, "Two riders report water at Minto Bridge, and within seconds, her route moves to the flyover.")]),
    dict(id="camera", n=13, chapter="Camera ride", title="The camera<br><em>watches the road</em>",
         sub="Two small models run on the phone: one finds potholes and estimates their depth, the other looks for water ahead.",
         pills=["YOLOv8n potholes", "SegFormer water", "!On-device"],
         parts=[(NARR, "On a mount, two more models run on the phone: one finds potholes and estimates their depth, the other watches for water.")]),
    dict(id="flood", n=13, chapter="Camera ride", title="Water ahead?<br><em>Find a way round.</em>",
         sub="A spoken warning and a saved dashcam clip. It looks for a way around, and when there is none, it says so instead of guiding her into water.",
         pills=["Spoken alerts", "Dashcam clips", "!Never fakes safety"],
         parts=[(NARR, "Water ahead. She gets a spoken warning and a saved clip. And with no way around on the flyover, it tells her to stop, instead of faking safety.")]),
    dict(id="summary", n=13, chapter="Camera ride", title="Every ride<br><em>maps the city</em>",
         sub="Potholes seen, water alerts and saved clips, each one tap away from becoming a report. Pocket mode speaks the directions instead.",
         pills=["Ride summary", "One-tap reports", "Pocket mode"],
         parts=[(NARR, "The ride ends with a summary, and every sighting is one tap away from a report.")]),
    dict(id="offline", n=14, chapter="Works offline", title="No network?<br><em>No problem.</em>",
         sub="The report waits safely on the phone and sends itself, exactly once, when you are back online.",
         pills=["Offline outbox", "Idempotent writes", "PWA"],
         parts=[(NARR, "No network? Reports wait on the phone and send themselves later, exactly once.")]),
    dict(id="hindi", n=15, chapter="Built for Bharat", title="Every screen,<br><em>in Hindi too</em>",
         sub="Hindi and English throughout, and light enough for a budget phone.",
         pills=["Hindi", "English", "Budget phones"],
         parts=[(NARR, "And every screen works in Hindi.")]),
    dict(id="outro", card=True, parts=[(NARR, "Kestrel. Report once, track in public, and ride safer. Thank you!")]),
]
CHAPTERS = 15

INTRO = ("<img src='assets/logo-mark.png' alt=''><h1>Kestrel</h1>"
         "<p>Report civic problems once. Track them in public until they're fixed.<br>Ride around them safely in the meantime.</p>"
         "<p class='tag'>Build for Bharat · Smarter Cities and Civic Infrastructure</p>")
OUTRO = ("<img src='assets/logo-mark.png' alt=''><h1>Kestrel</h1>"
         "<p>Report once &nbsp;·&nbsp; Track in public &nbsp;·&nbsp; Ride safer</p>"
         "<p class='tag'>github.com/4-thkind/Kestrel</p>"
         "<p class='small'>Real app, synthetic demo data. Photos: Tracy Hunter, thomas.vangeijn, Alan Stanton and others on Flickr (CC BY / BY-SA). Camera feed simulated from RDD2022 India road photos (CC BY-SA 4.0). Map © OpenStreetMap contributors.</p>")


# --------------------------------------------------------------------------------------------- recorder
class Rec:
    def __init__(self, page, dry: bool) -> None:
        self.page, self.dry = page, dry
        self.app = page.frame_locator("#app")
        self.frame = None
        self.frames: list[tuple[float, Path]] = []
        self.seg_t0 = 0.0
        self.shots = 0

    async def js(self, expr: str, arg=None):
        return await self.frame.evaluate(expr, arg)

    async def tap(self, loc, pause: float = 0.18) -> None:
        await loc.scroll_into_view_if_needed()
        bb = await loc.bounding_box()
        if bb:
            await self.page.evaluate("p => stage.tap(p[0], p[1])", [bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2])
        await asyncio.sleep(pause)
        await loc.click()

    async def tap_js(self, sel: str) -> None:
        """Ripple where the element is, then the app's own click handler (for elements that never settle)."""
        bb = await self.app.locator(sel).bounding_box()
        if bb:
            await self.page.evaluate("p => stage.tap(p[0], p[1])", [bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2])
        await asyncio.sleep(0.18)
        await self.js(f"() => document.querySelector({json.dumps(sel)}).click()")

    async def at(self, sec: float) -> None:
        """Wait until `sec` seconds into the current segment's narration."""
        if self.dry:
            return
        d = self.seg_t0 + sec - time.time()
        if d > 0:
            await asyncio.sleep(d)

    async def hash(self, h: str) -> None:
        await self.js("h => { location.hash = h; }", h)

    async def scroll(self, y: int, smooth=True) -> None:
        await self.js("([y, s]) => window.scrollTo({ top: y, behavior: s ? 'smooth' : 'instant' })", [y, smooth])

    async def glide(self, to: int, seconds: float) -> None:
        """Slow, even scroll of the app page (smooth scrolling is too fast to read)."""
        start = await self.js("() => scrollY")
        steps = max(1, int(seconds * 30))
        for i in range(1, steps + 1):
            k = i / steps
            k = k * k * (3 - 2 * k)
            await self.js("y => window.scrollTo(0, y)", start + (to - start) * k)
            await asyncio.sleep(seconds / steps if not self.dry else 0)

    async def shot(self, name: str) -> None:
        if self.dry:
            self.shots += 1
            await self.page.screenshot(path=str(BUILD / "dry" / f"{self.shots:02d}-{name}.png"))


async def run_segment_actions(r: Rec, seg: dict, ctx: dict) -> None:
    sid = seg["id"]
    a = r.app
    if sid == "home":
        await asyncio.sleep(1.5)
        handle = a.locator(".sheet-handle")
        bb = await handle.bounding_box()
        if bb:
            x, y = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
            await r.page.evaluate("p => stage.tap(p[0], p[1])", [x, y])
            await r.page.mouse.move(x, y)
            await r.page.mouse.down()
            await r.page.mouse.move(x, y - 210, steps=24)
            await r.page.mouse.up()
        await r.at(4.0)
        await r.tap(a.locator(".filter-chip[data-cat='POTHOLE']"))
        await r.at(6.0)
        await r.tap(a.locator(".filter-chip[data-cat='ALL']"))
        await r.shot("home")
    elif sid == "say":
        await r.tap(a.locator(".c-tab-report"))
        box = a.locator("#rep-say")
        await box.wait_for()
        await r.at(seg["meta"]["starts"][1] - 0.2)
        await r.tap(box, 0.1)
        text = "Knee-deep water in the Ring Road underpass, vehicles are stuck"
        dur = seg["meta"]["starts"][2] - seg["meta"]["starts"][1]
        await box.press_sequentially(text, delay=0 if r.dry else max(25, int(dur * 1000 * 0.9 / len(text))))
        await r.js("() => document.querySelector('#rep-say').dispatchEvent(new Event('change'))")
        await a.locator(".understood", has_text="We understood").wait_for()
        await r.shot("say")
    elif sid == "where":
        await r.tap(a.locator(".wiz-next"))
        located = a.locator(".loc-status", has_text="Located")
        for _ in range(4):
            try:
                await located.wait_for(timeout=5000)
                break
            except Exception:
                await r.tap(a.locator(".loc-row button"))
        await located.wait_for(timeout=8000)
        await r.shot("where")
    elif sid == "junk":
        await r.at(1.0)
        await r.tap(a.locator(".wiz-next"))
        await a.locator(".photo-drop").wait_for()
        await r.at(2.6)
        await r.tap(a.locator(".photo-drop"), 0.25)
        await a.locator("#rep-photo").set_input_files(str(PHOTOS / "selfie.jpg"))
        await a.locator(".vision-bars").wait_for(timeout=60000)
        await r.shot("junk")
    elif sid == "water":
        await r.tap(a.locator(".photo-preview .link"))
        await asyncio.sleep(0.3)
        await a.locator("#rep-photo").set_input_files(str(PHOTOS / "flooded-street.jpg"))
        await a.locator(".vision-bars").wait_for(timeout=60000)
        await asyncio.sleep(0.6)
        await r.glide(260, 1.5)
        await r.shot("water")
    elif sid == "dupes":
        await r.tap(a.locator(".wiz-next"))
        same = a.locator(".dupe button", has_text="Same one").first
        await same.wait_for(timeout=15000)
        await r.glide(400, 1.2)
        await r.at(seg["meta"]["duration"] - 3.2)
        await r.tap(same)
        await a.locator(".dupe button", has_text="Joined").wait_for()
        await r.shot("dupes")
    elif sid == "sent":
        await r.tap(a.locator(".wiz-next"))
        await a.locator(".rep-done").wait_for(timeout=15000)
        await r.shot("sent")
    elif sid == "issue":
        await r.tap(a.locator(".rep-done a.primary"))
        await a.locator(".issue-hero").wait_for()
        await asyncio.sleep(1.2)
        total = seg["meta"]["duration"]
        h = await r.js("() => document.documentElement.scrollHeight - innerHeight")
        await r.at(2.0)
        await r.glide(min(h, 900), 3)
        await r.glide(min(h, 1900), 3)
        await r.shot("issue")
    elif sid == "wards":
        await r.tap(a.locator(".c-tab", has_text="Wards"))
        await a.locator(".ward-card").first.wait_for()
        await asyncio.sleep(1.5)
        await r.glide(700, 3.5)
        await r.shot("wards")
    elif sid == "officer":
        await r.hash(f"#/officer/W-LN")
        row = a.locator(".q-row", has_text="Moolchand")
        await row.wait_for(timeout=15000)
        await asyncio.sleep(0.3)
        await r.page.evaluate("() => stage.card(null)")
        await r.at(3.0)
        await r.tap(row)
        await a.locator(".off-detail h2", has_text="Moolchand").wait_for()
        await r.shot("officer")
    elif sid == "fake":
        await r.tap(a.locator(".seg button", has_text="Mark resolved"))
        await asyncio.sleep(0.6)
        await r.at(2.5)
        await a.locator(".off-fields input[type=file]").set_input_files(str(PHOTOS / "pothole.jpg"))
        await a.locator(".off-fields .vision-check.bad").wait_for(timeout=60000)
        await r.js("() => document.querySelector('.off-fields .vision-check').scrollIntoView({block:'center', behavior:'smooth'})")
        await r.shot("fake")
    elif sid == "real":
        await a.locator(".off-fields input[type=file]").set_input_files(str(PHOTOS / "repaired-road.jpg"))
        await a.locator(".off-fields .vision-check.good").wait_for(timeout=60000)
        note = a.locator(".off-fields textarea")
        await r.tap(note, 0.1)
        await note.press_sequentially("Patched and rolled. After-photo attached.", delay=0 if r.dry else 32)
        await r.tap(a.locator(".off-form button.primary", has_text="Apply"))
        await a.locator(".toast.show", has_text="Saved").wait_for(timeout=15000)
        await r.shot("real")
    elif sid == "confirm":
        await r.hash(f"#/i/{ctx['pothole']}")
        await a.locator(".vote-fixed").wait_for(timeout=15000)
        await r.page.evaluate("() => stage.card(null)")
        await r.js("() => document.querySelector('.vote').scrollIntoView({block:'center'})")
        await r.at(seg["meta"]["duration"] * 0.45)
        await r.tap(a.locator(".vote-fixed"))
        await a.locator(".toast.show", has_text="Thanks").wait_for()
        await r.js("() => localStorage.setItem('kestrel.citizen', 'demo-neighbour-2')")
        await r.at(seg["meta"]["duration"] * 0.62)
        await r.js("() => document.querySelector('.vote')?.scrollIntoView({block:'center'})")
        await r.tap(a.locator(".vote-fixed"))
        await a.locator(".hero-status .pill", has_text="Closed").wait_for(timeout=15000)
        await r.scroll(0)
        await r.shot("confirm")
    elif sid == "plan":
        await r.tap(a.locator(".c-tab", has_text="Ride"))
        await asyncio.sleep(1.2)
        rider = a.locator('[data-role="rider"]')
        await rider.wait_for(timeout=15000)
        await r.page.evaluate("() => stage.card(null)")
        await r.at(1.5)
        await r.tap(rider)
        await asyncio.sleep(1.0)
        await r.tap(a.locator("#btn-preset"))
        await a.locator("#decision-card .route-name").wait_for(timeout=20000)
        await r.at(seg["meta"]["duration"] - 4.5)
        await r.tap(a.locator("#vehicle-row .vchip", has_text="Car"))
        await asyncio.sleep(1.6)
        await r.tap(a.locator("#vehicle-row .vchip", has_text="Two-wheeler"))
        await r.shot("plan")
    elif sid == "why":
        await r.tap(a.locator("#btn-why"))
        await asyncio.sleep(1.2)
        await r.at(seg["meta"]["duration"] * 0.45)
        await r.js("() => document.getElementById('screen-evidence').scrollTo({ top: 420, behavior: 'smooth' })")
        await r.at(seg["meta"]["duration"] - 1.5)
        await r.tap(a.locator("#btn-ev-back"))
        await r.shot("why")
    elif sid == "reroute":
        status = api("/v1/status")
        await r.at(1.5)
        for who in ("demo-rider-a", "demo-rider-b"):
            api("/v1/observations", {"schemaVersion": "1.0", "eventId": str(uuid.uuid4()), "hotspotId": "MINTO_BRIDGE", "kind": "WATER_OBSERVED",
                                     "observedAt": status["serverTime"], "location": {"source": "selected_hotspot", "accuracyM": None},
                                     "clientMode": status["clientMode"]}, {"x-demo-contributor": who})
        await r.frame.wait_for_function("() => document.querySelector('#decision-card').innerText.includes('Shivaji')", timeout=45000)
        await r.shot("reroute")
    elif sid == "camera":
        await r.at(1.0)
        await r.tap(a.locator("#btn-ride"))
        await a.locator("#screen-ride").wait_for(timeout=15000)
        ctx["drive"] = asyncio.ensure_future(drive(r, ctx))
        await r.shot("camera")
    elif sid == "flood":
        await a.locator("#alert-banner", has_text="water").wait_for(timeout=60000)
        await r.shot("flood")
    elif sid == "summary":
        if ctx.get("drive"):
            ctx["drive"].cancel()   # fewer calls into a page whose main thread is busy running the detector
        await r.at(0.5)
        await r.tap_js("#btn-end")   # the ride map keeps animating, so a pointer click waits for "stable" forever
        await a.locator("#screen-summary").wait_for(timeout=15000)
        if ctx.get("drive"):
            ctx["drive"].cancel()
        await asyncio.sleep(1.0)
        await r.at(seg["meta"]["duration"] * 0.55)
        await r.js("() => document.getElementById('screen-summary').scrollTo({ top: 400, behavior: 'smooth' })")
        await r.shot("summary")
        await r.at(seg["meta"]["duration"] - 0.6)
        await r.tap_js("#btn-home")
    elif sid == "offline":
        await r.page.context.set_offline(True)
        await r.hash("#/report")
        again = a.locator("button", has_text="Report another")
        if await again.count():
            await r.tap(again)
        await r.tap(a.locator(".cat-tile", has_text="Open manhole"))
        for _ in range(3):
            await r.tap(a.locator(".wiz-next"), 0.12)
            await asyncio.sleep(0.5)
        await r.tap(a.locator(".wiz-next"))
        await a.locator(".rep-done h1", has_text="Saved on your phone").wait_for(timeout=15000)
        await r.frame.wait_for_function("() => !document.getElementById('c-pending').hidden")   # "1 waiting to send"
        await r.at(seg["meta"]["duration"] - 4.5)
        await r.page.context.set_offline(False)      # Chrome fires `online`; the outbox sends and the badge clears
        await r.frame.wait_for_function("() => document.getElementById('c-pending').hidden", timeout=15000)
        await asyncio.sleep(1.0)
        await r.shot("offline")
    elif sid == "hindi":
        await r.hash("#/")
        await asyncio.sleep(0.6)
        await r.tap(r.app.locator("#c-lang"))
        await asyncio.sleep(1.5)
        await r.shot("hindi")


async def drive(r: Rec, ctx: dict) -> None:
    """Simulated GPS: ride along the selected route at about 22 km/h (we are not riding in Delhi)."""
    route = ctx.get("route") or []
    if len(route) < 2:
        return
    import math
    pts = [(lat, lon) for lon, lat in route]
    seg_len = [math.dist((p[0] * 111_000, p[1] * 97_500), (q[0] * 111_000, q[1] * 97_500)) for p, q in zip(pts, pts[1:])]
    # start 40% of the way along: the camera's personal reroute needs room for a detour
    speed, travelled, k = 6.0, sum(seg_len) * 0.4, 0
    while True:
        while k < len(seg_len) and travelled > seg_len[k]:
            travelled -= seg_len[k]
            k += 1
        if k >= len(seg_len):
            return
        f = travelled / seg_len[k] if seg_len[k] else 0
        (la, lo), (lb, lo2) = pts[k], pts[k + 1]
        heading = (math.degrees(math.atan2((lo2 - lo) * 97_500, (lb - la) * 111_000)) + 360) % 360
        try:
            await r.frame.evaluate("p => window.__gps && window.__gps(p[0], p[1], p[2], p[3])", [la + (lb - la) * f, lo + (lo2 - lo) * f, speed, heading])
        except Exception:
            return
        await asyncio.sleep(1.0)
        travelled += speed * 1.0


async def subtitles(page, seg: dict, t0: float) -> None:
    for a_, b_, text in seg["meta"]["cues"]:
        d = t0 + a_ - time.time()
        if d > 0:
            await asyncio.sleep(d)
        await page.evaluate("t => stage.subtitle(t)", text)
    d = t0 + seg["meta"]["duration"] - time.time()
    if d > 0:
        await asyncio.sleep(d)
    await page.evaluate("() => stage.subtitle('')")


async def record(dry: bool) -> tuple[list, list, float, float]:
    # fresh synthetic city, and the ids this run needs
    api("/v1/demo/control", {"reset": True}, {"x-demo-admin-key": "local-demo-admin"})
    issues = api("/v1/issues?status=open")["issues"]
    water = next(i for i in issues if i["category"] == "WATERLOGGING" and "Lajpat" in (i["place"] or ""))
    pothole = next(i for i in issues if "Moolchand" in (i["place"] or ""))
    ctx = {"pothole": pothole["issueId"]}

    frames_dir = Path(tempfile.mkdtemp(prefix="kestrel-frames-"))
    frames: list[tuple[float, Path]] = []
    events: list[tuple[float, Path]] = []

    async with async_playwright() as p:
        drive_cam = BUILD / "drive.y4m"   # fake dashcam feed: python "demo video/make_drive.py"
        if not drive_cam.exists():
            raise SystemExit("run make_drive.py first (builds the simulated dashcam feed)")
        browser = await p.chromium.launch(channel="chrome", headless=True, args=["--autoplay-policy=no-user-gesture-required",
            "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", f"--use-file-for-fake-video-capture={drive_cam}"])
        context = await browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1,
                                            geolocation={"latitude": water["lat"] + 0.00018, "longitude": water["lon"] - 0.00012, "accuracy": 8},
                                            permissions=["geolocation", "camera"])

        async def serve(route):
            rel = route.request.url.split("/__stage/", 1)[1].split("?")[0]
            f = HERE / rel
            await route.fulfill(path=str(f), content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        # simulated GPS fix at the underpass (we are not standing in Delhi); Chrome's own emulation was flaky under screencast
        lat, lon = water["lat"] + 0.00018, water["lon"] - 0.00012
        await context.add_init_script(f"""(() => {{
          let fix = {{ lat: {lat}, lon: {lon} }}, speed = null, heading = null, n = 0; const watchers = new Map();
          const pos = () => ({{ coords: {{ latitude: fix.lat, longitude: fix.lon, accuracy: 8, altitude: null, altitudeAccuracy: null, heading, speed }}, timestamp: Date.now() }});
          window.__gps = (lat, lon, s, h) => {{ fix = {{ lat, lon }}; speed = s; heading = h; for (const cb of watchers.values()) cb(pos()); }};
          Object.defineProperty(navigator, 'geolocation', {{ value: {{
            getCurrentPosition: (ok) => setTimeout(() => ok(pos()), 700),
            watchPosition: (ok) => {{ const id = ++n; watchers.set(id, ok); setTimeout(() => ok(pos()), 700); return id; }},
            clearWatch: (id) => watchers.delete(id) }} }});
        }})();""")

        async def on_response(resp):
            if "/v1/routes/compare" in resp.url:
                try:
                    d = await resp.json()
                    sel = next(x for x in d["routes"] if x["id"] == d["selectedRouteId"])
                    ctx["route"] = sel["geometry"]["coordinates"]
                except Exception:
                    pass
        context.on("response", lambda resp: asyncio.ensure_future(on_response(resp)))
        await context.route("**/__stage/**", serve)
        page = await context.new_page()
        page.on("pageerror", lambda e: print("PAGE ERROR", e))
        await page.goto(API + "/__stage/stage.html")
        await page.evaluate(f"() => {{ stage.chapters({CHAPTERS}); stage.card({json.dumps(INTRO)}); }}")
        await page.evaluate("() => { localStorage.setItem('kestrel.citizen', 'demo-riya'); localStorage.setItem('kestrel.lang', 'en'); }")
        await page.evaluate(f"() => document.getElementById('app').src = '{API}/#/'")
        r = Rec(page, dry)
        await page.wait_for_function("() => document.getElementById('app').contentWindow.document.querySelector('.map-pin')", timeout=30000)
        r.frame = await (await page.query_selector("#app")).content_frame()
        # warm the vision model so the first photo is instant (loads the ONNX file into the browser cache)
        await asyncio.sleep(1.0)

        cdp = await context.new_cdp_session(page)

        def on_frame(params):
            ts = params["metadata"]["timestamp"]
            path = frames_dir / f"{len(frames):06d}.jpg"
            path.write_bytes(base64.b64decode(params["data"]))
            frames.append((ts, path))
            asyncio.ensure_future(cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]}))
        cdp.on("Page.screencastFrame", on_frame)
        if not dry:
            await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 93, "maxWidth": 1920, "maxHeight": 1080, "everyNthFrame": 1})
        start = time.time()
        await asyncio.sleep(0.4)

        for seg in SEGMENTS:
            meta = seg["meta"]
            if seg.get("transition"):
                await page.evaluate("h => stage.card(h)", seg["transition"])
                await asyncio.sleep(0 if dry else 0.6)
                if seg["id"] == "officer":
                    await page.evaluate("() => { stage.mode('laptop'); stage.url('kestrel.app/#/officer/W-LN'); }")
                if seg["id"] == "confirm":
                    await page.evaluate("() => stage.mode('phone')")
                await asyncio.sleep(0 if dry else 0.9)
            if seg["id"] == "outro":
                await page.evaluate("h => stage.card(h)", OUTRO)
                await asyncio.sleep(0 if dry else 0.6)
            if not seg.get("card"):
                await page.evaluate("s => stage.set(s)", {k: seg[k] for k in ("n", "chapter", "title", "sub", "pills") if k in seg})
                await asyncio.sleep(0 if dry else 0.35)
            t0 = time.time()
            r.seg_t0 = t0
            events.append((t0 - start, BUILD / f"{seg['id']}.wav"))
            subs = None if dry else asyncio.ensure_future(subtitles(page, seg, t0))
            try:
                await run_segment_actions(r, seg, ctx)
            except Exception as err:
                await page.screenshot(path=str(BUILD / f"FAILED-{seg['id']}.png"))
                raise RuntimeError(f"segment {seg['id']} failed: {err}") from err
            if subs:
                await subs
            if seg["id"] == "intro":
                await page.evaluate("() => stage.card(null)")
            await asyncio.sleep(0 if dry else 0.3)
            print(f"  {seg['id']:<8} done at {time.time() - start:6.1f}s", flush=True)
        await asyncio.sleep(0 if dry else 1.5)
        end = time.time()
        if not dry:
            await cdp.send("Page.stopScreencast")
        await asyncio.sleep(0.5)
        await browser.close()
    return frames, events, start, end


def frames_to_video(frames: list[tuple[float, Path]], start: float, end: float, out: Path) -> None:
    lst = out.with_suffix(".txt")
    lines = []
    frames = sorted(frames)
    for i, (ts, path) in enumerate(frames):
        nxt = frames[i + 1][0] if i + 1 < len(frames) else end
        if i == 0:
            ts = start
        lines += [f"file '{path.as_posix()}'", f"duration {max(0.001, nxt - ts):.4f}"]
    lines.append(f"file '{frames[-1][1].as_posix()}'")
    lst.write_text("\n".join(lines), encoding="utf-8")
    kit.ff("-f", "concat", "-safe", "0", "-i", str(lst), "-vf", "fps=30,scale=1920:1080:flags=lanczos:out_range=tv,format=yuv420p",
           "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-tune", "animation", str(out))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    BUILD.mkdir(exist_ok=True)
    if args.dry:
        shutil.rmtree(BUILD / "dry", ignore_errors=True)
        (BUILD / "dry").mkdir()
    print("voice…", flush=True)
    for seg in SEGMENTS:
        seg["meta"] = kit.speak(seg["parts"], BUILD / f"{seg['id']}.wav")
    total_voice = sum(s["meta"]["duration"] for s in SEGMENTS)
    print(f"  narration {total_voice:.1f}s", flush=True)
    print("recording…", flush=True)
    frames, events, start, end = asyncio.run(record(args.dry))
    if args.dry:
        print("dry run ok, screenshots in", BUILD / "dry")
        return
    seconds = end - start
    (BUILD / "events.json").write_text(json.dumps({"start": start, "end": end, "events": [(t, str(w)) for t, w in events]}), encoding="utf-8")
    print(f"  {len(frames)} frames over {seconds:.1f}s ({len(frames) / seconds:.1f} fps captured)", flush=True)
    video = BUILD / "video.mp4"
    frames_to_video(frames, start, end, video)
    kit.make_music(seconds, BUILD / "music.wav")
    kit.mix_audio(events, seconds, BUILD / "music.wav", BUILD / "audio.wav")
    out = HERE / "Kestrel-demo.mp4"
    kit.mux(video, BUILD / "audio.wav", out)
    shutil.rmtree(frames[0][1].parent, ignore_errors=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
