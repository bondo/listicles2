"""Checks the Gradle repository setup that keeps cold dependency downloads from failing on HTTP 429.

Maven Central (repo.maven.apache.org, behind Cloudflare) answers a share of requests from shared cloud
egress IPs with 429. Gradle disables a repository for the rest of the build once its retries for one
request run out, so a single unlucky burst fails the whole build. The setup this checks:
  * Google's Maven Central mirror is listed before mavenCentral() (mavenCentral() stays as fallback),
  * google() only gets the groups it hosts, so other artifacts are not looked up there first,
  * Gradle retries repository requests often enough, with backoff, to ride out a 429 burst.
It also checks Gradle dependency verification (gradle/verification-metadata.xml, sha256 for every artifact), so a
mirror or CDN problem cannot silently change an artifact; Gradle itself enforces it in every build.
Run: python3 -I scripts/check_gradle_repos.py  (exit 1 and one line per problem when the setup is off).
"""

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
ONLY_GOOGLE = re.compile(r"\s*google\s*\(\s*\)\s*;?\s*")


def _strip(text, blank_strings=False):
    """Kotlin source without // and (nested) /* */ comments, each block comment replaced by one space so tokens never glue.

    String and char literal contents become spaces if blank_strings. Block comments nest in Kotlin."""
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            depth, i = 1, i + 2
            while i < n and depth:
                if text.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif text.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
            out.append(" ")
        elif text[i] == "'" and (char := CHAR_LITERAL.match(text, i)) is not None:
            out.append("'" + " " * (char.end() - i - 2) + "'" if blank_strings else char.group())
            i = char.end()
        elif text[i] == '"':
            out.append('"')
            i += 1
            while i < n and text[i] != '"':
                step = 2 if text[i] == "\\" else 1
                out.append(" " * step if blank_strings else text[i : i + step])
                i += step
            if i < n:
                out.append('"')
                i += 1
        else:
            out.append(text[i])
            i += 1
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


def _repositories(text, name):
    """Every repositories { } body inside every `name { }` block, joined in order (Gradle adds them all up).

    Returns (code with string contents blanked, code with strings kept); both have the same length."""
    blanked, kept = _strip(text, blank_strings=True), _strip(text)
    parts = []
    for o_start, o_end in _spans(blanked, name):
        for r_start, r_end in _spans(blanked[o_start:o_end], "repositories"):
            parts.append((o_start + r_start, o_start + r_end))
    if not parts:
        return None, None
    return "\n".join(blanked[a:b] for a, b in parts), "\n".join(kept[a:b] for a, b in parts)


def check_settings(text):
    problems = []
    for name in BLOCKS:
        repos, repos_text = _repositories(text, name)
        if repos is None:
            problems.append(f"{name}: no repositories block")
            continue
        mirror = repos_text.find(f'"{MIRROR}"')
        central = re.search(r"\bmavenCentral\s*(?:\(\s*\)|\{\s*\})", repos)  # mavenCentral() or an empty mavenCentral { }
        if mirror < 0:
            problems.append(f"{name}: Maven Central mirror {MIRROR} missing")
        elif central is None:
            problems.append(f"{name}: mavenCentral() fallback missing")
        elif mirror > central.start():
            problems.append(f"{name}: Maven Central mirror must come before mavenCentral()")
        # A qualified call (this.google(), foo.google()) counts too; strings are blanked, so URLs never match.
        calls = re.finditer(r"(?<!\w)google\b\s*(\(\s*\))?", repos)
        exclusive = _exclusive(repos)
        if not all(_filtered(repos, c) or any(a <= c.start() < b for a, b in exclusive) for c in calls):
            problems.append(f"{name}: google() needs a content filter")
    return problems


def check_properties(text):
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
            problems.append(f"gradle.properties: {key} missing or not a number")
        elif int(value) < minimum:
            problems.append(f"gradle.properties: {key}={value} is below {minimum}")
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


def main(root):
    root = Path(root)
    problems = check_settings((root / "settings.gradle.kts").read_text(encoding="utf-8"))
    problems += check_properties((root / "gradle.properties").read_text(encoding="utf-8"))
    meta = root / "gradle" / META
    problems += check_verification(
        meta.read_text(encoding="utf-8") if meta.is_file() else None, (root / "gradle.properties").read_text(encoding="utf-8"),
        (root / "scripts" / "verify.sh").read_text(encoding="utf-8"),
    )
    for p in problems:
        print(f"gradle-repos: {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent))
