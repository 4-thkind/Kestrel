"""Hinglish / Hindi / English report extraction - deterministic rules.

Used directly when Bedrock is not configured, and as the fallback whenever a
Bedrock call times out, errors, or returns something that fails validation.
The output is only a DRAFT that the contributor reviews; it never changes
hazard state by itself.
"""
from __future__ import annotations

import re

#: Allowlist of 5 known Delhi waterlogging sites (brief 4.1). Only routing-enabled
#: hotspots can be submitted; the others are recognised so the user gets a clear message.
CATALOG: dict[str, list[str]] = {
    "MINTO_BRIDGE": ["minto bridge", "minto road", "minto", "vivekanand marg underpass", "मिंटो ब्रिज", "मिंटो"],
    "PUL_PRAHLADPUR": ["pul prahladpur", "prahladpur", "पुल प्रह्लादपुर", "प्रह्लादपुर"],
    "ZAKHIRA": ["zakhira", "zakhira underpass", "ज़खीरा", "जखीरा"],
    "TILAK_BRIDGE": ["tilak bridge", "tilak", "तिलक ब्रिज"],
    "ASHRAM_CHOWK": ["ashram chowk", "ashram", "आश्रम चौक", "आश्रम"],
}

WATER = ["paani", "pani", "water", "waterlog", "jalbharav", "jal bharav", "bhara", "bhar gaya", "dooba", "duba",
         "flood", "submerged", "पानी", "जलभराव", "भरा", "डूबा", "बाढ़"]
BLOCKED = ["band hai", "blocked", "closed", "barricade", "बंद"]
NEGATION = ["nahi", "nahin", "nhi", "no ", "not ", "dry", "sookha", "sukha", "saaf", "clear", "नहीं", "सूखा"]
PAST = ["kal", "yesterday", "pichle", "last week", "tha ", "thi ", "था", "थी", "कल"]
UNSURE = ["pata nahi", "sure nahi", "shayad", "maybe", "not sure", "पता नहीं", "शायद"]
QUALITATIVE_DEPTH = [
    ("submerged", ["gale tak", "neck", "doob gaya", "poora dooba", "गले तक"]),
    ("waist", ["kamar tak", "waist", "कमर तक", "kamar"]),
    ("knee", ["ghutne tak", "ghutne", "knee", "घुटने"]),
    ("ankle", ["takhne", "ankle", "टखने", "pair tak"]),
]
DEPTH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(foot|feet|ft|fut|cm|centimet(?:er|re)s?|inch(?:es)?|in\b|m\b|meter|metre)", re.I)
TO_CM = {"cm": 1.0, "m": 100.0, "in": 2.54, "ft": 30.48}


#: Civic category vocabulary (English, Hinglish, Hindi). Most hits wins; ties go to the earlier entry.
CATEGORY_WORDS: list[tuple[str, list[str]]] = [
    ("OPEN_MANHOLE", ["manhole", "man hole", "dhakkan", "dhakan", "gutter khula", "sewer khula", "naala khula",
                      "nala khula", "मैनहोल", "ढक्कन", "गटर"]),
    ("STREETLIGHT_OUT", ["streetlight", "street light", "light nahi", "light band", "lights band", "batti",
                         "khamba", "andhera", "dark stretch", "स्ट्रीट लाइट", "लाइट", "अंधेरा", "बत्ती"]),
    ("GARBAGE_DUMP", ["kooda", "kuda", "koodha", "kachra", "kachara", "garbage", "trash", "dump", "dhalao",
                      "waste", "कूड़ा", "कूड़े", "कचरा"]),
    ("POTHOLE", ["gaddha", "gadda", "gaddhe", "gadhe", "gadha", "khadda", "khadde", "pothole", "crater",
                 "road toota", "sadak tooti", "tooti sadak", "गड्ढा", "गड्ढे", "गड्डा"]),
    ("WATERLOGGING", WATER),
    ("BLOCKED_ROAD", ["blocked", "ped gira", "tree fallen", "fallen tree", "malba", "debris", "barricade",
                      "rasta band", "raasta band", "road band", "road closed", "पेड़ गिरा", "रास्ता बंद", "मलबा"]),
]
#: Words mined from real phrasings by ml/mine_rule_words.py (Covexcode proposes, 95%-precision filter keeps,
#: reviewed by hand; see ml/rule_words.json). They let the offline rules read Bengali, Tamil, Marathi, Punjabi
#: and Urdu reports too. Added to category detection only, never to the water-depth extractor.
MINED_WORDS: dict[str, list[str]] = {
    'POTHOLE': ["loose gravel", "surface utar gaya", "گڑھوں", "उखड़ी हुई", "खड्डे आहेत", "বড় বড় গর্ত", "பெரிய குழி"],
    'WATERLOGGING': ["paani jama hai", "paani ke andar", "paani khada", "پانی کھڑا", "अंडरपासमध्ये पाणी", "पाणी साचल्यामुळे", "ਪਾਣੀ ਖੜ੍ਹਾ", "நீர் தேங்கியுள்ளது"],
    'OPEN_MANHOLE': ["cover missing", "cover nahi", "cover nahi hai", "cover toota", "open drain", "مین ہول", "نالے کا ڈھکن", "ڈھکن غائب", "ڈھکن ٹوٹا", "کھلا مین ہول", "گٹر کا ڈھکن", "उघडं पडलंय", "गटार उघडं", "गटाराचं झाकण", "झाकण गायब", "झाकण तुटलेलं", "ढक्कन", "ढक्कन गायब", "लोखंडी झाकण", "খোলা গর্ত", "খোলা ড্রেন", "ড্রেনের ঢাকনা", "ঢাকনা চুরি", "ঢাকনা নেই", "ঢাকনা ভাঙা", "ম্যানহোলের ঢাকনা", "ਕਵਰ ਗਾਇਬ", "ਗੋਲ ਖੁੱਲ੍ਹਾ", "ਡਰੇਨ ਕਵਰ", "ਢੱਕਣ ਗਾਇਬ", "ਢੱਕਣ ਟੁੱਟਿਆ", "ਢੱਕਣ ਨਹੀਂ", "ਨਾਲੀ ਦਾ ਢੱਕਣ", "ਲੋਹੇ ਦਾ ਢੱਕਣ", "கவர் இல்ல", "சாக்கடை மூடி", "திறந்து கிடக்கு", "பெரிய ஓட்டை", "மூடி உடைந்த", "மூடி உடைந்து", "மூடி காணாமல்"],
    'BLOCKED_ROAD': ["broken concrete", "cement bags", "construction material", "fallen tree", "iron rods", "lane band", "ped gir gaya", "تعمیراتی سامان", "درخت گر گیا", "سڑک بند", "ملبہ", "ملبہ پڑا", "झाडाच्या फांद्या", "निर्माण सामग्री", "मलबा", "ইট-বালি", "গাছ পড়ে", "ਮਲਬਾ", "கிளை உடைஞ்சு", "மரக்கிளை"],
    'GARBAGE_DUMP': ["bins", "kachre ka dher", "safai nahi hui", "wrappers", "مکھیاں", "ڈھیر لگا", "کچرے کا ڈھیر", "کچرے کی گاڑی", "আবর্জনার স্তূপ", "উপচে পড়ছে", "ডাস্টবিন", "ডাস্টবিন উপচে পড়ছে", "ময়লার গাড়ি", "ਕਚਰਾ", "ਕੂੜਾ ਇਕੱਠਾ", "ਕੂੜਾ ਪਿਆ", "ਕੂੜਾ ਸੁੱਟ", "ਗੰਦਗੀ", "ਨਹੀਂ ਚੁੱਕਿਆ", "ਮੱਖੀਆਂ", "குப்பை வண்டி", "குப்பைக் குவியல்", "குப்பைத்தொட்டி"],
    'STREETLIGHT_OUT': ["pitch dark", "roshni nahi", "so dark", "unlit", "اندھیرا ہے", "روشنی نہیں", "لائٹ نہیں", "گھپ اندھیرا", "अंधार", "अंधारात", "काहीच दिसत नाही", "दिवे बंद", "स्ट्रीट लाईट", "আলো নেই", "এত অন্ধকার", "ঘুটঘুটে অন্ধকার", "জ্বলছে না", "লাইট নষ্ট", "স্ট্রিটলাইট", "ਅੰਨ੍ਹੇਰਾ", "ਬਿਲਕੁਲ ਹਨੇਰਾ", "ਬੱਤੀ", "ਹਨੇਰਾ", "இருட்டு", "ரொம்ப இருட்டா இருக்கு", "விளக்கு இல்ல", "விளக்கு எரியல"],
}
CATEGORY_WORDS = [(key, words + MINED_WORDS.get(key, [])) for key, words in CATEGORY_WORDS]
DETAIL_WORDS: dict[str, list[str]] = {
    "deep": ["gehra", "gahra", "bahut bada", "deep", "huge", "गहरा"],
    "near_school": ["school", "स्कूल", "vidyalaya"],
    "near_hospital": ["hospital", "aspatal", "अस्पताल", "clinic"],
    "major_road": ["main road", "highway", "ring road", "flyover", "marg", "मुख्य सड़क"],
    "night_hazard": ["raat", "andhera", "night", "रात"],
    "vehicles_stuck": ["phas gay", "phasi", "phase hue", "stuck", "बंद पड़", "फंस"],
}


def detect_category(text: str) -> str | None:
    low = f" {text.lower()} "
    hits = [(len(_has(low, words)), -i, key) for i, (key, words) in enumerate(CATEGORY_WORDS)]
    best = max(hits)
    return best[2] if best[0] else None


def detect_details(text: str) -> list[str]:
    low = f" {text.lower()} "
    return sorted(k for k, words in DETAIL_WORDS.items() if _has(low, words))


def depth_level(cm: float) -> str:
    """Spec 5 depth scale. Applied to a user CLAIM, never to a measurement."""
    if cm < 15:
        return "ankle"
    if cm < 30:
        return "knee"
    if cm <= 45:
        return "waist"
    return "submerged"


def _has(text: str, words: list[str]) -> list[str]:
    return [w for w in words if w in text]


def locations_in(text: str) -> list[str]:
    low = text.lower()
    return [hid for hid, aliases in CATALOG.items() if any(a in low for a in aliases)]


def extract_rules(text: str) -> dict:
    low = f" {text.lower()} "
    locations = locations_in(text)
    water = _has(low, WATER)
    unsure = bool(_has(low, UNSURE))
    negated = bool(_has(low, NEGATION)) and bool(water) and not unsure
    blocked = _has(low, BLOCKED)
    past = bool(_has(low, PAST))

    depth = None
    m = DEPTH_RE.search(text)
    if m:
        g = m.group(2).lower()
        unit = "ft" if g.startswith("f") else "cm" if g.startswith("c") else "in" if g.startswith("in") else "m"
        value = float(m.group(1))
        depth = {"phrase": m.group(0), "value": value, "unit": unit,
                 "level": depth_level(value * TO_CM[unit])}
    else:
        for level, words in QUALITATIVE_DEPTH:
            hit = _has(low, words)
            if hit:
                depth = {"phrase": hit[0], "value": None, "unit": None, "level": level}
                break

    if water and not negated:
        kind = "WATER_OBSERVED"
    elif blocked and not negated:
        kind = "ROAD_BLOCKED_REPORTED"
    elif water and negated:
        kind = "NO_WATER_OBSERVED"
    else:
        kind = "UNSURE"
    if unsure or past:
        kind = "UNSURE"

    reasons = []
    if not locations:
        reasons.append("No known place found - please pick the place.")
    elif len(locations) > 1 or " ya " in low or " or " in low:
        reasons.append("More than one place mentioned - please pick one.")
    if past:
        reasons.append("Sounds like an earlier incident, not what you see now.")
    if unsure:
        reasons.append("The report sounds unsure.")
    if not water and not blocked:
        reasons.append("No mention of water or a blocked road.")

    return draft(
        method="rules",
        location=locations[0] if len(locations) == 1 else None,
        candidates=locations,
        water=bool(water) and not negated,
        negated=negated,
        kind=kind,
        temporal="past" if past else ("unknown" if unsure else "current"),
        depth=depth,
        reasons=reasons,
        spans=[s for s in (water + blocked)[:3]] + ([depth["phrase"]] if depth else []),
    )


def draft(*, method: str, location: str | None, candidates: list[str], water: bool, negated: bool,
          kind: str, temporal: str, depth: dict | None, reasons: list[str], spans: list[str],
          model_id: str | None = None, fallback_reason: str | None = None) -> dict:
    return {
        "schemaVersion": "1.0",
        "method": method,
        "modelId": model_id,
        "fallbackReason": fallback_reason,
        "location_matched": location,
        "locationCandidates": candidates,
        "water_detected": water,
        "negated": negated,
        "suggestedKind": kind,
        "temporalReference": temporal,
        "user_claimed_depth": depth,
        "needs_clarification": bool(reasons),
        "clarificationReasons": reasons,
        "evidenceSpans": spans,
        "note": "Draft only. Review before sending. Depth is your claim, not a measurement.",
    }
