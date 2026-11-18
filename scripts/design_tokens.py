"""Checks on design/tokens.json: colors are well-formed, both themes define the same roles, and every contrast pair passes.

Usage: python3 -I scripts/design_tokens.py [tokens.json]   (default: design/tokens.json)
Exit status: 0 clean, 1 findings (one line per finding). A file that is missing, is not JSON or has a malformed structure
(a wrong type, a missing key) is reported as a finding too, never as a traceback.

Rules: every color is #RRGGBB in upper case; the light and dark themes have exactly the same roles (so a theme can be swapped
whole, post-v1); every pair in REQUIRED_PAIRS is listed in contrastPairs (an empty or shortened list fails); every
contrastPairs entry names roles that exist, keeps the WCAG AA minimum (4.5 for text, 3.0 for the outline pair) and meets
that minimum in both themes. Thresholds are never read from anywhere that could weaken them: a pair may ask for
more than AA, never less.
"""

import json
import math
import re
import sys
from pathlib import Path

TOKENS = Path(__file__).resolve().parent.parent / "design" / "tokens.json"
HEX = re.compile(r"#[0-9A-F]{6}")
AA_TEXT = 4.5
AA_NON_TEXT = 3.0
NON_TEXT_PAIRS = {("outline", "surface")}
# The pairs the gate always checks: deleting one from tokens.json (or emptying the list) fails, so the gate cannot be weakened there.
REQUIRED_PAIRS = (
    ("onPrimary", "primary"),
    ("onPrimaryContainer", "primaryContainer"),
    ("onSecondaryContainer", "secondaryContainer"),
    ("onTertiaryContainer", "tertiaryContainer"),
    ("onErrorContainer", "errorContainer"),
    ("onError", "error"),
    ("onSurface", "surface"),
    ("onSurfaceVariant", "surface"),
    ("onSurfaceVariant", "surfaceContainerHigh"),
    ("onSurfaceVariant", "surfaceContainerLow"),
    ("onSurfaceVariant", "surfaceContainer"),
    ("onSurface", "surfaceContainerLow"),
    ("onSurface", "surfaceContainer"),
    ("onSurface", "surfaceContainerHigh"),
    ("onSurface", "surfaceContainerHighest"),
    ("onSurfaceVariant", "surfaceContainerHighest"),
    ("primary", "surface"),
    ("primary", "surfaceContainerLow"),
    ("primary", "surfaceContainerHigh"),
    ("error", "surface"),
    ("error", "surfaceContainerLow"),
    ("error", "surfaceContainer"),
    ("error", "surfaceContainerHigh"),
    ("inverseOnSurface", "inverseSurface"),
    ("inversePrimary", "inverseSurface"),
    ("outline", "surface"),
)


def _lum(color: str) -> float:
    ch = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    ch = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)  # NaN would pass every comparison


def check_structure(tokens: object) -> list[str]:
    """Structural findings: the shape check() relies on (color: theme -> role -> value; contrastPairs: list of fg/bg/min)."""
    if not isinstance(tokens, dict):
        return [f"top level must be an object, not {type(tokens).__name__}"]
    found: list[str] = []
    colors = tokens.get("color")
    if not isinstance(colors, dict):
        found.append(f"color must be an object of themes, not {type(colors).__name__}")
    else:
        found.extend(f"color.{theme} must be an object of roles, not {type(roles).__name__}" for theme, roles in colors.items() if not isinstance(roles, dict))
    pairs = tokens.get("contrastPairs")
    if not isinstance(pairs, list):
        found.append(f"contrastPairs must be a list, not {type(pairs).__name__}")
        return found
    for i, pair in enumerate(pairs):
        if not isinstance(pair, dict):
            found.append(f"contrastPairs[{i}] must be an object, not {type(pair).__name__}")
            continue
        for key in ("fg", "bg"):
            if not isinstance(pair.get(key), str):
                found.append(f"contrastPairs[{i}].{key} must be a role name (string), not {type(pair.get(key)).__name__}")
        if not _is_number(pair.get("min")):
            found.append(f"contrastPairs[{i}].min must be a finite number, not {type(pair.get('min')).__name__}")
    return found


def check(tokens: object, required: tuple[tuple[str, str], ...] = REQUIRED_PAIRS) -> list[str]:
    malformed = check_structure(tokens)
    if malformed:
        return malformed
    assert isinstance(tokens, dict)  # check_structure proved it; narrows the type
    found: list[str] = []
    listed = {(p["fg"], p["bg"]) for p in tokens["contrastPairs"]}
    for fg, bg in required:
        if (fg, bg) not in listed:
            found.append(f"pair {fg} on {bg} is missing from contrastPairs (required)")
    colors = tokens["color"]
    themes = sorted(colors)
    roles = {t: set(colors[t]) for t in themes}
    every = set().union(*roles.values())
    for theme in themes:
        for role in sorted(every - roles[theme]):
            found.append(f"{theme}: role {role} is missing (every theme needs the same roles)")
        for role, value in colors[theme].items():
            if not (isinstance(value, str) and HEX.fullmatch(value)):
                found.append(f"{theme}: {role} is {value!r}, not #RRGGBB in upper case")
    for pair in tokens["contrastPairs"]:
        fg, bg, need = pair["fg"], pair["bg"], pair["min"]
        floor = AA_NON_TEXT if (fg, bg) in NON_TEXT_PAIRS else AA_TEXT
        if need < floor:
            found.append(f"pair {fg} on {bg}: minimum {need} is below the WCAG AA minimum {floor}")
        for theme in themes:
            c = colors[theme]
            if fg not in c or bg not in c:
                found.append(f"{theme}: pair {fg} on {bg} names a role that does not exist")
                continue
            if not (HEX.fullmatch(str(c[fg])) and HEX.fullmatch(str(c[bg]))):
                continue  # already reported as a malformed color
            ratio = contrast(c[fg], c[bg])
            if ratio < need:
                found.append(f"{theme}: {fg} on {bg} is {ratio:.2f}, needs {need}")
    return found


def main(argv: list[str]) -> int:
    path = Path(argv[0]) if argv else TOKENS
    try:
        tokens = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        print(f"{path}: cannot read the file: {exc}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"{path}: not valid JSON: {exc}")
        return 1
    found = check(tokens)
    for line in found:
        print(f"{path}: {line}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
