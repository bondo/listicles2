"""Static XSS check for the wireframes page (docs/product/wireframes/wireframes.html).

Usage: python3 -I scripts/wireframes_safety.py [file ...]   (default: the wireframes page)
Exit status: 0 clean, 1 findings (one line per finding: file:line message).

Rule: text that an attacker can influence must not reach markup. Sinks: an innerHTML/outerHTML assignment, insertAdjacentHTML,
document.write, and every interpolation `${...}` of a template literal that contains markup (`<tag`), wherever that template ends up.
Sources: the URL (location, document.URL, documentURI, baseURI, referrer, cookie, window.name, URLSearchParams and its .get), an error
object (catch parameter, .catch callback parameter) and fetched data (the value of .json()/.text(), and the parameter of the .then
callback that follows a callback that reads them). Show such text with textContent instead, or wrap the WHOLE value in a whitelisted
sanitizer call: esc(...) for one string, escDeep(...) for a fetched object (both are tested against the real page in
scripts/test_wireframes_safety.py).

A value is derived (tainted) when it is declared or assigned (`=` or a compound `+=`, `||=`, `??=`, ... anywhere in code: chained, in
conditions, after `=>`, `else` or a comma) from a source or from another tainted value, when it is a parameter of a
function that is called with a tainted argument, or when it is a parameter of an array callback (`.map`, `.forEach`, ...) whose
receiver is tainted. A value stops being tainted only when the WHOLE right-hand side is one of: a whitelisted sanitizer call; a
ternary whose two results are string literals; a boolean/number method (`.includes`, `.test`, `.has`, `.some`, `.every`, `.indexOf`,
`.startsWith`, `.endsWith`, `.findIndex`); or `.find`/`.filter` on a receiver that is not tainted. A lookup or literal ternary
somewhere inside a larger expression cleans nothing; a sanitizer call is removed from an expression only as a whole operand
(`'<p>' + esc(x)` is fine, `esc(x) + x` is not).

Limits (this is a lint, not a proof): taint is tracked per name inside the function or block where the name is declared, so two
variables with the same name in the same scope share it (conservative) and a shadowed name in a nested scope is not told apart; only
the contents of <script> elements are analysed (markup and inline event-handler attributes outside them are not); there
is no aliasing or property tracking (`o.x = tainted; use(o.x)`), no flow through closures that are not named functions, no `+`
string concatenation outside a sink expression, no tracking through DOM reads (`el.value`, `el.dataset`, `localStorage`),
`postMessage`, `eval`, `new Function`, `javascript:` URLs, event-handler attributes or other sinks (`.src`, `.href`, `setAttribute`),
regex literals that contain quote or backtick characters confuse the scanner (write them with
\x22, \x27, \x60), and only `//` line comments at the start or after code are stripped. Test pages by hand in a browser for anything beyond these rules.
"""

import re
import sys
from pathlib import Path

PAGE = Path("docs/product/wireframes/wireframes.html")
SANITIZERS = ("esc", "escDeep")

_ID = r"[A-Za-z_$][\w$]*"
_SINK = re.compile(r"\.(?:innerHTML|outerHTML)\s*\+?=(?!=)\s*")
_CALL_SINK = re.compile(r"\.insertAdjacentHTML\s*\(|\bdocument\s*\.\s*write(?:ln)?\s*\(")
_DECL = re.compile(r"\b(?:const|let|var)\s+(" + _ID + r")\s*=(?![=>])\s*")
_ASSIGN = re.compile(r"(?<![\w$.])(" + _ID + r")\s*(?:\*\*|<<|>>>?|\|\||&&|\?\?|[-+*/%&|^])?=(?![=>])\s*")
_DECL_PATTERN = re.compile(r"\b(?:const|let|var)\s+([\[{][^=;]*?[\]}])\s*=(?!=)\s*")
_FOR_OF = re.compile(r"\bfor\s*\(\s*(?:const|let|var)\s+([^;()]*?)\s+(?:of|in)\s+")
_PARAMS_OBJECT = re.compile(r"\b(" + _ID + r")\s*=\s*new\s+URLSearchParams\b")
_CATCH_PARAM = re.compile(
    r"\bcatch\s*\(\s*(" + _ID + r")\s*\)"
    r"|\.catch\(\s*\(?\s*(" + _ID + r")\s*\)?\s*=>"
    r"|\.catch\(\s*function\s*\(\s*(" + _ID + r")"
)
_THEN = re.compile(r"\.then\s*\(")
_READS_BODY = re.compile(r"\.(?:json|text|formData|blob|arrayBuffer)\s*\(")
_FUNCTION = re.compile(r"\bfunction\s+(" + _ID + r")\s*\(")
_ARROW_CONST = re.compile(r"\b(?:const|let|var)\s+(" + _ID + r")\s*=\s*(?:async\s*)?(?:\(|(" + _ID + r")\s*=>)")
_CALL = re.compile(r"(?<![\w$.])(" + _ID + r")\s*\(")
_ARRAY_CALLBACK = re.compile(
    r"\.(?:map|forEach|filter|find|findLast|some|every|flatMap|reduce|sort)\s*\(\s*(?:async\s*)?(?:\(([^()]*)\)|(" + _ID + r"))\s*=>"
)
_BOOL_METHODS = ("includes", "test", "has", "some", "every", "indexOf", "startsWith", "endsWith", "findIndex")
_ELEM_METHODS = ("find", "filter", "findLast")
_LITERAL_TERNARY = re.compile(r"[^?]*\?\s*(?:'[^'\\]*'|\"[^\"\\]*\")\s*:\s*(?:'[^'\\]*'|\"[^\"\\]*\")")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"(?m)(?<![:\w'\"`])//.*$")
_MARKUP = re.compile(r"<[A-Za-z!/]")


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


def _split_args(s: str) -> list[str]:
    """Split on commas at depth 0 (strings and templates skipped)."""
    out: list[str] = []
    depth = 0
    start = 0
    i = 0
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
            depth -= 1
        elif c == "," and depth == 0:
            out.append(s[start:i])
            start = i + 1
        i += 1
    out.append(s[start:])
    return out


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


def _templates(s: str, base: int = 0) -> list[tuple[str, list[tuple[int, str]]]]:
    """Every template literal in s (nested ones too) as (static text, [(offset, interpolation code)])."""
    found: list[tuple[str, list[tuple[int, str]]]] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c in "'\"":
            i = _skip_string(s, i)
        elif c == "`":
            static: list[str] = []
            interps: list[tuple[int, str]] = []
            i += 1
            while i < len(s) and s[i] != "`":
                if s[i] == "\\":
                    static.append(s[i : i + 2])
                    i += 2
                elif s.startswith("${", i):
                    end = _skip_balanced(s, i + 2)
                    interps.append((base + i, s[i + 2 : end]))
                    found.extend(_templates(s[i + 2 : end], base + i + 2))
                    i = end + 1
                else:
                    static.append(s[i])
                    i += 1
            i += 1
            found.append(("".join(static), interps))
        else:
            i += 1
    return found


def _words(code: str) -> set[str]:
    return set(re.findall(r"(?<![\w$.])" + _ID, code))


Span = tuple[int, int]


def _code_mask(js: str) -> bytearray:
    """1 for every character that is code: not inside a string literal or the static text of a template (`${...}` is code)."""
    mask = bytearray(len(js))

    def code(i: int, in_interp: bool) -> int:
        depth = 0
        while i < len(js):
            c = js[i]
            if c in "'\"":
                i = _skip_string(js, i)
                continue
            if c == "`":
                i = template(i)
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                if depth == 0 and in_interp:
                    return i
                depth = max(depth - 1, 0)
            mask[i] = 1
            i += 1
        return i

    def template(i: int) -> int:
        i += 1
        while i < len(js) and js[i] != "`":
            if js[i] == "\\":
                i += 2
            elif js.startswith("${", i):
                i = code(i + 2, True) + 1
            else:
                i += 1
        return i + 1

    code(0, False)
    return mask


def _script_only(text: str) -> str:
    """The text with everything outside <script> elements blanked (line numbers kept); text without a script tag is returned as is."""
    scripts = list(re.finditer(r"<script\b[^>]*>(.*?)</script\s*>", text, re.S | re.I))
    if not scripts:
        return text
    chars = list(re.sub(r"[^\n]", " ", text))
    for m in scripts:
        chars[m.start(1) : m.end(1)] = list(text[m.start(1) : m.end(1)])
    return "".join(chars)


def _blocks(js: str) -> list[Span]:
    """Spans of every `{...}` in code, including `${...}` inside templates."""
    spans: list[Span] = []
    stack: list[int] = []

    def scan(i: int, end_on_close: bool) -> int:
        """Scan code from i; return the index after the `}` that closes the context (or len)."""
        while i < len(js):
            c = js[i]
            if c in "'\"":
                i = _skip_string(js, i)
                continue
            if c == "`":
                i = scan_template(i)
                continue
            if c == "{":
                stack.append(i)
            elif c == "}":
                if stack:
                    spans.append((stack.pop(), i + 1))
                elif end_on_close:
                    return i + 1
            i += 1
        return i

    def scan_template(i: int) -> int:
        i += 1
        while i < len(js) and js[i] != "`":
            if js[i] == "\\":
                i += 2
            elif js.startswith("${", i):
                start = i
                stack.append(start)
                i = scan_interp(i + 2)
            else:
                i += 1
        return i + 1

    def scan_interp(i: int) -> int:
        depth = len(stack)
        while i < len(js):
            c = js[i]
            if c in "'\"":
                i = _skip_string(js, i)
                continue
            if c == "`":
                i = scan_template(i)
                continue
            if c == "{":
                stack.append(i)
            elif c == "}":
                start = stack.pop()
                spans.append((start, i + 1))
                if len(stack) < depth:
                    return i + 1
            i += 1
        return i

    scan(0, False)
    return spans


def _body_span(js: str, i: int) -> Span:
    """Span of a function body that starts at js[i] (after `=>` or after the parameter list)."""
    while i < len(js) and js[i].isspace():
        i += 1
    if i < len(js) and js[i] == "{":
        return (i, _skip_balanced(js, i + 1) + 1)
    return (i, _expr_end(js, i))


def _receiver(js: str, dot: int) -> tuple[str, int]:
    """The expression before the `.` at js[dot] (a chain of identifiers, dots, calls and brackets) and where it starts."""
    i = dot
    while i > 0 and js[i - 1].isspace():
        i -= 1
    while i > 0:
        c = js[i - 1]
        if c in ")]}":
            depth = 0
            j = i
            while j > 0:
                j -= 1
                if js[j] in ")]}":
                    depth += 1
                elif js[j] in "([{":
                    depth -= 1
                    if depth == 0:
                        break
            i = j
        elif c.isalnum() or c in "_$.":
            i -= 1
        else:
            break
    return js[i:dot], i


def _sources(js: str) -> re.Pattern[str]:
    """Pattern for a direct use of a source: the URL, a URLSearchParams object, or the body of a response."""
    names = sorted(set(_PARAMS_OBJECT.findall(js)) | {"params"})
    return re.compile(
        r"\blocation\b|\bURLSearchParams\b|\bdocument\s*\.\s*(?:URL|documentURI|baseURI|referrer|cookie)\b|\bwindow\s*\.\s*name\b"
        r"|\b(?:" + "|".join(re.escape(n) for n in names) + r")\s*\.\s*get\s*\(" + "|" + _READS_BODY.pattern
    )


def _whole_call(raw: str, head: re.Pattern[str]) -> re.Match[str] | None:
    """The match of `head` (ending right after the opening parenthesis) when the call spans the whole of raw."""
    m = head.match(raw)
    if m and _expr_end(raw, m.end()) == len(raw) - 1:
        return m
    return None


_SANITIZER_CALL = re.compile(r"(?:" + "|".join(SANITIZERS) + r")\s*\(")
_BOOL_CALL = re.compile(r"[\w$.]+\.(?:" + "|".join(_BOOL_METHODS) + r")\s*\(")
_ELEM_CALL = re.compile(r"([\w$.]+)\.(?:" + "|".join(_ELEM_METHODS) + r")\s*\(")


_SANITIZER_START = re.compile(r"(?<![\w$.])(?:" + "|".join(SANITIZERS) + r")\s*\(")


def _strip_sanitizers(code: str) -> str:
    """Remove every whitelisted sanitizer call (its argument is escaped, so it may mention a source) from code."""
    while m := _SANITIZER_START.search(code):
        code = code[: m.start()] + " " + code[_expr_end(code, m.end()) + 1 :]
    return code


class _Taint:
    """Tainted names with the spans (function or block bodies) in which each is tainted."""

    def __init__(self, source: re.Pattern[str]) -> None:
        self.source = source
        self.spans: dict[str, set[Span]] = {}

    def add(self, names: set[str], span: Span) -> bool:
        grew = False
        for n in names:
            if span not in self.spans.setdefault(n, set()):
                self.spans[n].add(span)
                grew = True
        return grew

    def at(self, pos: int) -> set[str]:
        return {n for n, sp in self.spans.items() if any(a <= pos < b for a, b in sp)}

    def is_clean(self, raw: str, pos: int) -> bool:
        """True when the WHOLE value is a sanitizer call, a literal-only ternary, a boolean method or a lookup in a clean list."""
        raw = raw.strip()
        if _whole_call(raw, _SANITIZER_CALL) or _whole_call(raw, _BOOL_CALL) or _LITERAL_TERNARY.fullmatch(raw):
            return True
        m = _whole_call(raw, _ELEM_CALL)
        return bool(m and not self.source.search(m.group(1)) and not _words(m.group(1)) & self.at(pos))

    def tainted(self, raw: str, pos: int) -> bool:
        if self.is_clean(raw, pos):
            return False
        code = _strip_sanitizers(_code_only(raw))
        return bool(self.source.search(code) or _words(code) & self.at(pos))

    def why(self, raw: str, pos: int) -> str:
        code = _strip_sanitizers(_code_only(raw))
        hit = self.source.search(code)
        return hit.group(0) if hit else ", ".join(sorted(_words(code) & self.at(pos)))


def _param_words(params: str) -> list[set[str]]:
    """Identifier words of each parameter, ignoring default values."""
    return [_words(re.sub(r"=[^,}\]]*", "", p)) for p in _split_args(params)]


def _taint(js: str) -> _Taint:
    """Names that hold URL, error or fetched data, directly or through other values (see the module docstring)."""
    t = _Taint(_sources(js))
    whole = (0, len(js))
    blocks = _blocks(js)

    def scope(pos: int) -> Span:
        inside = [b for b in blocks if b[0] <= pos < b[1]]
        return min(inside, key=lambda b: b[1] - b[0]) if inside else whole

    # errors: the catch parameter is tainted inside its handler
    for m in re.finditer(r"\bcatch\s*\(\s*(" + _ID + r")\s*\)\s*(?=\{)", js):
        t.add({m.group(1)}, _body_span(js, m.end()))
    for m in re.finditer(r"\.catch\(\s*\(?\s*(" + _ID + r")\s*\)?\s*=>", js):
        t.add({m.group(1)}, _body_span(js, m.end()))
    for m in re.finditer(r"\.catch\(\s*function\s*\(\s*(" + _ID + r")[^)]*\)", js):
        t.add({m.group(1)}, _body_span(js, m.end()))

    functions: dict[str, tuple[list[set[str]], Span]] = {}
    for m in _FUNCTION.finditer(js):
        end = _expr_end(js, m.end())
        functions[m.group(1)] = (_param_words(js[m.end() : end]), _body_span(js, end + 1))
    for m in _ARROW_CONST.finditer(js):
        if m.group(2):
            functions[m.group(1)] = ([{m.group(2)}], _body_span(js, m.end()))
        else:
            end = _expr_end(js, m.end())
            arrow = re.match(r"\s*=>", js[end + 1 :])
            if arrow:
                functions[m.group(1)] = (_param_words(js[m.end() : end]), _body_span(js, end + 1 + arrow.end()))

    # fetched data: the callback that follows a callback reading the body
    thens = [(m.end(), _expr_end(js, m.end())) for m in _THEN.finditer(js)]
    for (a1, b1), (a2, b2) in zip(thens, thens[1:], strict=False):
        if not _READS_BODY.search(js[a1:b1]):
            continue
        arrow = re.match(r"\s*(?:async\s*)?\(?\s*(" + _ID + r")\s*\)?\s*=>", js[a2:b2])
        plain = re.fullmatch(r"\s*(" + _ID + r")\s*", js[a2:b2])
        if arrow:
            t.add({arrow.group(1)}, (a2, b2))
        elif plain and plain.group(1) in functions:
            params, body = functions[plain.group(1)]
            if params:
                t.add(params[0], body)

    decls: list[tuple[set[str], str, int, Span]] = []
    declared: dict[str, list[Span]] = {}  # name -> scopes of its const/let/var declarations and function parameters
    for rx in (_DECL, _DECL_PATTERN, _FOR_OF):
        for m in rx.finditer(js):
            sc = scope(m.start())
            decls.append((_words(m.group(1)), js[m.end() : _expr_end(js, m.end())], m.end(), sc))
            for n in _words(m.group(1)):
                declared.setdefault(n, []).append(sc)
    for params, body in functions.values():
        for group in params:
            for n in group:
                declared.setdefault(n, []).append(body)

    def assign_scope(name: str, pos: int) -> Span:
        """The scope of the variable an assignment at pos writes to: the innermost declaration around it, else the whole file."""
        inside = [sp for sp in declared.get(name, []) if sp[0] <= pos < sp[1]]
        return min(inside, key=lambda sp: sp[1] - sp[0]) if inside else whole

    mask = _code_mask(js)
    for m in _ASSIGN.finditer(js):
        if not mask[m.start(1)]:
            continue
        decls.append(({m.group(1)}, js[m.end() : _expr_end(js, m.end())], m.end(), assign_scope(m.group(1), m.start())))
    calls: list[tuple[str, list[tuple[str, int]]]] = []
    for m in _CALL.finditer(js):
        if m.group(1) in functions and not re.search(r"\bfunction\s+$", js[: m.start()]):
            text = js[m.end() : _expr_end(js, m.end())]
            args: list[tuple[str, int]] = []
            at = m.end()
            for piece in _split_args(text):
                args.append((piece, at))
                at += len(piece) + 1
            calls.append((m.group(1), args))
    callbacks: list[tuple[str, int, set[str], Span]] = []
    for m in _ARRAY_CALLBACK.finditer(js):
        recv, recv_pos = _receiver(js, m.start())
        callbacks.append((recv, recv_pos, _words(m.group(1) or m.group(2) or ""), _body_span(js, m.end())))

    changed = True
    while changed:
        changed = False
        for names, raw, pos, span in decls:
            if t.tainted(raw, pos) and t.add(names, span):
                changed = True
        for name, args in calls:
            params, body = functions[name]
            for i, (raw, pos) in enumerate(args):
                if i < len(params) and t.tainted(raw, pos) and t.add(params[i], body):
                    changed = True
        for recv, recv_pos, names, span in callbacks:
            if t.tainted(recv, recv_pos) and t.add(names, span):
                changed = True
    return t


def tainted_names(js: str) -> set[str]:
    """All names that are tainted somewhere in js (for tests and debugging)."""
    return set(_taint(js).spans)


def check(text: str) -> list[tuple[int, str]]:
    """Findings (line, message) for one HTML or JS text, one per line."""
    js = _BLOCK_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), _script_only(text))
    js = _LINE_COMMENT.sub("", js)
    t = _taint(js)
    found: dict[int, str] = {}

    def report(pos: int, what: str, raw: str) -> None:
        msg = f"{what} uses a value derived from the URL, an error or fetched data ({t.why(raw, pos)}); use textContent or esc()/escDeep()"
        found.setdefault(js.count("\n", 0, pos) + 1, msg)

    for m in _SINK.finditer(js):
        raw = js[m.end() : _expr_end(js, m.end())]
        if t.tainted(raw, m.end()):
            report(m.end(), "innerHTML/outerHTML assignment", raw)
    for m in _CALL_SINK.finditer(js):
        raw = js[m.end() : _expr_end(js, m.end())]
        if t.tainted(raw, m.end()):
            report(m.end(), "HTML insertion call", raw)
    for static, interps in _templates(js):
        if _MARKUP.search(static):
            for offset, code in interps:
                if t.tainted(code, offset + 2):
                    report(offset + 2, "markup template", code)
    return sorted(found.items())


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
