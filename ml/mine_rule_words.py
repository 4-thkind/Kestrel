"""Teach Kestrel's offline keyword rules new words, using Covexcode, and prove they help.

    python ml/mine_rule_words.py          (after ml/eval_report_understanding.py; keys from .env)

The keyword rules (backend/src/domain/extract.py) are what runs with no network and no model. They miss
reports phrased in ways nobody wrote down ("badbu aa rahi hai", "dhakkan gayab"). This script:
1. splits ml/understanding_set.jsonl (+ the regional set if present) into a mining half and a held-out half;
2. shows Covexcode the mining-half texts the rules got wrong, category by category, and asks for short words or
   phrases that people actually used (every candidate must appear verbatim in at least one of those texts);
3. keeps a candidate only if, on the mining half, it fires on 3+ texts and is right at least 95% of the time;
4. scores old rules vs old+new rules on the HELD-OUT half, which nothing above has seen.
Writes ml/rule_words.json (accepted words per category + before/after accuracy). Merging the words into
CATEGORY_WORDS is a reviewed code change, not automatic.
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_report_understanding import CATS, call  # noqa: E402  (loads .env, rotates team keys)

from domain.extract import CATEGORY_WORDS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MINER = """You help a keyword matcher recognise civic complaints from Delhi. Below are citizen messages that all
describe: %s. A simple matcher missed them. Return ONLY JSON {"phrases": [...]} with up to 40 SHORT words or
phrases (1-3 words, lower case, any script) that strongly signal this problem and appear verbatim in the
messages. Prefer words a different person would also use. No place names, no generic words like "road",
"problem", "please", "sadak", "bahut"."""


def rules(text: str, words: list[tuple[str, list[str]]]) -> str | None:
    low = f" {text.lower()} "
    hits = [(sum(w in low for w in ws), -i, key) for i, (key, ws) in enumerate(words)]
    best = max(hits)
    return best[2] if best[0] else None


def main() -> None:
    items = []
    for name in ("understanding_set.jsonl", "understanding_set_regional.jsonl"):
        p = ROOT / "ml" / name
        if p.exists():
            items += [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]
    random.Random(7).shuffle(items)
    mine, held = items[: len(items) // 2], items[len(items) // 2:]
    describe = {c: c.replace("_", " ").lower() for c in CATS}

    def ask(cat: str) -> list[str]:
        missed = [i["text"] for i in mine if i["label"] == cat and rules(i["text"], CATEGORY_WORDS) != cat]
        out: list[str] = []
        for k in range(0, min(len(missed), 320), 40):    # several batches per category
            chunk = missed[k:k + 40]
            try:
                raw = call(MINER % describe[cat], "\n".join(f"- {t}" for t in chunk), 16000)   # ~3k hidden reasoning tokens first
            except Exception:  # noqa: BLE001
                continue
            joined = "\n".join(chunk).lower()
            out += [p.strip().lower() for p in raw.get("phrases", []) if isinstance(p, str) and 2 < len(p.strip()) <= 30
                    and p.strip().lower() in joined]
        return sorted(set(out))

    with ThreadPoolExecutor(max_workers=len(CATS)) as pool:
        candidates = dict(zip(CATS, pool.map(ask, CATS)))

    accepted: dict[str, list[str]] = defaultdict(list)
    for cat, phrases in candidates.items():
        for ph in phrases:
            fired = [i for i in mine if ph in f" {i['text'].lower()} "]
            if len(fired) >= 3 and sum(i["label"] == cat for i in fired) / len(fired) >= 0.95:
                accepted[cat].append(ph)
    new_words = [(k, ws + accepted.get(k, [])) for k, ws in CATEGORY_WORDS]

    def acc(words, sub):
        return round(sum(rules(i["text"], words) == i["label"] for i in sub) / len(sub), 3)

    by_lang = sorted({i["lang"] for i in held})
    result = {
        "texts": {"mining": len(mine), "heldOut": len(held)},
        "candidates": {k: len(v) for k, v in candidates.items()},
        "accepted": dict(accepted),
        "heldOutAccuracy": {"before": acc(CATEGORY_WORDS, held), "after": acc(new_words, held)},
        "heldOutByLanguage": {l: {"before": acc(CATEGORY_WORDS, [i for i in held if i["lang"] == l]),
                                  "after": acc(new_words, [i for i in held if i["lang"] == l])} for l in by_lang},
        "rule": "kept if it fires on 3+ mining texts with >= 95% precision; scored on the held-out half only",
    }
    (ROOT / "ml" / "rule_words.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("heldOutAccuracy", "candidates")}, ensure_ascii=False))
    print({k: len(v) for k, v in accepted.items()})


if __name__ == "__main__":
    main()
