"""Covexcode integration without the network: validation, fallback, caching, officer-only briefs."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from test_civic import Base, officer  # noqa: E402
from test_scenarios import who  # noqa: E402

from domain.validation import ApiError  # noqa: E402
from providers import covexcode  # noqa: E402

TEXT = "Lajpat Nagar school ke saamne manhole ka dhakkan gayab hai, raat ko andhera"


class Validation(unittest.TestCase):
    def test_keeps_only_kestrel_lists_and_quoted_place(self) -> None:
        out = covexcode.validate_understanding({"category": "OPEN_MANHOLE", "details": ["near_school", "flying_cars"],
                                                "place": "Lajpat Nagar", "summary_en": " Open manhole. ",
                                                "summary_hi": "खुला मैनहोल।"}, TEXT)
        self.assertEqual(out["category"], "OPEN_MANHOLE")
        self.assertEqual(out["details"], ["near_school"])
        self.assertEqual(out["place"], "Lajpat Nagar")
        self.assertEqual(out["summaryEn"], "Open manhole.")

    def test_invented_place_is_dropped(self) -> None:
        out = covexcode.validate_understanding({"category": None, "details": [], "place": "Connaught Place"}, TEXT)
        self.assertIsNone(out["place"])

    def test_unknown_category_rejected(self) -> None:
        with self.assertRaises(ValueError):
            covexcode.validate_understanding({"category": "ALIENS", "details": []}, TEXT)


class Drafts(Base):
    def setUp(self) -> None:
        super().setUp()
        covexcode._cache.clear()

    def test_without_key_rules_stand(self) -> None:
        with mock.patch.dict(os.environ, {"COVEXCODE_API_KEY": "", "COVEXCODE_API_KEYS": ""}):
            d = self.svc.report_draft({"text": TEXT}, who("a"))
        self.assertEqual(d["understanding"], {"method": "rules"})
        self.assertEqual(d["suggestedCategory"], "OPEN_MANHOLE")

    def test_model_answer_used_and_cached(self) -> None:
        answer = ({"category": "OPEN_MANHOLE", "details": ["near_school", "night_hazard"], "place": "Lajpat Nagar",
                   "summary_en": "Open manhole near a school.", "summary_hi": "स्कूल के पास खुला मैनहोल।"}, {})
        with mock.patch.dict(os.environ, {"COVEXCODE_API_KEY": "test", "COVEXCODE_API_KEYS": ""}), \
                mock.patch.object(covexcode, "chat", return_value=answer) as chat:
            d = self.svc.report_draft({"text": TEXT}, who("a"))
            self.svc.report_draft({"text": TEXT}, who("b"))
        self.assertEqual(chat.call_count, 1, "same text is not billed twice")
        self.assertEqual(d["understanding"]["method"], "covexcode")
        self.assertEqual(d["suggestedDetails"], ["near_school", "night_hazard"])

    def test_model_failure_falls_back(self) -> None:
        with mock.patch.dict(os.environ, {"COVEXCODE_API_KEY": "test", "COVEXCODE_API_KEYS": ""}), \
                mock.patch.object(covexcode, "chat", side_effect=TimeoutError("slow")):
            d = self.svc.report_draft({"text": TEXT}, who("a"))
        self.assertEqual(d["understanding"], {"method": "rules"})
        self.assertEqual(d["suggestedCategory"], "OPEN_MANHOLE")


class Briefs(Base):
    def test_brief_is_officer_only_and_uses_descriptions(self) -> None:
        _, r = self.report("a", category="POTHOLE", description="Deep pothole near the school gate")
        iid = r["issueId"]
        with self.assertRaises(ApiError):
            self.civic.brief(iid, who("a"))
        answer = ({"brief_en": "Citizens report a deep pothole near a school.", "brief_hi": "गहरा गड्ढा।"}, {})
        with mock.patch.dict(os.environ, {"COVEXCODE_API_KEY": "test", "COVEXCODE_API_KEYS": ""}), \
                mock.patch.object(covexcode, "chat", return_value=answer) as chat:
            out = self.civic.brief(iid, officer())
        self.assertEqual(out["brief"]["en"], "Citizens report a deep pothole near a school.")
        self.assertIn("Deep pothole near the school gate", chat.call_args.args[1])

    def test_pulse_uses_structured_data_only(self) -> None:
        self.report("a", category="POTHOLE", description="secret personal note")
        answer = ({"pulse_en": "One urgent pothole.", "pulse_hi": "एक गड्ढा।"}, {})
        with mock.patch.dict(os.environ, {"COVEXCODE_API_KEY": "test", "COVEXCODE_API_KEYS": ""}),                 mock.patch.object(covexcode, "chat", return_value=answer) as chat:
            out = self.civic.pulse("W-LN")
        self.assertEqual(out["pulse"]["en"], "One urgent pothole.")
        self.assertNotIn("secret personal note", chat.call_args.args[1], "no citizen free text in a public summary")


if __name__ == "__main__":
    unittest.main()
