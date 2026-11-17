"""Static XSS check for the wireframes page (docs/product/wireframes/wireframes.html).

Usage: python3 -I scripts/wireframes_safety.py [file ...]   (default: the wireframes page)
Exit status: 0 clean, 1 findings (one line per finding: file:line message).

Rule: no innerHTML/outerHTML assignment and no insertAdjacentHTML call may use a value derived from the URL
(location, a URLSearchParams object and its .get) or from an error object (catch parameter, .catch callback parameter).
Show such text with textContent instead. A value counts as derived when it is declared from such a source, or from
another derived value; it stops counting when it is reduced to a fixed literal (`x === 'dark' ? 'dark' : 'light'`) or
looked up in a trusted list (`.find`, `.some`, `.includes`, `.indexOf`, `.test`, `.has`, `.every`).
Only code is inspected: the static text of template literals and string literals is ignored.
"""

import re
import sys
from pathlib import Path

PAGE = Path("docs/product/wireframes/wireframes.html")

_SINK = re.compile(r"\.(?:innerHTML|outerHTML)\s*\+?=(?!=)\s*")
_ADJACENT = re.compile(r"\.insertAdjacentHTML\s*\(")
_DECL = re.compile(r"(?:\b(?:const|let|var)\s+|(?m:^)\s*)([A-Za-z_$][\w$]*)\s*=(?![=>])\s*")
_PARAMS_OBJECT = re.compile(r"\b([A-Za-z_$][\w$]*)\s*=\s*new\s+URLSearchParams\b")
_CATCH_PARAM = re.compile(
    r"\bcatch\s*\(\s*([A-Za-z_$][\w$]*)\s*\)"
    r"|\.catch\(\s*\(?\s*([A-Za-z_$][\w$]*)\s*\)?\s*=>"
    r"|\.catch\(\s*function\s*\(\s*([A-Za-z_$][\w$]*)"
)
_TRUSTED_LOOKUP = re.compile(r"\.(?:find|some|includes|indexOf|test|has|every)\s*\(")
_LITERAL_TERNARY = re.compile(r"\?\s*(['\"])[^'\"]*\1\s*:\s*(['\"])[^'\"]*\2")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _skip_string(s: str, i: int) -> int:
    """Index after the string literal that starts at s[i]."""
    quote = s[i]
    i += 1
    while i < len(s) and s[i] != quote:
        i += 2 if s[i] == "\\" else 1
    return i + 1


def _skip_template(s: str, i: int) -> int:
    """Index after the template literal that starts at s[i] (a backtick)."""
    i += 1
    while i < len(s) and s[i] != "`":
        if s[i] == "\\":
            i += 2
        elif s.startswith("${", i):
            i = _skip_balanced(s, i + 2) + 1
        else:
            i += 1
    return i + 1


def _skip_balanced(s: str, i: int) -> int:
    """Index of the `}` that closes a `${` whose content starts at s[i]."""
    depth = 0
    while i < len(s):
        c = s[i]
        if c in "'\"":
            i = _skip_string(s, i)
            continue
        if c == "`":
            i = _skip_template(s, i)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                return i
            depth -= 1
        i += 1
    return len(s)


def _expr_end(s: str, i: int) -> int:
    """End of the expression that starts at s[i]: the `;` or unmatched closer at depth 0."""
    depth = 0
    while i < len(s):
        c = s[i]
        if c in "'\"":
            i = _skip_string(s, i)
            continue
        if c == "`":
            i = _skip_template(s, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif c == ";" and depth == 0:
            return i
        i += 1
    return len(s)


def _code_only(s: str) -> str:
    """The expression without string literals and without the static text of templates; `${...}` code is kept."""
    out: list[str] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c in "'\"":
            i = _skip_string(s, i)
            out.append(" ")
        elif c == "`":
            i += 1
            while i < len(s) and s[i] != "`":
                if s[i] == "\\":
                    i += 2
                elif s.startswith("${", i):
                    end = _skip_balanced(s, i + 2)
                    out.append(" " + _code_only(s[i + 2 : end]) + " ")
                    i = end + 1
                else:
                    i += 1
            i += 1
            out.append(" ")
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _words(code: str) -> set[str]:
    return set(re.findall(r"(?<![\w$.])[A-Za-z_$][\w$]*", code))


def _sources(js: str) -> re.Pattern[str]:
    """Pattern that matches a direct use of a URL source: location, URLSearchParams, <params object>.get."""
    names = sorted(set(_PARAMS_OBJECT.findall(js)) | {"params"})
    return re.compile(r"\blocation\b|\bURLSearchParams\b|\b(?:" + "|".join(re.escape(n) for n in names) + r")\s*\.\s*get\s*\(")


def tainted_names(js: str) -> set[str]:
    """Names declared from a URL or error source, directly or through other tainted names."""
    source = _sources(js)
    tainted = {g for m in _CATCH_PARAM.finditer(js) for g in m.groups() if g}
    decls = []
    for m in _DECL.finditer(js):
        raw = js[m.end() : _expr_end(js, m.end())]
        decls.append((m.group(1), raw, _code_only(raw)))
    changed = True
    while changed:
        changed = False
        for name, raw, rhs in decls:
            if name in tainted or _TRUSTED_LOOKUP.search(rhs) or _LITERAL_TERNARY.search(raw):
                continue
            if source.search(rhs) or _words(rhs) & tainted:
                tainted.add(name)
                changed = True
    return tainted


def check(text: str) -> list[tuple[int, str]]:
    """Findings (line, message) for one HTML or JS text."""
    js = _BLOCK_COMMENT.sub(lambda m: " " * len(m.group(0)), text)
    source = _sources(js)
    tainted = tainted_names(js)
    found: list[tuple[int, str]] = []

    def inspect(start: int, end: int, what: str) -> None:
        code = _code_only(js[start:end])
        hit = source.search(code)
        names = sorted(_words(code) & tainted)
        if hit or names:
            why = hit.group(0) if hit else ", ".join(names)
            line = js.count("\n", 0, start) + 1
            found.append((line, f"{what} uses a value derived from the URL or an error ({why}); use textContent"))

    for m in _SINK.finditer(js):
        inspect(m.end(), _expr_end(js, m.end()), "innerHTML/outerHTML assignment")
    for m in _ADJACENT.finditer(js):
        inspect(m.end(), _expr_end(js, m.end()), "insertAdjacentHTML call")
    return sorted(set(found))


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent.parent
    paths = [Path(a) for a in argv] or [root / PAGE]
    bad = 0
    for p in paths:
        for line, msg in check(p.read_text(encoding="utf-8")):
            print(f"{p}:{line} {msg}")
            bad = 1
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
