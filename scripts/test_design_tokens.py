"""Tests for scripts/design_tokens.py and for the palette decision recorded in design/tokens.json (T1: Petrol, #15).

Run: python3 -I scripts/test_design_tokens.py
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import design_tokens as dt  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
REAL = json.loads((ROOT / "design" / "tokens.json").read_text(encoding="utf-8"))
PAGE = (ROOT / "docs" / "product" / "wireframes" / "wireframes.html").read_text(encoding="utf-8")

# Petrol as the owner saw it in the palette comparison (issue #15, T1): the 7 roles that page lists, light and dark.
PETROL = {
    "light": {
        "primary": "#006878",
        "primaryContainer": "#A7EDFF",
        "secondaryContainer": "#D4E6E8",
        "tertiaryContainer": "#FFDEAE",
        "surface": "#F6FAFB",
        "surfaceContainerLow": "#F0F4F5",
        "error": "#BA1A1A",
    },
    "dark": {
        "primary": "#7DD3E7",
        "primaryContainer": "#004E5B",
        "secondaryContainer": "#394A4B",
        "tertiaryContainer": "#604100",
        "surface": "#0F1415",
        "surfaceContainerLow": "#181C1D",
        "error": "#FFB4AB",
    },
}
# The retired teal palette: none of it may remain in the tokens or on the wireframes page.
TEAL = ["#1F6A5F", "#B4EFE2", "#CCE8E1", "#F6FAF8", "#F0F4F2", "#8ED4C6", "#005046", "#334B46", "#0F1513", "#171D1B", "#6F7975"]


class Contrast(unittest.TestCase):
    def test_known_ratios(self):
        self.assertAlmostEqual(dt.contrast("#000000", "#FFFFFF"), 21.0, places=2)
        self.assertAlmostEqual(dt.contrast("#FFFFFF", "#000000"), 21.0, places=2)
        self.assertAlmostEqual(dt.contrast("#777777", "#FFFFFF"), 4.48, places=2)
        self.assertAlmostEqual(dt.contrast("#123456", "#123456"), 1.0, places=2)


class Check(unittest.TestCase):
    def test_the_real_tokens_pass(self):
        self.assertEqual(dt.check(REAL), [])

    def test_a_failing_contrast_pair_is_reported_in_the_theme_that_fails(self):
        bad = copy.deepcopy(REAL)
        bad["color"]["dark"]["onSurface"] = bad["color"]["dark"]["surface"]
        found = dt.check(bad)
        self.assertTrue(any("dark" in f and "onSurface on surface" in f for f in found), found)
        self.assertFalse(any(f.startswith("light") for f in found), found)

    def test_a_pair_just_under_its_minimum_fails_and_at_the_minimum_passes(self):
        toks = {"color": {th: {"a": "#777777", "b": "#FFFFFF"} for th in ("light", "dark")}, "contrastPairs": [{"fg": "a", "bg": "b", "min": 4.5}]}
        self.assertEqual(len(dt.check(toks)), 2)  # 4.48 < 4.5, once per theme
        for th in toks["color"]:
            toks["color"][th]["a"] = "#767676"  # 4.54
        self.assertEqual(dt.check(toks), [])

    def test_a_role_in_one_theme_only_is_reported(self):
        bad = copy.deepcopy(REAL)
        del bad["color"]["dark"]["tertiary"]
        self.assertTrue(any("tertiary" in f and "dark" in f for f in dt.check(bad)), dt.check(bad))

    def test_a_pair_that_names_an_unknown_role_is_reported(self):
        bad = copy.deepcopy(REAL)
        bad["contrastPairs"].append({"fg": "onNothing", "bg": "surface", "min": 4.5})
        self.assertTrue(any("onNothing" in f for f in dt.check(bad)), dt.check(bad))

    def test_a_color_that_is_not_six_digit_upper_case_hex_is_reported(self):
        for value in ("#fff", "#1f6a5f", "teal", "#12345", "#1234567", "rgb(0,0,0)", "", None):
            bad = copy.deepcopy(REAL)
            bad["color"]["light"]["primary"] = value
            self.assertTrue(any("primary" in f for f in dt.check(bad)), value)

    def test_a_pair_with_a_weaker_minimum_than_aa_is_reported(self):
        bad = copy.deepcopy(REAL)
        bad["contrastPairs"][0]["min"] = 3.0  # onPrimary on primary is text: AA needs 4.5
        self.assertTrue(any("onPrimary on primary" in f and "minimum" in f for f in dt.check(bad)), dt.check(bad))

    def test_the_outline_pair_keeps_the_non_text_minimum(self):
        pairs = {(p["fg"], p["bg"]): p["min"] for p in REAL["contrastPairs"]}
        self.assertEqual(pairs[("outline", "surface")], 3.0)

    def test_main_returns_zero_for_the_real_tokens_and_one_for_a_bad_file(self):
        self.assertEqual(dt.main([]), 0)
        bad = copy.deepcopy(REAL)
        bad["color"]["light"]["onPrimary"] = bad["color"]["light"]["primary"]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.json"
            p.write_text(json.dumps(bad), encoding="utf-8")
            self.assertEqual(dt.main([str(p)]), 1)


class PetrolDecision(unittest.TestCase):
    """T1 is decided: the app palette is Petrol (owner, 2026-11-17, issue #15 comment 6956773225)."""

    def test_the_roles_the_owner_saw_are_petrol_in_both_themes(self):
        for theme, roles in PETROL.items():
            for role, value in roles.items():
                self.assertEqual(REAL["color"][theme][role], value, f"{theme}.{role}")

    def test_inverse_primary_is_the_primary_of_the_other_theme(self):
        self.assertEqual(REAL["color"]["light"]["inversePrimary"], REAL["color"]["dark"]["primary"])
        self.assertEqual(REAL["color"]["dark"]["inversePrimary"], REAL["color"]["light"]["primary"])

    def test_no_teal_value_is_left_in_the_tokens(self):
        text = json.dumps(REAL).upper()
        for teal in TEAL:
            self.assertNotIn(teal, text)

    def test_the_tokens_say_t1_is_decided_and_no_longer_open(self):
        status = REAL["meta"]["status"]
        self.assertIn("T1", status)
        self.assertIn("Petrol", status)
        self.assertNotIn("open: T1", status)

    def test_tokens_stay_theme_swappable_roles_only_and_no_palette_named_keys(self):
        # A user theme (post-v1) swaps whole color sets, so tokens are Material roles and nothing else names a palette.
        self.assertEqual(set(REAL["color"]), {"light", "dark"})
        self.assertEqual(set(REAL["color"]["light"]), set(REAL["color"]["dark"]))
        self.assertIn("theme-swappable", REAL["meta"]["notes"])
        for key in json.dumps(REAL["color"]).lower().split('"'):
            self.assertNotIn("petrol", key)
            self.assertNotIn("teal", key)


class WireframesPage(unittest.TestCase):
    def test_the_page_hard_codes_no_teal_value(self):
        text = PAGE.upper()
        for teal in TEAL:
            self.assertNotIn(teal, text)

    def test_the_page_lists_t1_as_decided_not_open(self):
        self.assertNotIn("open: T1", PAGE)
        self.assertNotIn("T1, T2", PAGE)
        self.assertIn("T1 decided: Petrol", PAGE)


if __name__ == "__main__":
    unittest.main()
