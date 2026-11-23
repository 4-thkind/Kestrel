"""Render the Kestrel explainer: narrated motion graphics, frame by frame, at 1080p 30 fps.

    python "project explanation/capture_screens.py"      (once, needs the local server: app stills)
    python "project explanation/render_explainer.py"     -> project explanation/Kestrel-explained.mp4
    python "project explanation/render_explainer.py" --stills   -> a few sample frames only

explainer.html holds every scene; window.render(t) draws the exact frame for time t, so the output is
deterministic and every animation is cued to the sentence the narrator is speaking (edge-tts sentence
boundaries). Narration: edge-tts Andrew (multilingual neural), plain English.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import subprocess
import sys
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "demo video"))
import kit  # noqa: E402

BUILD = HERE / "build"
VOICE = "en-US-AndrewMultilingualNeural"
FPS = 30
LEAD, TAIL = 0.5, 0.85

SCENES = [
    # sentence counts per scene must match the cue indices (c0, c1, ...) used in explainer.html
    ("hook", "Quick question. How many times have you passed the same pothole, every single day, and assumed someone must have complained by now?"),
    ("problem", "Here's the thing. Delhi already has complaint apps and helplines. Reporting isn't the problem. What happens after is. "
                "One pothole gets fifty separate complaints. Nobody can tell which one is urgent. "
                "And when the ticket says resolved, nobody can check. The ticket closes, and the pothole stays."),
    ("who", "This hurts three people. The citizen, who never knows if anyone listened. The ward officer, drowning in duplicates. "
            "And the city, with no honest picture of what gets fixed."),
    ("solution", "So we built Kestrel. The idea is simple. Report it once. Track it in public. Close it only when citizens confirm the fix. "
                 "And meanwhile, ride around it safely."),
    ("fusion", "First, duplicates. Kestrel looks for the same problem nearby. Each category has its own radius. "
               "Twenty-five metres for a pothole, sixty for waterlogging. Fifty complaints become one issue, with fifty voices."),
    ("severity", "Second, priority. Not a black-box AI score. A simple sum anyone can read. "
                 "Category base, people confirming, depth, a major road or a school nearby, and days overdue. "
                 "Seventy or more is P1, and the officer sees exactly why."),
    ("lifecycle", "Third, accountability. Assign, start, resolve: every step goes on a public timeline. But resolved is not closed. "
                  "Two citizens must confirm the fix. Two people saying it's still there reopens it. "
                  "And reopens count against the ward's public scorecard."),
    ("vision", "Then there's Kestrel Vision, our own AI model. Just thirteen point seven MB, running in the phone's browser. "
               "It suggests the category, rejects junk photos, matches same-spot photos, and catches fake fixes. "
               "We distilled two open CLIP models into a small MobileNet. "
               "Then we tested it on four hundred and thirty-one hand-checked photos it had never seen. "
               "Eighty-four point five percent overall. And ninety-four percent when it's confident enough to fill the form."),
    ("routing", "Fourth, reports keep people safe. In ride mode, every route is checked against reported hazards. "
                "Flooded underpasses, open manholes, blocked roads, deep potholes. "
                "When two riders report water, routes through it are rejected, and a validated detour is shown, with the reason. "
                "And if no safe route exists, Kestrel says so."),
    ("roadvision", "Ride mode also makes the phone a co-pilot. On a mount, it runs two more models on the phone. "
                   "One finds potholes and estimates their depth. The other watches for water ahead. "
                   "Riders get spoken warnings, dashcam clips and turn-by-turn guidance, or pocket mode with just the voice. "
                   "And the camera only suggests. A person decides what becomes a report."),
    ("bharat", "And it's built for Bharat. Report in English, Hindi or Hinglish, typed or spoken. "
               "No network? The report waits on the phone and sends itself later, exactly once. "
               "It runs on budget phones, and shares straight to WhatsApp."),
    ("tech", "Under the hood, it's a TypeScript web app, with a pure Python core on AWS Lambda and DynamoDB. "
             "Every write is transactional and idempotent, so nothing is lost or counted twice. "
             "Over a hundred backend tests, plus full browser tests."),
    ("adoption", "Adoption is practical. Start with one ward. Connect the existing complaint system. "
                 "Then grow ward by ward, with public scorecards."),
    ("close", "So that's Kestrel. Report it once, track it in public, and ride around it safely until it's really fixed. Thank you!"),
]


def timeline() -> tuple[list[dict], float]:
    scenes, t = [], LEAD
    for sid, text in SCENES:
        meta = kit.speak([(VOICE, text)], BUILD / f"{sid}.wav")
        dur = meta["duration"] + TAIL
        scenes.append({"id": sid, "start": round(t, 3), "dur": round(dur, 3), "cues": meta["cues"], "wav": str(BUILD / f"{sid}.wav")})
        print(f"  {sid:<10} {dur:5.1f}s  {len(meta['cues'])} sentences", flush=True)
        t += dur
    return scenes, t + 0.6


async def render(scenes: list[dict], total: float, out: Path, stills: list[float] | None) -> None:
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", headless=True, args=["--allow-file-access-from-files"])
        page = await b.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page.on("pageerror", lambda e: print("PAGE ERROR", e))
        await page.goto((HERE / "explainer.html").as_uri())
        await page.wait_for_function("() => document.fonts.ready.then(() => [...document.images].every((i) => i.complete && i.naturalWidth))")
        await page.evaluate("tl => setTimeline(tl)", {"scenes": [{k: s[k] for k in ("id", "start", "dur", "cues")} for s in scenes]})
        cdp = await page.context.new_cdp_session(page)

        async def grab() -> bytes:
            r = await cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 92})
            return base64.b64decode(r["data"])

        if stills is not None:
            for t in stills:
                await page.evaluate(f"render({t})")
                (BUILD / f"still-{t:06.1f}.jpg").write_bytes(await grab())
            await b.close()
            return
        enc = subprocess.Popen([kit.FFMPEG, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-",
                                "-vf", "scale=out_range=tv,format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "17", str(out)], stdin=subprocess.PIPE)
        n = int(total * FPS)
        for i in range(n):
            await page.evaluate(f"render({i / FPS})")
            enc.stdin.write(await grab())
            if i % 300 == 0:
                print(f"  frame {i}/{n}", flush=True)
        enc.stdin.close()
        enc.wait()
        await b.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", nargs="*", type=float, help="render only these times (seconds) to build/still-*.jpg")
    args = ap.parse_args()
    BUILD.mkdir(exist_ok=True)
    print("voice…", flush=True)
    scenes, total = timeline()
    print(f"  total {total:.1f}s", flush=True)
    if args.stills is not None:
        times = args.stills or [s["start"] + s["dur"] * 0.85 for s in scenes]
        asyncio.run(render(scenes, total, BUILD / "x.mp4", times))
        print("stills in", BUILD)
        return
    print("frames…", flush=True)
    video = BUILD / "video.mp4"
    asyncio.run(render(scenes, total, video, None))
    kit.make_music(total, BUILD / "music.wav", bpm=92, seed=3)
    kit.mix_audio([(s["start"] + 0.15, Path(s["wav"])) for s in scenes], total, BUILD / "music.wav", BUILD / "audio.wav", music_db=-20)
    out = HERE / "Kestrel-explained.mp4"
    kit.mux(video, BUILD / "audio.wav", out)
    print("wrote", out)


if __name__ == "__main__":
    main()
