"""How well does Kestrel understand a citizen's words? Keyword rules vs Covexcode (deepseek-v4-flash).

    python ml/eval_report_understanding.py [--per-cell 20]      (keys from the repo-root .env)

1. Build a test set from a fixed grid: 6 categories x 3 languages (English, Hindi in Devanagari, romanised
   Hinglish) x 4 styles (formal, angry/casual, voice transcript, very short). Covexcode writes the texts, but
   the LABEL is the grid cell we asked for, never the model's opinion, and the writer is told not to always
   name the problem outright (people describe what they see).
2. Score both readers on every text: domain/extract.detect_category (the keyword rules Kestrel had) and
   providers/covexcode (what /v1/report-drafts now uses, with the same validation).
Every call rotates round-robin through the team keys in COVEXCODE_API_KEYS. Writes ml/understanding_set.jsonl
and ml/understanding_eval.json. Caveat, stated in the results: the same model family writes and reads the
texts, so the model's score is likely optimistic; the rules' score is a fair floor.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))
if (ROOT / ".env").exists():
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        k, _, v = line.partition("=")
        if k.strip() and not k.lstrip().startswith("#") and v:
            os.environ.setdefault(k.strip(), v.split("#")[0].strip())

from domain.categories import CATEGORIES, DETAILS  # noqa: E402
from domain.extract import detect_category  # noqa: E402
from providers import covexcode  # noqa: E402

CATS = ["POTHOLE", "WATERLOGGING", "OPEN_MANHOLE", "BLOCKED_ROAD", "GARBAGE_DUMP", "STREETLIGHT_OUT"]
LANGS = {"en": "English", "hi": "Hindi written in Devanagari script",
         "hinglish": "Hinglish (Hindi in Roman letters mixed with English)"}
REGIONAL = {"bn": "Bengali in Bengali script", "ta": "Tamil in Tamil script", "mr": "Marathi in Devanagari script",
            "pa": "Punjabi in Gurmukhi script", "ur": "Urdu in Urdu script"}
STYLES = {"formal": "a polite, formal complaint", "angry": "an angry or casual message to a friend or a WhatsApp group",
          "voice": "a voice-note transcript: fillers, run-on sentences, small speech-to-text errors",
          "short": "very short, 4 to 10 words, like a quick tap-and-send"}
DESCRIBE = {"POTHOLE": "a pothole or broken road surface", "WATERLOGGING": "water standing on a road or in an underpass",
            "OPEN_MANHOLE": "an open, missing or broken manhole or drain cover",
            "BLOCKED_ROAD": "a road blocked by a fallen tree, debris or construction",
            "GARBAGE_DUMP": "garbage piled up or not collected", "STREETLIGHT_OUT": "streetlights not working, a dark stretch"}
WRITER = """You write realistic messages that residents of Delhi send to a civic complaint app.
Return ONLY JSON: {"texts": [ ... exactly %d different strings ... ]}.
Every message describes this problem: %s. Language: %s. Style: %s.
Vary the places (real-sounding Delhi roads, markets, colonies, metro stations), the details and the wording.
Do not always name the problem directly; often describe what the person sees, smells or experiences."""

OUT_SET = ROOT / "ml" / "understanding_set.jsonl"
OUT_EVAL = ROOT / "ml" / "understanding_eval.json"
LANG_SETS = {"core": LANGS, "regional": REGIONAL}
_lock = threading.Lock()
tokens = Counter()     # per key suffix, so the split across the team is visible
calls = Counter()


def call(system: str, user: str, max_tokens: int, tries: int = 3) -> dict:
    err: Exception = RuntimeError("no attempt")
    for attempt in range(tries):
        key = covexcode.next_key()   # round-robin: every call (and every retry) goes to the next team key
        try:
            raw, u = covexcode.chat(system, user, max_tokens=max_tokens, key=key, timeout=300)
            with _lock:
                tokens[key[-4:]] += u.get("total_tokens", 0)
                calls[key[-4:]] += 1
            return raw
        except Exception as exc:  # noqa: BLE001 - rate limits and empty answers: back off and retry
            err = exc
            time.sleep(2 + 3 * attempt)
    raise err


def generate(per_cell: int, workers: int, langs: dict) -> list[dict]:
    jobs = [(c, l, s) for c, l, s in itertools.product(CATS, langs, STYLES) for _ in range(0, per_cell, 10)]

    def one(job):
        cat, lang, style = job
        n = min(10, per_cell)
        try:
            raw = call(WRITER % (n, DESCRIBE[cat], langs[lang], STYLES[style]), "Write them now.", 4000)
        except Exception:  # noqa: BLE001
            return []
        texts = [t.strip() for t in raw.get("texts", []) if isinstance(t, str) and 3 <= len(t.strip()) <= 600]
        return [{"text": t, "label": cat, "lang": lang, "style": style} for t in texts[:n]]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        items = [x for batch in pool.map(one, jobs) for x in batch]
    seen, unique = set(), []
    for it in items:
        if it["text"].lower() not in seen:
            seen.add(it["text"].lower())
            unique.append(it)
    return unique


def read_all(items: list[dict], workers: int) -> None:
    prompt = covexcode.UNDERSTAND_PROMPT % (json.dumps(sorted(CATEGORIES)), json.dumps(sorted(DETAILS)))

    def one(it):
        it["rules"] = detect_category(it["text"])
        started = time.perf_counter()
        try:
            it["model"] = covexcode.validate_understanding(call(prompt, it["text"], 1500), it["text"])["category"]
            it["modelMs"] = round((time.perf_counter() - started) * 1000)
        except Exception as exc:  # noqa: BLE001
            it["model"], it["modelError"] = None, type(exc).__name__

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, items))


def score(items: list[dict], reader: str) -> dict:
    def acc(sub):
        return round(sum(i[reader] == i["label"] for i in sub) / len(sub), 3) if sub else None

    def by(key):
        return {k: acc([i for i in items if i[key] == k]) for k in sorted({i[key] for i in items})}
    return {"accuracy": acc(items), "noAnswer": round(sum(i[reader] is None for i in items) / len(items), 3),
            "byLanguage": by("lang"), "byStyle": by("style"), "byCategory": by("label")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-cell", type=int, default=20)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--reuse", action="store_true", help="re-score the existing understanding_set.jsonl")
    ap.add_argument("--langs", choices=list(LANG_SETS), default="core",
                    help="core: English, Hindi, Hinglish; regional: Bengali, Tamil, Marathi, Punjabi, Urdu")
    args = ap.parse_args()
    global OUT_SET, OUT_EVAL
    if args.langs != "core":
        OUT_SET = OUT_SET.with_name(f"understanding_set_{args.langs}.jsonl")
        OUT_EVAL = OUT_EVAL.with_name(f"understanding_eval_{args.langs}.json")
    langs = LANG_SETS[args.langs]
    team = covexcode.team_keys()
    assert team, "no Covexcode key: set COVEXCODE_API_KEYS in .env"
    t0 = time.time()
    if args.reuse and OUT_SET.exists():
        items = [json.loads(line) for line in OUT_SET.read_text(encoding="utf-8").splitlines()]
    else:
        items = generate(args.per_cell, args.workers, langs)
        print(f"generated {len(items)} texts in {time.time() - t0:.0f}s · tokens {sum(tokens.values()):,} · {dict(calls)}", flush=True)
    read_all(items, args.workers)
    OUT_SET.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
    ms = sorted(i["modelMs"] for i in items if "modelMs" in i)
    result = {
        "model": covexcode.model_id(), "texts": len(items),
        "grid": {"categories": CATS, "languages": list(langs), "styles": list(STYLES)},
        "rules": score(items, "rules"), "covexcode": score(items, "model"),
        "covexcodeLatencyMs": {"median": ms[len(ms) // 2], "p90": ms[int(len(ms) * 0.9)]} if ms else None,
        "tokensUsed": sum(tokens.values()), "teamKeys": len(team),
        "callsPerKey": {f"key {i + 1}": calls[k[-4:]] for i, k in enumerate(team)},
        "caveat": "The same model family wrote and read the texts, so the model score is likely optimistic. Labels are the requested grid cell.",
    }
    OUT_EVAL.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"texts": result["texts"], "tokens": result["tokensUsed"], "rules": result["rules"]["accuracy"],
                      "covexcode": result["covexcode"]["accuracy"], "callsPerKey": result["callsPerKey"]}), flush=True)


if __name__ == "__main__":
    main()
