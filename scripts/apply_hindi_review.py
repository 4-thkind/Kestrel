"""Apply the reviewed subset of scripts/hindi_review.json to the app's Hindi strings.

    python scripts/apply_hindi_review.py

SKIP lists suggestions a human rejected; OVERRIDE replaces a suggestion with a human choice. Each change
replaces the exact quoted Hindi string ("..." or `...`) in app/src, re-escaping quotes for its delimiter.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {265}  # "ऑटो-सुरक्षित" would add a safety claim the app deliberately avoids
OVERRIDE = {
    137: "मेरी लोकेशन लें",                                  # same wording as the planner button (247)
    22: "लोकेशन बंद है या उपलब्ध नहीं।",                      # consistent with 121
    121: "लोकेशन बंद है या उपलब्ध नहीं। नक्शे पर समस्या की जगह टैप करें।",
}


def main() -> None:
    review = json.loads((ROOT / "scripts" / "hindi_review.json").read_text(encoding="utf-8"))
    files = sorted((ROOT / "app" / "src").rglob("*.ts"))
    texts = {f: f.read_text(encoding="utf-8") for f in files}
    applied, missing = 0, []
    for fix in review["fixes"]:
        if fix["id"] in SKIP:
            continue
        new = OVERRIDE.get(fix["id"], fix["suggested"])
        old = fix["hi"]
        hit = False
        for f, s in texts.items():
            for q in ('"', "`"):
                needle = f"{q}{old}{q}"
                if needle in s:
                    body = new.replace("\\" + q, q).replace(q, "\\" + q) if q == '"' else new
                    s = s.replace(needle, f"{q}{body}{q}")
                    hit = True
            texts[f] = s
        applied += hit
        if not hit:
            missing.append(fix["id"])
    for f, s in texts.items():
        if s != f.read_text(encoding="utf-8"):
            f.write_text(s, encoding="utf-8")
    print(f"applied {applied}, skipped {len(SKIP)}, not found {missing}")


if __name__ == "__main__":
    main()
