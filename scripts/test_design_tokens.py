"""Tests for scripts/design_tokens.py and for the palette decision recorded in design/tokens.json (T1: Petrol, #15).

Run: python3 -I scripts/test_design_tokens.py
"""

import contextlib
import copy
import io
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


# Every Material 3 ColorScheme color role (issue #190). Written out here on purpose: the gate's own list must match it.
M3_ROLES = (
    "primary", "onPrimary", "primaryContainer", "onPrimaryContainer",
    "inversePrimary",
    "secondary", "onSecondary", "secondaryContainer", "onSecondaryContainer",
    "tertiary", "onTertiary", "tertiaryContainer", "onTertiaryContainer",
    "background", "onBackground",
    "surface", "onSurface", "surfaceVariant", "onSurfaceVariant", "surfaceTint",
    "inverseSurface", "inverseOnSurface",
    "error", "onError", "errorContainer", "onErrorContainer",
    "outline", "outlineVariant", "scrim",
    "surfaceBright", "surfaceDim",
    "surfaceContainer", "surfaceContainerHigh", "surfaceContainerHighest", "surfaceContainerLow", "surfaceContainerLowest",
    "primaryFixed", "primaryFixedDim", "onPrimaryFixed", "onPrimaryFixedVariant",
    "secondaryFixed", "secondaryFixedDim", "onSecondaryFixed", "onSecondaryFixedVariant",
    "tertiaryFixed", "tertiaryFixedDim", "onTertiaryFixed", "onTertiaryFixedVariant",
)


class M3Roles(unittest.TestCase):
    def test_the_gate_requires_every_m3_role(self):
        self.assertEqual(set(dt.REQUIRED_ROLES), set(M3_ROLES))

    def test_the_real_tokens_define_every_m3_role_in_both_themes(self):
        for theme in ("light", "dark"):
            self.assertEqual(sorted(set(M3_ROLES) - set(REAL["color"][theme])), [], theme)

    def test_a_missing_m3_role_is_reported_in_the_theme_that_lacks_it(self):
        for role in M3_ROLES:
            for theme in ("light", "dark"):
                bad = copy.deepcopy(REAL)
                bad["color"][theme].pop(role, None)
                with self.subTest(role=role, theme=theme):
                    found = dt.check(bad)
                    self.assertTrue(any(theme in f and role in f and "M3" in f for f in found), found)

    def test_a_role_missing_from_both_themes_is_still_reported(self):
        bad = copy.deepcopy(REAL)
        for theme in ("light", "dark"):
            bad["color"][theme].pop("surfaceTint", None)
        self.assertTrue(any("surfaceTint" in f and "M3" in f for f in dt.check(bad)))

    def test_each_fixed_variant_role_is_gated_on_both_fixed_backgrounds(self):
        for palette in ("Primary", "Secondary", "Tertiary"):
            fg, low = f"on{palette}FixedVariant", palette.lower()
            for bg in (f"{low}Fixed", f"{low}FixedDim"):
                with self.subTest(pair=(fg, bg)):
                    self.assertIn((fg, bg), dt.REQUIRED_PAIRS)
                    self.assertTrue(any(p["fg"] == fg and p["bg"] == bg for p in REAL["contrastPairs"]))

    def test_an_extra_non_m3_role_is_not_a_finding(self):
        ok = copy.deepcopy(REAL)
        for theme in ("light", "dark"):
            ok["color"][theme]["customAccent"] = "#123456"
        self.assertEqual(dt.check(ok), [])


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
        self.assertEqual(len(dt.check(toks, required=(), roles_required=())), 2)  # 4.48 < 4.5, once per theme
        for th in toks["color"]:
            toks["color"][th]["a"] = "#767676"  # 4.54
        self.assertEqual(dt.check(toks, required=(), roles_required=()), [])

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

    def test_an_empty_pair_list_fails_the_gate(self):
        bad = copy.deepcopy(REAL)
        bad["contrastPairs"] = []
        self.assertTrue(dt.check(bad))

    def test_deleting_any_one_pair_fails_the_gate(self):
        for i, pair in enumerate(REAL["contrastPairs"]):
            bad = copy.deepcopy(REAL)
            del bad["contrastPairs"][i]
            found = dt.check(bad)
            self.assertTrue(any(pair["fg"] in f and pair["bg"] in f and "missing" in f for f in found), (pair, found))

    def test_a_duplicate_of_another_pair_does_not_stand_in_for_a_required_one(self):
        bad = copy.deepcopy(REAL)
        bad["contrastPairs"][0] = {"fg": "onSurface", "bg": "surface", "min": 4.5}  # duplicate of another pair
        self.assertTrue(any("onPrimary on primary" in f and "missing" in f for f in dt.check(bad)))

    def test_main_returns_zero_for_the_real_tokens_and_one_for_a_bad_file(self):
        self.assertEqual(dt.main([]), 0)
        bad = copy.deepcopy(REAL)
        bad["color"]["light"]["onPrimary"] = bad["color"]["light"]["primary"]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.json"
            p.write_text(json.dumps(bad), encoding="utf-8")
            self.assertEqual(dt.main([str(p)]), 1)


def _run_main(content: bytes | None) -> tuple[int, str]:
    """Run main() on a temp file holding content (None: the file does not exist); return (status, stdout). Any exception fails the test."""
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.json"
        if content is not None:
            p.write_bytes(content)
        with contextlib.redirect_stdout(out):
            status = dt.main([str(p)])
    return status, out.getvalue()


MALFORMED = {
    "top level is a list": lambda t: [],
    "top level is a string": lambda t: "tokens",
    "top level is null": lambda t: None,
    "color is missing": lambda t: t.pop("color") and t,
    "contrastPairs is missing": lambda t: t.pop("contrastPairs") and t,
    "color is a list": lambda t: t.update(color=[]) or t,
    "color is null": lambda t: t.update(color=None) or t,
    "the dark theme is missing": lambda t: t["color"].pop("dark") and t,
    "the light theme is missing": lambda t: t["color"].pop("light") and t,
    "color is empty": lambda t: t.update(color={}) or t,
    "a theme is a list": lambda t: t["color"].update(light=["#FFFFFF"]) or t,
    "a theme is null": lambda t: t["color"].update(dark=None) or t,
    "contrastPairs is an object": lambda t: t.update(contrastPairs={}) or t,
    "contrastPairs is null": lambda t: t.update(contrastPairs=None) or t,
    "a pair is a string": lambda t: t["contrastPairs"].append("onPrimary on primary") or t,
    "a pair is null": lambda t: t["contrastPairs"].append(None) or t,
    "a pair has no fg": lambda t: t["contrastPairs"][0].pop("fg") and t,
    "a pair has no bg": lambda t: t["contrastPairs"][0].pop("bg") and t,
    "a pair has no min": lambda t: t["contrastPairs"][0].pop("min") and t,
    "a pair fg is a number": lambda t: t["contrastPairs"][0].update(fg=7) or t,
    "a pair bg is a list": lambda t: t["contrastPairs"][0].update(bg=["surface"]) or t,
    "a pair min is a string": lambda t: t["contrastPairs"][0].update(min="4.5") or t,
    "a pair min is null": lambda t: t["contrastPairs"][0].update(min=None) or t,
    "a pair min is NaN": lambda t: t["contrastPairs"][0].update(min=float("nan")) or t,
    "a pair min is infinite": lambda t: t["contrastPairs"][0].update(min=float("inf")) or t,
    "a pair min is a huge integer": lambda t: t["contrastPairs"][0].update(min=10**400) or t,
    "a pair min is a boolean": lambda t: t["contrastPairs"][0].update(min=True) or t,
}


class Malformed(unittest.TestCase):
    """A malformed token file is a finding (status 1, one line, no traceback), never an exception."""

    def test_a_malformed_structure_is_reported_by_check_not_raised(self):
        for name, mutate in MALFORMED.items():
            tokens = copy.deepcopy(REAL)
            tokens = mutate(tokens)
            with self.subTest(name):
                found = dt.check(tokens)
                self.assertTrue(found, "no finding")
                self.assertTrue(all(isinstance(f, str) and "\n" not in f for f in found), found)

    def test_main_reports_each_malformed_structure_with_status_one_and_the_path(self):
        for name, mutate in MALFORMED.items():
            with self.subTest(name):
                status, out = _run_main(json.dumps(mutate(copy.deepcopy(REAL))).encode())
                self.assertEqual(status, 1)
                self.assertIn("t.json", out)
                self.assertNotIn("Traceback", out)

    def test_main_reports_a_file_that_is_not_json(self):
        for content in (b"", b"{", b"not json", b'{"color": }', b"\xff\xfe\x00bad"):
            with self.subTest(content=content):
                status, out = _run_main(content)
                self.assertEqual(status, 1)
                self.assertIn("t.json", out)

    def test_main_reports_a_missing_file(self):
        status, out = _run_main(None)
        self.assertEqual(status, 1)
        self.assertIn("t.json", out)

    def test_main_reports_json_that_the_parser_refuses_to_read_without_a_traceback(self):
        too_many_digits = b'{"min": ' + b"9" * 5000 + b"}"  # over Python's int digit limit: ValueError, not JSONDecodeError
        too_deep = b"[" * 200_000 + b"]" * 200_000  # RecursionError
        for name, content in (("an integer over the digit limit", too_many_digits), ("nesting too deep to parse", too_deep)):
            with self.subTest(name):
                status, out = _run_main(content)
                self.assertEqual(status, 1)
                self.assertIn("t.json", out)

    def test_an_extra_key_and_an_int_or_float_minimum_are_not_findings(self):
        for minimum in (5, 5.5):
            tokens = copy.deepcopy(REAL)
            tokens["extra"] = {"anything": [1, 2]}
            tokens["contrastPairs"][0]["min"] = minimum  # above AA and below the real ratio
            with self.subTest(minimum=minimum):
                self.assertEqual(dt.check(tokens), [])


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
