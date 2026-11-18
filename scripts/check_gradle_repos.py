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


def _strip(text, blank_strings=False):
    """Kotlin source without // and /* */ comments; string contents become spaces if blank_strings."""
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
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


def _block(text, name):
    """Body of the first `name { ... }` block, or None."""
    spans = _spans(text, name)
    return text[spans[0][0] : spans[0][1]] if spans else None


def _filtered(repos, call):
    """True if the google() call at match `call` has a content { include...(...) } filter."""
    brace = re.compile(r"\s*\{").match(repos, call.end())
    body = _body(repos, brace.end() - 1) if brace else None
    content = _block(body, "content") if body is not None else None
    return content is not None and re.search(r"\binclude\w*\s*\(", content) is not None


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
        central = re.search(r"\bmavenCentral\s*\(\s*\)", repos)
        if mirror < 0:
            problems.append(f"{name}: Maven Central mirror {MIRROR} missing")
        elif central is None:
            problems.append(f"{name}: mavenCentral() fallback missing")
        elif mirror > central.start():
            problems.append(f"{name}: Maven Central mirror must come before mavenCentral()")
        # A qualified call (this.google(), foo.google()) counts too; strings are blanked, so URLs never match.
        calls = re.finditer(r"(?<!\w)google\b\s*(\(\s*\))?", repos)
        if not all(_filtered(repos, call) for call in calls):
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
    for line in props_text.splitlines():
        m = None if line.lstrip().startswith(("#", "!")) else prop.fullmatch(line.rstrip()) or prop.match(line)
        if m and m.group(1).lower() in ("off", "lenient"):
            problems.append(f"gradle.properties: {VERIFICATION_PROP}={m.group(1).lower()} disables verification")
    flags = re.compile(
        r"(?:--dependency-verification|\s-F|-D" + re.escape(VERIFICATION_PROP) + r")(?:\s*=\s*|\s+)(?:off|lenient)\b", re.I
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
