"""Crisp stills of the real app (2x pixel density) for the explainer video.

    python backend/local_server.py
    python "project explanation/capture_screens.py"     -> project explanation/assets/screens/*.png
"""
from __future__ import annotations

import asyncio
import json
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE / "assets" / "screens"
API = "http://127.0.0.1:8787"
PHOTO = HERE.parent / "demo video" / "assets" / "photos" / "flooded-street.jpg"


def api(path: str, body: dict | None = None, headers: dict | None = None) -> dict:
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json", **(headers or {})}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    api("/v1/demo/control", {"reset": True}, {"x-demo-admin-key": "local-demo-admin"})
    issues = api("/v1/issues?status=open")["issues"]
    pothole = next(i for i in issues if "Moolchand" in (i["place"] or ""))
    water = next(i for i in issues if i["category"] == "WATERLOGGING" and "Lajpat" in (i["place"] or ""))
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", headless=True)
        phone = await b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True,
                                    geolocation={"latitude": water["lat"] + 0.00018, "longitude": water["lon"]}, permissions=["geolocation"])
        lat, lon = water["lat"] + 0.00018, water["lon"]
        await phone.add_init_script(f"""Object.defineProperty(navigator, 'geolocation', {{ value: {{
            getCurrentPosition: (ok) => setTimeout(() => ok({{ coords: {{ latitude: {lat}, longitude: {lon}, accuracy: 8 }}, timestamp: Date.now() }}), 300),
            watchPosition: () => 1, clearWatch: () => {{}} }} }});""")   # simulated GPS fix (Chrome's emulation is flaky headless)
        pg = await phone.new_page()
        await pg.goto(API + "/#/")
        await pg.evaluate("() => { localStorage.setItem('kestrel.citizen', 'demo-shots'); localStorage.setItem('kestrel.lang', 'en'); }")
        await pg.reload()
        await pg.wait_for_selector(".map-pin")
        await asyncio.sleep(3)
        await pg.screenshot(path=str(OUT / "home.png"))
        await pg.evaluate(f"() => location.hash = '#/i/{pothole['issueId']}'")
        await pg.wait_for_selector(".sev-parts")
        await asyncio.sleep(1.5)
        await pg.evaluate("() => document.querySelector('.sev').closest('section').scrollIntoView({block: 'start'})")
        await pg.evaluate("() => scrollBy(0, -70)")
        await asyncio.sleep(0.6)
        await pg.screenshot(path=str(OUT / "severity.png"))
        await pg.evaluate("() => scrollTo(0, 0)")
        await asyncio.sleep(0.6)
        await pg.screenshot(path=str(OUT / "issue.png"))
        # report wizard with the vision card
        await pg.evaluate("() => location.hash = '#/report'")
        await pg.wait_for_selector(".cat-tile")
        await pg.fill("#rep-say", "Ring Road underpass mein ghutno tak paani hai, gaadiyan phas gayi hain")
        await pg.evaluate("() => document.querySelector('#rep-say').dispatchEvent(new Event('change'))")
        await pg.wait_for_selector(".understood:has-text('We understood')")
        await asyncio.sleep(0.4)
        await pg.screenshot(path=str(OUT / "say.png"))
        await pg.click(".wiz-next")
        await pg.wait_for_selector(".loc-status:has-text('Located')")
        await pg.click(".wiz-next")
        await pg.set_input_files("#rep-photo", str(PHOTO))
        await pg.wait_for_selector(".vision-bars", timeout=60000)
        await asyncio.sleep(0.8)
        await pg.screenshot(path=str(OUT / "vision.png"))
        await pg.evaluate("() => location.hash = '#/wards'")
        await pg.wait_for_selector(".ward-card")
        await asyncio.sleep(1)
        await pg.screenshot(path=str(OUT / "wards.png"))
        await pg.evaluate("() => location.hash = '#/'")
        await pg.click("#c-lang")
        await asyncio.sleep(2.5)
        await pg.screenshot(path=str(OUT / "hindi.png"))
        await pg.click("#c-lang")
        # officer console on a laptop-sized screen
        desk = await b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1.5)
        dp = await desk.new_page()
        await dp.goto(API + f"/#/officer/W-LN")
        await dp.wait_for_selector(".q-row")
        await dp.click(".q-row:has-text('Moolchand')")
        await dp.wait_for_selector(".off-detail h2:has-text('Moolchand')")
        await asyncio.sleep(0.8)
        await dp.screenshot(path=str(OUT / "officer.png"))
        await b.close()
    print("wrote", sorted(x.name for x in OUT.iterdir()))


if __name__ == "__main__":
    asyncio.run(main())
