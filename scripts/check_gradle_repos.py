"""Checks the Gradle repository setup that keeps cold dependency downloads from failing on HTTP 429.

Maven Central (repo.maven.apache.org, behind Cloudflare) answers a share of requests from shared cloud
egress IPs with 429. Gradle disables a repository for the rest of the build once its retries for one
request run out, so a single unlucky burst fails the whole build. The setup this checks:
  * Google's Maven Central mirror is listed before mavenCentral() (mavenCentral() stays as fallback),
  * google() only gets the groups it hosts, so other artifacts are not looked up there first,
    wherever it is written (a repositories { } block, repositories.google(), inside a string template),
  * Gradle retries repository requests often enough, with backoff, to ride out a 429 burst.
It also checks Gradle dependency verification (gradle/verification-metadata.xml, sha256 for every artifact), so a
mirror or CDN problem cannot silently change an artifact; Gradle itself enforces it in every build.
Settings it cannot read with confidence (an unterminated string or template) are reported, never passed.
Run: python3 -I scripts/check_gradle_repos.py  (exit 1 and one line per problem when the setup is off).
"""

import hashlib
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MIRROR = "https://maven-central.storage-download.googleapis.com/maven2"
BLOCKS = ("pluginManagement", "dependencyResolutionManagement")
MIN_TENTATIVES = 6
MIN_BACKOFF_MS = 1000
TENTATIVES = "systemProp.org.gradle.internal.repository.max.tentatives"
BACKOFF = "systemProp.org.gradle.internal.repository.initial.backoff"


CHAR_LITERAL = re.compile(r"'(?:[^\\'\n]|\\(?:u[0-9a-fA-F]{4}|[^\n]))'")
INCLUDE = re.compile(r"\binclude\w*\s*\(")
MIRROR_LITERAL = re.compile(r"\"+" + re.escape(MIRROR) + r"\"+")  # plain or raw string
# What may precede the mirror literal for it to declare a repository: maven("<url>"), maven(url = "<url>"), maven(uri("<url>")), or,
# inside a `maven { }` block, a statement url = [uri(]"<url>") or setUrl([uri(]"<url>"). A val or any other call holding the URL does not.
CALL_HEAD = re.compile(r"\bmaven\s*\(\s*(?:url\s*=\s*)?(?:uri\s*\(\s*)?$")
URL_HEAD = re.compile(r"(?:^|[{;.\n])[ \t]*(?:url\s*=|setUrl\s*\()\s*(?:uri\s*\(\s*)?$")
OWN = r"(?<![\w.)\]])(?:this\s*\.\s*)?repositories"  # the enclosing block's own repositories, not another object's
ONLY_GOOGLE = re.compile(r"\s*google\s*\(\s*\)\s*;?\s*")


class Unparsable(Exception):
    """Kotlin source the scanner cannot read with confidence; the check reports it instead of guessing."""


def _strip(text, blank_strings=False):
    """Kotlin source without // and (nested) /* */ comments, each block comment replaced by one space so tokens never glue.

    String and char literal contents become spaces if blank_strings, one space per character; the code inside a `${ }`
    template stays (it runs). Strings are modelled in full: escapes, raw strings (a run of quotes ends one with its last
    three), and templates, whose code can hold strings, comments and braces of its own, so the scanner recurses.
    Backtick identifiers are copied with their non-word characters replaced, so a quote or brace in one is not syntax.
    Raises Unparsable on an unterminated string, raw string, template or backtick identifier, a newline in a plain string, a
    multi-dollar string ($$"...") and a backtick short template ("$`a`"). Block comments nest."""
    out, n = [], len(text)

    def literal(chunk):
        out.append(" " * len(chunk) if blank_strings else chunk)

    def template(i):
        """text[i:i+2] is `${`; returns the index after the matching `}`."""
        out.append("${")
        i = code(i + 2, in_template=True)
        out.append("}")
        return i + 1

    def string(i):
        out.append('"')
        i += 1
        while i < n:
            if text[i] == '"':
                out.append('"')
                return i + 1
            if text.startswith("${", i):
                i = template(i)
            elif text.startswith("$`", i):
                raise Unparsable("backtick in a string template")
            elif text[i] == "\\":
                literal(text[i : i + 2])
                i += 2
            elif text[i] == "\n":
                break
            else:
                literal(text[i])
                i += 1
        raise Unparsable("unterminated string")

    def raw_string(i):
        out.append('"""')
        i += 3
        while i < n:
            if text.startswith('"""', i):
                quotes = len(text[i:]) - len(text[i:].lstrip('"'))  # the last three of a run close the string
                literal('"' * (quotes - 3))
                out.append('"""')
                return i + quotes
            if text.startswith("${", i):
                i = template(i)
            elif text.startswith("$`", i):
                raise Unparsable("backtick in a string template")
            else:
                literal(text[i])
                i += 1
        raise Unparsable("unterminated raw string")

    def code(i, in_template=False):
        """Scans code; inside a template it stops at the `}` that closes it and returns that index, else returns n."""
        depth = 0
        while i < n:
            if text.startswith("//", i):
                while i < n and text[i] != "\n":
                    i += 1
            elif text.startswith("/*", i):
                nesting, i = 1, i + 2
                while i < n and nesting:
                    if text.startswith("/*", i):
                        nesting, i = nesting + 1, i + 2
                    elif text.startswith("*/", i):
                        nesting, i = nesting - 1, i + 2
                    else:
                        i += 1
                out.append(" ")
            elif text[i] == "'" and (char := CHAR_LITERAL.match(text, i)) is not None:
                out.append("'")
                literal(char.group()[1:-1])
                out.append("'")
                i = char.end()
            elif text[i] == "$" and text.startswith('"', i + 1):
                raise Unparsable("multi-dollar string")  # $$"${" is plain text in Kotlin 2.2+; not modelled
            elif text[i] == "`":
                end = text.find("`", i + 1)
                if end < 0 or "\n" in text[i:end]:
                    raise Unparsable("unterminated backtick identifier")
                out.append("`" + re.sub(r"\W", "_", text[i + 1 : end]) + "`")  # a quote or brace in the name is not syntax
                i = end + 1
            elif text.startswith('"""', i):
                i = raw_string(i)
            elif text[i] == '"':
                i = string(i)
            elif in_template and text[i] == "}" and depth == 0:
                return i
            else:
                depth += {"{": 1, "}": -1}.get(text[i], 0)
                out.append(text[i])
                i += 1
        if in_template:
            raise Unparsable("unterminated string template")
        return i

    code(0)
    return "".join(out)


def _body(text, open_brace):
    """Body of the block whose `{` is at open_brace, or None if unbalanced."""
    depth, i = 1, open_brace + 1
    while i < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[open_brace + 1 : i - 1] if depth == 0 else None


def _spans(text, name):
    """(start, end) of the body of every top-level-in-text `name { ... }` block, in order."""
    spans, pos = [], 0
    pattern = re.compile(r"\b" + re.escape(name) + r"(\(\))?\s*\{")
    while (m := pattern.search(text, pos)) is not None:
        body = _body(text, m.end() - 1)
        if body is None:
            break
        spans.append((m.end(), m.end() + len(body)))
        pos = m.end() + len(body) + 1
    return spans


def _top_spans(text, name):
    """Like _spans, but only the `name { ... }` blocks that are not nested inside another block of text."""
    spans = []
    for m in re.finditer(r"\b" + re.escape(name) + r"(\(\))?\s*\{", text):
        if text.count("{", 0, m.start()) != text.count("}", 0, m.start()):
            continue
        body = _body(text, m.end() - 1)
        if body is not None:
            spans.append((m.end(), m.end() + len(body)))
    return spans


def _block(text, name):
    """Body of the first `name { ... }` block, or None."""
    spans = _spans(text, name)
    return text[spans[0][0] : spans[0][1]] if spans else None


def _filtered(repos, call):
    """True if the google() call at match `call` has a content { include...(...) } filter."""
    brace = re.compile(r"\s*\{").match(repos, call.end())
    body = _body(repos, brace.end() - 1) if brace else None
    content = _block(body, "content") if body is not None else None
    return content is not None and INCLUDE.search(content) is not None


def _exclusive(repos):
    """Spans of forRepository { } bodies that are exactly google() in exclusiveContent blocks whose own filter { } has an
    include...() rule. Gradle applies the filter only to the repository the lambda returns, so any other repository or
    statement in the body (google(); maven(...), maven { google() }) is not covered."""
    spans = []
    for start, end in _spans(repos, "exclusiveContent"):
        body = repos[start:end]
        if any(INCLUDE.search(body[a:b]) for a, b in _top_spans(body, "filter")):
            spans += [(start + a, start + b) for a, b in _top_spans(body, "forRepository") if ONLY_GOOGLE.fullmatch(body[a:b])]
    return spans


def _enclosing_brace(text, pos):
    """Index of the `{` of the innermost block of text that contains pos, or None at top level."""
    depth = 0
    for i in range(pos - 1, -1, -1):
        if text[i] == "}":
            depth += 1
        elif text[i] == "{":
            if depth == 0:
                return i
            depth -= 1
    return None


def _on_own_repositories(outer, maven):
    """True if the maven call starting at index `maven` of outer (a block's body) is a direct statement of a top-level
    `repositories { }`, `repositories() { }` or `this.repositories { }` body of that block: the form main counts too.
    A dotted call (repositories.maven(...)) never counts: whether `repositories` is the block's own handler and whether the
    statement runs depends on receivers, local names and control flow that a scanner cannot see, so it fails closed."""
    if outer[:maven].rstrip().endswith("."):
        return False
    brace = _enclosing_brace(outer, maven)
    return brace is not None and re.search(OWN + r"\s*(?:\(\s*\))?\s*$", outer[:brace]) is not None and _enclosing_brace(outer, brace) is None


def _mirror_start(outer, outer_kept):
    """Index of the first mirror URL that declares a repository of the block (outer is its code, outer_kept the same with strings), or -1."""
    for lit in MIRROR_LITERAL.finditer(outer_kept):
        before = outer[: lit.start()]
        head = CALL_HEAD.search(before)
        if head is None and URL_HEAD.search(before) is not None:
            brace = _enclosing_brace(outer, lit.start())
            head = re.search(r"\bmaven\s*$", outer[:brace]) if brace is not None else None
        if head is not None and _on_own_repositories(outer, head.start()):
            return lit.start()
    return -1


def _repositories(blanked, kept, name):
    """Every repositories { } body inside every `name { }` block, joined in order (Gradle adds them all up).

    blanked and kept are the same code with string contents blanked or kept (same length); returns both joined texts."""
    parts = []
    for o_start, o_end in _spans(blanked, name):
        for r_start, r_end in _spans(blanked[o_start:o_end], "repositories"):
            parts.append((o_start + r_start, o_start + r_end))
    if not parts:
        return None, None
    return "\n".join(blanked[a:b] for a, b in parts), "\n".join(kept[a:b] for a, b in parts)


def _unfiltered_google(blanked, blocks=BLOCKS):
    """Names of the blocks (BLOCKS by default) whose text holds a google() without a content filter, plus None if one sits outside all of them.

    The whole file is searched, not only braced repositories { } bodies, so repositories.google(), with(repositories) { google() }
    and pluginManagement.repositories.google() need the same filter. Strings are blanked, so URLs never match."""
    exclusive = _exclusive(blanked)
    owners = [(name, a, b) for name in blocks for a, b in _spans(blanked, name)]
    bad = set()
    # A qualified call (this.google(), foo.google()) counts too, and so does any other use of the name (google as a value).
    for call in re.finditer(r"(?<!\w)google\b`?\s*(\(\s*\))?", blanked):  # `google` in backticks is the same name
        if _filtered(blanked, call) or any(a <= call.start() < b for a, b in exclusive):
            continue
        bad.add(next((name for name, a, b in owners if a <= call.start() < b), None))
    return bad


def _outer(blanked, kept, name):
    """The `name { }` bodies joined in order (blanked, kept), and the (start, end) spans of those bodies in the whole text."""
    spans = _spans(blanked, name)
    return "\n".join(blanked[a:b] for a, b in spans), "\n".join(kept[a:b] for a, b in spans), spans


def check_settings(text, blocks=BLOCKS):
    """Problems with a settings.gradle.kts. blocks are the outer blocks that must list the mirror and mavenCentral():
    both for the root and build-logic, pluginManagement alone for the licensee fixture, which resolves its artifacts from repo/."""
    try:
        blanked, kept = _strip(text, blank_strings=True), _strip(text)
    except Unparsable as e:
        return [f"settings.gradle.kts: cannot parse ({e}), so the repositories cannot be checked"]
    unfiltered = _unfiltered_google(blanked, blocks)
    problems, inside = [], []
    for name in blocks:
        repos, _ = _repositories(blanked, kept, name)
        outer, outer_kept, spans = _outer(blanked, kept, name)
        inside += spans
        if repos is None:
            problems.append(f"{name}: no repositories block")
        else:
            # The mirror and the first mention of mavenCentral are looked for in the whole block, not only in braced
            # repositories { } bodies, so repositories.mavenCentral() before the block cannot hide behind them.
            mirror = _mirror_start(outer, outer_kept)
            central = re.search(r"\bmavenCentral\s*(?:\(\s*\)|\{\s*\})", repos)  # mavenCentral() or an empty mavenCentral { }
            first_central = re.search(r"(?<!\w)mavenCentral\b", outer)
            if mirror < 0:
                problems.append(f"{name}: Maven Central mirror {MIRROR} missing")
            elif central is None:
                problems.append(f"{name}: mavenCentral() fallback missing")
            elif first_central is not None and mirror > first_central.start():
                problems.append(f"{name}: Maven Central mirror must come before mavenCentral()")
        if name in unfiltered:
            problems.append(f"{name}: google() needs a content filter")
    for a, b in _spans(blanked, "pluginManagement"):  # it runs first, so what it adds to the dependency repositories comes before the mirror
        if re.search(r"(?<!\w)(?:get)?[dD]ependencyResolutionManagement\b", blanked[a:b]):
            problems.append("pluginManagement: refers to dependencyResolutionManagement, so repositories added there come before its own mirror")
            break
    where = " and ".join(blocks)
    if None in unfiltered:
        problems.append(f"settings.gradle.kts: google() outside {where} needs a content filter")
    if any(not any(a <= m.start() < b for a, b in inside) for m in re.finditer(r"(?<!\w)mavenCentral\b", blanked)):
        problems.append(f"settings.gradle.kts: mavenCentral() outside {where} cannot be ordered after the mirror")
    return problems


def check_properties(text, name="gradle.properties"):
    props = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            props[key.strip()] = value.strip()
    problems = []
    for key, minimum in ((TENTATIVES, MIN_TENTATIVES), (BACKOFF, MIN_BACKOFF_MS)):
        value = props.get(key)
        if value is None or not value.isdigit():
            problems.append(f"{name}: {key} missing or not a number")
        elif int(value) < minimum:
            problems.append(f"{name}: {key}={value} is below {minimum}")
    return problems


VERIFICATION_PROP = "org.gradle.dependency.verification"
META = "verification-metadata.xml"


def check_verification(meta, props_text, verify_text=""):
    """Problems with the dependency verification metadata (text, or None if the file is missing) and gradle.properties."""
    problems = []
    # Gradle reads gradle.properties with java.util.Properties (key ends at =, : or whitespace) and the mode case-insensitively.
    prop = re.compile(r"\s*" + re.escape(VERIFICATION_PROP) + r"(?:\s*[=:]\s*|\s+)(\S+)")
    lines, joined = [], ""
    for raw in props_text.splitlines():  # a non-comment line ending in an odd number of backslashes continues on the next line
        line = joined + (raw.lstrip() if joined else raw)
        cont = not line.lstrip().startswith(("#", "!")) and (len(line) - len(line.rstrip("\\"))) % 2 == 1
        joined = line[:-1] if cont else ""
        if not cont:
            lines.append(line)
    for line in lines:
        m = None if line.lstrip().startswith(("#", "!")) else prop.fullmatch(line.rstrip()) or prop.match(line)
        if m and m.group(1).lower() in ("off", "lenient"):
            problems.append(f"gradle.properties: {VERIFICATION_PROP}={m.group(1).lower()} disables verification")
    flags = re.compile(
        r"(?:--dependency-verification|\s-F|-D" + re.escape(VERIFICATION_PROP) + r")(?:\s*=\s*|\s+|(?<=-F))[\"']?(?:off|lenient)\b", re.I
    )
    if any(flags.search(ln) for ln in verify_text.splitlines() if not ln.lstrip().startswith("#")):
        problems.append("scripts/verify.sh: switches Gradle dependency verification off")
    if meta is None:
        return [f"{META} missing"] + problems
    try:
        root = ET.fromstring(meta)
    except ET.ParseError:
        return [f"{META} is not well-formed XML"] + problems

    def tag(el):
        return el.tag.rsplit("}", 1)[-1]

    elements = list(root.iter())
    flag = [e for e in elements if tag(e) == "verify-metadata"]
    if not flag or any((e.text or "").strip() != "true" for e in flag):
        problems.append(f"{META}: verify-metadata must be true")
    if any(tag(e) == "trusted-artifacts" for e in elements):
        problems.append(f"{META}: trusted-artifacts bypass verification")
    components = [e for e in elements if tag(e) == "component"]
    if not components:
        problems.append(f"{META}: no components")
    for comp in components:
        if comp.get("group") == "com.android.tools.build" and comp.get("name") == "aapt2":
            names = [a.get("name", "") for a in comp if tag(a) == "artifact"]
            gone = [o for o in ("linux", "osx", "windows") if not any(n.endswith(f"-{o}.jar") for n in names)]
            if gone:
                what = ", ".join(gone) + (" jars" if len(gone) > 1 else " jar")
                problems.append(f"{META}: aapt2 {comp.get('version')} lacks {what} (see docs/ANDROID-BEST-PRACTICES.md section 11)")
        for art in (e for e in comp if tag(e) == "artifact"):
            hashes = [e.get("value", "") for e in art if tag(e) == "sha256"]
            if not any(re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes):
                gav = f"{comp.get('group')}:{comp.get('name')}:{comp.get('version')}"
                problems.append(f"{META}: artifact {art.get('name')} of {gav} has no sha256")
    return problems


FIXTURE = "config/licensee/fixture"
FIXTURE_GROUP = "fixture"
LICENSEE = ("app.cash.licensee", "licensee-gradle-plugin")
# Any way to tell Gradle to skip verification in the testLicenseeGate command: --dependency-verification, -F, -Dorg.gradle.dependency.verification.
GATE_OFF = re.compile(r"dependency[-.]verification|\"-F\"")


def _relabel(problems, old, new):
    return [new + p[len(old) :] if p.startswith(old) else p for p in problems]


def check_fixture_metadata(meta, poms, licensee_version):
    """Problems with the licensee fixture build's verification metadata (text, or None if missing).

    The fixture is a separate build run by testLicenseeGate, so the root metadata does not cover it. The file must pass the same
    checks as the root one, hold the licensee plugin version of the catalog (a bump needs it regenerated, and this says so before
    the gate does), and a sha256 equal to the file's for every POM under repo/ (poms maps (artifact, version) to its sha256)."""
    where = f"{FIXTURE}/gradle/{META}"
    problems = _relabel(check_verification(meta, ""), META, where)
    try:
        root = ET.fromstring(meta or "")
    except ET.ParseError:
        return problems  # missing or not XML, already reported
    found = {}
    for comp in (e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "component"):
        names = {a.get("name"): [h.get("value") for h in a if h.tag.rsplit("}", 1)[-1] == "sha256"] for a in comp if a.tag.rsplit("}", 1)[-1] == "artifact"}
        found[(comp.get("group"), comp.get("name"), comp.get("version"))] = names
    if not any(g == LICENSEE[0] and n == LICENSEE[1] and v == licensee_version for g, n, v in found):
        problems.append(f"{where}: no component {LICENSEE[0]}:{LICENSEE[1]} for licensee {licensee_version}")
    for (artifact, version), digest in sorted(poms.items()):
        pom = f"{artifact}-{version}.pom"
        recorded = found.get((FIXTURE_GROUP, artifact, version), {}).get(pom)
        if recorded is None:
            problems.append(f"{where}: no sha256 for {FIXTURE_GROUP}:{artifact}:{version} ({pom})")
        elif digest not in recorded:
            problems.append(f"{where}: sha256 of {FIXTURE_GROUP}:{artifact}:{version} ({pom}) does not match the file")
    return problems


def check_gate_command(build_text):
    """The root build.gradle.kts starts the fixture builds (testLicenseeGate); none of its code may switch verification off."""
    code = (ln for ln in build_text.splitlines() if not ln.lstrip().startswith("//"))
    if any(GATE_OFF.search(ln) for ln in code):
        return ["build.gradle.kts: the licensee gate switches Gradle dependency verification off"]
    return []


def _read(path):
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _nested_settings(root, rel, blocks):
    text = _read(root / rel)
    if text is None:
        return [f"{rel} missing"]
    return [f"{rel}: {p}" for p in check_settings(text, blocks)]


def main(root):
    root = Path(root)
    problems = check_settings((root / "settings.gradle.kts").read_text(encoding="utf-8"))
    problems += check_properties((root / "gradle.properties").read_text(encoding="utf-8"))
    meta = root / "gradle" / META
    problems += check_verification(
        meta.read_text(encoding="utf-8") if meta.is_file() else None, (root / "gradle.properties").read_text(encoding="utf-8"),
        (root / "scripts" / "verify.sh").read_text(encoding="utf-8"),
    )
    # M1-69 (issue 217 item 4): the nested builds. build-logic is an included build, so the root metadata covers its artifacts and the
    # root gradle.properties applies, but its settings file has its own repositories. The fixture is a separate build with its own.
    problems += _nested_settings(root, "build-logic/settings.gradle.kts", BLOCKS)
    problems += _nested_settings(root, f"{FIXTURE}/settings.gradle.kts", BLOCKS[:1])
    fixture_props = _read(root / FIXTURE / "gradle.properties")
    if fixture_props is None:
        problems.append(f"{FIXTURE}/gradle.properties missing")
    else:
        problems += check_properties(fixture_props, f"{FIXTURE}/gradle.properties")
        off = [p for p in check_verification(None, fixture_props) if p.startswith("gradle.properties")]
        problems += _relabel(off, "gradle.properties", f"{FIXTURE}/gradle.properties")
    catalog = re.search(r'(?m)^licensee\s*=\s*"([^"]+)"', _read(root / "gradle" / "libs.versions.toml") or "")
    poms = {}
    for pom in sorted((root / FIXTURE / "repo" / FIXTURE_GROUP).glob("*/*/*.pom")):
        poms[(pom.parent.parent.name, pom.parent.name)] = hashlib.sha256(pom.read_bytes()).hexdigest()
    if catalog is None:
        problems.append("gradle/libs.versions.toml: no licensee version")
    else:
        problems += check_fixture_metadata(_read(root / FIXTURE / "gradle" / META), poms, catalog[1])
    problems += check_gate_command((root / "build.gradle.kts").read_text(encoding="utf-8"))
    for p in problems:
        print(f"gradle-repos: {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent))
