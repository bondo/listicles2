"""Checks on design/tokens.json: colors are well-formed, both themes define the same roles, and every contrast pair passes.

Usage: python3 -I scripts/design_tokens.py [tokens.json]   (default: design/tokens.json)
Exit status: 0 clean, 1 findings (one line per finding).

Rules: every color is #RRGGBB in upper case; the light and dark themes have exactly the same roles (so a theme can be swapped
whole, post-v1); every contrastPairs entry names roles that exist, keeps the WCAG AA minimum (4.5 for text, 3.0 for the outline
pair) and meets that minimum in both themes. Thresholds are never read from anywhere that could weaken them: a pair may ask for
more than AA, never less.
"""

import json
import re
import sys
from pathlib import Path

TOKENS = Path(__file__).resolve().parent.parent / "design" / "tokens.json"
HEX = re.compile(r"#[0-9A-F]{6}")
AA_TEXT = 4.5
AA_NON_TEXT = 3.0
NON_TEXT_PAIRS = {("outline", "surface")}


def _lum(color: str) -> float:
    ch = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    ch = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def check(tokens: dict) -> list[str]:
    found: list[str] = []
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
    found = check(json.loads(path.read_text(encoding="utf-8")))
    for line in found:
        print(f"{path}: {line}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
