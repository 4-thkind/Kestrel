"""First-pass review of every Hindi UI string with Covexcode (keys rotate per call), before a fluent speaker.

    python scripts/review_hindi.py            -> scripts/hindi_review.json  (nothing is edited automatically)

Collects every English/Hindi pair from app/src/civic/*.ts (L("en", "hi") calls) and app/src/flood/i18n.ts
({ en: "...", hi: "..." } entries), sends them in batches, and asks only for real problems: wrong meaning,
grammar, unnatural or overly formal phrasing for a phone app, and inconsistent terms across screens.
A suggestion is dropped automatically if it changes a ${...} placeholder or a number.
"""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ml"))
from eval_report_understanding import call  # noqa: E402  (loads .env, rotates team keys)

L_CALL = re.compile(r'L\(\s*(["`])((?:\\.|(?!\1).)*)\1\s*,\s*(["`])((?:\\.|(?!\3).)*)\3\s*[,)]', re.S)
TABLE = re.compile(r'en:\s*"((?:\\.|[^"\\])*)"\s*,\s*hi:\s*"((?:\\.|[^"\\])*)"', re.S)
PROMPT = """You are a fluent Hindi editor reviewing the Hindi text of a civic-issue phone app used across Delhi
(reporting potholes, garbage, streetlights, waterlogging; ward officers; route planning for riders).
For each item you get the English source and the current Hindi. Flag ONLY real problems: wrong or missing
meaning, grammar or spelling errors, unnatural or overly formal phrasing for a simple phone app, or a term
used inconsistently with how this app says it elsewhere. Keep ${...} placeholders, numbers, punctuation style
and roughly the same length. Return ONLY JSON:
{"fixes": [{"id": <id>, "hi": "<corrected Hindi>", "why": "<short reason in English>"}]}
Return an empty list if everything is fine. Do not rewrite strings that are already correct."""


def pairs() -> list[dict]:
    out = []
    for f in sorted((ROOT / "app" / "src" / "civic").glob("*.ts")):
        for m in L_CALL.finditer(f.read_text(encoding="utf-8")):
            out.append({"file": str(f.relative_to(ROOT)), "en": m.group(2), "hi": m.group(4)})
    i18n = ROOT / "app" / "src" / "flood" / "i18n.ts"
    for m in TABLE.finditer(i18n.read_text(encoding="utf-8")):
        out.append({"file": str(i18n.relative_to(ROOT)), "en": m.group(1), "hi": m.group(2)})
    seen, uniq = set(), []
    for p in out:
        if p["hi"] not in seen and re.search(r"[\u0900-\u097F]", p["hi"]):
            seen.add(p["hi"])
            uniq.append({**p, "id": len(uniq)})
    return uniq


def safe(old: str, new: str) -> bool:
    keep = lambda t: (sorted(re.findall(r"\$\{[^}]*\}", t)), sorted(re.findall(r"\d+", t)))  # noqa: E731
    return bool(new.strip()) and new != old and keep(old) == keep(new) and len(new) <= 2 * len(old) + 20


def main() -> None:
    items = pairs()
    batches = [items[i:i + 25] for i in range(0, len(items), 25)]

    def review(batch):
        payload = json.dumps([{"id": p["id"], "en": p["en"], "hi": p["hi"]} for p in batch], ensure_ascii=False)
        try:
            return call(PROMPT, payload, 16000).get("fixes", [])
        except Exception:  # noqa: BLE001
            return []

    with ThreadPoolExecutor(max_workers=6) as pool:
        fixes = [f for batch in pool.map(review, batches) for f in batch if isinstance(f, dict)]
    by_id = {p["id"]: p for p in items}
    out = []
    for f in fixes:
        p = by_id.get(f.get("id"))
        if p and isinstance(f.get("hi"), str) and safe(p["hi"], f["hi"]):
            out.append({**p, "suggested": f["hi"], "why": str(f.get("why", ""))[:200]})
    (ROOT / "scripts" / "hindi_review.json").write_text(json.dumps({"strings": len(items), "flagged": len(out), "fixes": out},
                                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(items)} Hindi strings reviewed, {len(out)} flagged -> scripts/hindi_review.json")


if __name__ == "__main__":
    main()
