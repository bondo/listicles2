#!/usr/bin/env python3
"""Checks JVM-module class files against the Android SDK's api-versions.xml for minSdk (M1-37, issue 228).

Usage: python3 -I scripts/check_java_api_level.py --api-versions FILE --min-sdk N PATH...   (PATH: a class directory or a .class file)

Android lint's NewApi skips pure JVM modules such as :core:domain, and no core library desugaring is configured, so a Java 9 to 17
member that is newer than minSdk (Stream.toList is API 34, Objects.requireNonNullElse is API 30) compiles and then crashes on old devices.
This reads every field and method reference in the class files and looks it up in api-versions.xml, following the superclass and interface
chain (also through the scanned project classes). A reference to a java/ or android/ class or member that the file does not list, or lists
with a `since` above minSdk, is a violation. invokedynamic bootstrap methods (lambdas, string concatenation) are desugared by D8 and not checked.
Known gaps: a class used only by checkcast, instanceof or a catch clause (no member reference) is not looked up; a project class whose
parent is a third-party class that is not scanned is not resolved further.

Exit: 0 clean, 1 violations, 2 the check could not run (missing, empty or unreadable api file, no class files, a corrupt class file, bad usage).
Whole-number arithmetic only: a level is the tuple (major, minor) of integers, so `37.0` and `26.1` are above 26.
"""

import argparse
import heapq
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET

CHECKED_PREFIXES = ("java/", "android/")
ANCHOR_CLASSES = ("java/lang/Object", "java/util/List")  # a file without these is not a platform api-versions.xml
LEVEL = re.compile(r"(\d+)(?:\.(\d+))?")
ONE = (1, 0)


class CheckError(Exception):
    """The check cannot give an answer: the caller must fail, not pass."""


def level(text, where):
    m = LEVEL.fullmatch(text.strip()) if text else None
    if not m:
        raise CheckError(f"{where}: unreadable since=\"{text}\"")
    return (int(m.group(1)), int(m.group(2) or 0))


class Api:
    """classes[name] = (since, {member key: since}, [(parent, since)]); a member key is "M:name(desc)ret" or "F:name"."""

    def __init__(self, path):
        self.classes = {}
        try:
            with open(path, "rb") as f:
                for _, el in ET.iterparse(f):
                    if el.tag == "class":
                        self.add(el)
                        el.clear()
        except OSError as e:
            raise CheckError(f"cannot read api-versions.xml {path}: {e.strerror}") from e
        except ET.ParseError as e:
            raise CheckError(f"{path} is not well-formed XML (truncated?): {e}") from e
        missing = [c for c in ANCHOR_CLASSES if c not in self.classes]
        if missing:
            raise CheckError(f"{path} is not a platform api-versions.xml: it lists no {', '.join(missing)}")

    def add(self, el):
        name = el.get("name", "")
        since = level(el.get("since", "1"), name)
        members, parents = {}, []
        for child in el:
            s = level(child.get("since", "1"), f"{name} {child.get('name')}")
            if child.tag == "method":
                members["M:" + child.get("name", "")] = s
            elif child.tag == "field":
                members["F:" + child.get("name", "")] = s
            elif child.tag in ("extends", "implements"):
                parents.append((child.get("name", ""), s))
        self.classes[name] = (since, members, parents)


class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, fmt):
        size = struct.calcsize(fmt)
        if self.pos + size > len(self.data):
            raise CheckError("class file is truncated")
        (v,) = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += size
        return v

    def advance(self, n):
        if self.pos + n > len(self.data):
            raise CheckError("class file is truncated")
        self.pos += n

    def raw(self, n):
        self.advance(n)
        return self.data[self.pos - n : self.pos]


def parse_class(data):
    """(name, super, interfaces, declared member keys, refs); a ref is (owner, member key, display)."""
    r = Reader(data)
    if r.take(">I") != 0xCAFEBABE:
        raise CheckError("not a class file (bad magic)")
    r.advance(4)  # minor, major
    count = r.take(">H")
    pool, i = {}, 1
    while i < count:
        tag = r.take(">B")
        if tag == 1:
            pool[i] = (1, r.raw(r.take(">H")).decode("utf-8", errors="replace"))
        elif tag in (3, 4):
            r.advance(4)
        elif tag in (5, 6):
            r.advance(8)
            i += 1  # long and double take two slots
        elif tag in (7, 8, 16, 19, 20):
            pool[i] = (tag, r.take(">H"))
        elif tag in (9, 10, 11, 12, 17, 18):
            pool[i] = (tag, r.take(">H"), r.take(">H"))
        elif tag == 15:
            pool[i] = (15, r.take(">B"), r.take(">H"))
        else:
            raise CheckError(f"class file has an unknown constant pool tag {tag}")
        i += 1

    def utf8(idx):
        return pool[idx][1]

    def class_name(idx):
        return utf8(pool[idx][1]) if idx else None

    try:
        r.advance(2)  # access flags
        name = class_name(r.take(">H"))
        sup = class_name(r.take(">H"))
        interfaces = [class_name(r.take(">H")) for _ in range(r.take(">H"))]
        declared = set()
        for kind in ("F", "M"):
            for _ in range(r.take(">H")):
                r.advance(2)
                n, d = utf8(r.take(">H")), utf8(r.take(">H"))
                declared.add(f"F:{n}" if kind == "F" else f"M:{n}{d}")
                for _ in range(r.take(">H")):
                    r.advance(2)
                    r.advance(r.take(">I"))
        excluded = set()  # Methodref entries that only name a bootstrap method of an invokedynamic
        for _ in range(r.take(">H")):
            attr, length = utf8(r.take(">H")), r.take(">I")
            if attr == "BootstrapMethods":
                end = r.pos + length
                for _ in range(r.take(">H")):
                    handle = pool[r.take(">H")]
                    excluded.add(handle[2])
                    r.advance(2 * r.take(">H"))
                r.pos = end
            else:
                r.advance(length)
        refs = []
        for idx, e in pool.items():
            if e[0] in (9, 10, 11) and idx not in excluded:
                owner, nat = class_name(e[1]), pool[e[2]]
                n, d = utf8(nat[1]), utf8(nat[2])
                refs.append((owner, f"F:{n}" if e[0] == 9 else f"M:{n}{d}", f"{owner}.{n}" if e[0] == 9 else f"{owner}.{n}{d}"))
    except (KeyError, IndexError, TypeError) as e:
        raise CheckError(f"class file is corrupt ({type(e).__name__})") from e
    return name, sup, interfaces, declared, refs


class Checker:
    def __init__(self, api, min_sdk):
        self.api, self.limit = api, (min_sdk, 0)
        self.project = {}  # scanned class name -> (super, interfaces, declared member keys)

    def lookup(self, owner, key):
        """(lowest level at which the member exists on `owner`, whether some parent was unknown); level None if it is on no path."""
        best, opaque = None, False
        reached = {}
        queue = [(ONE, owner)]
        while queue:
            lvl, cls = heapq.heappop(queue)
            if cls in reached and reached[cls] <= lvl:
                continue
            reached[cls] = lvl
            if cls in self.api.classes:
                since, members, parents = self.api.classes[cls]
                lvl = max(lvl, since)
                if key in members and (best is None or max(lvl, members[key]) < best):
                    best = max(lvl, members[key])
                nxt = parents
            elif cls in self.project:
                sup, interfaces, declared = self.project[cls]
                if key in declared:
                    best = ONE if best is None else min(best, ONE)
                nxt = [(p, ONE) for p in [sup, *interfaces] if p]
            else:
                opaque = opaque or not cls.startswith(CHECKED_PREFIXES)
                continue
            for parent, since in nxt:
                heapq.heappush(queue, (max(lvl, since), parent))
        if best is None and "java/lang/Object" in self.api.classes:
            members = self.api.classes["java/lang/Object"][1]
            best = members.get(key)
        return best, opaque

    def unknown(self, cls):
        return cls.startswith(CHECKED_PREFIXES) and cls not in self.api.classes

    def check_ref(self, owner, key, shown):
        if owner.startswith("["):
            return None
        if owner in self.project or owner in self.api.classes:
            lvl, opaque = self.lookup(owner, key)
            if lvl is None:
                return None if opaque else f"{shown} is not in the Android API (api-versions.xml lists no such member)"
            return f"{shown} requires API {fmt(lvl)} (minSdk {self.limit[0]})" if lvl > self.limit else None
        return f"{shown} is not in the Android API (api-versions.xml lists no class {owner})" if self.unknown(owner) else None

    def check_header(self, name, sup, interfaces):
        for parent in [sup, *interfaces]:
            if parent and self.unknown(parent):
                yield f"{name} extends or implements {parent}, which is not in the Android API (api-versions.xml lists no such class)"
            elif parent in self.api.classes and self.api.classes[parent][0] > self.limit:
                yield f"{name} extends or implements {parent}, which requires API {fmt(self.api.classes[parent][0])} (minSdk {self.limit[0]})"


def fmt(lvl):
    return str(lvl[0]) if lvl[1] == 0 else f"{lvl[0]}.{lvl[1]}"


def class_files(paths):
    found = []
    for p in paths:
        if os.path.isfile(p):
            found.append(p)
        elif os.path.isdir(p):
            found += [os.path.join(d, f) for d, _, fs in os.walk(p) for f in fs if f.endswith(".class")]
        else:
            raise CheckError(f"{p} does not exist")
    if not found:
        raise CheckError("no class files found under " + " ".join(paths))
    return sorted(found)


def run(api_path, min_sdk, paths):
    checker = Checker(Api(api_path), min_sdk)
    parsed = []
    for path in class_files(paths):
        try:
            with open(path, "rb") as f:
                parsed.append(parse_class(f.read()))
        except CheckError as e:
            raise CheckError(f"{path}: {e}") from e
    for name, sup, interfaces, declared, _ in parsed:
        checker.project[name] = (sup, interfaces, declared)
    problems = set()
    for name, sup, interfaces, _, refs in parsed:
        problems.update(f"{name}: {p}" for p in checker.check_header(name, sup, interfaces))
        for owner, key, shown in refs:
            msg = checker.check_ref(owner, key, shown)
            if msg:
                problems.add(f"{name}: {msg}")
    return len(parsed), sorted(problems)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--api-versions", required=True)
    ap.add_argument("--min-sdk", required=True)
    ap.add_argument("paths", nargs="+")
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2
    try:
        if not args.min_sdk.isdigit():
            raise CheckError(f"--min-sdk must be a whole number, not {args.min_sdk!r}")
        scanned, problems = run(args.api_versions, int(args.min_sdk), args.paths)
    except CheckError as e:
        print(f"java-api-level: cannot check: {e}")
        return 2
    for p in problems:
        print(f"java-api-level: {p}")
    if problems:
        print(f"java-api-level: {len(problems)} reference(s) above minSdk {args.min_sdk} in {scanned} class file(s)")
        return 1
    print(f"java-api-level: {scanned} class file(s) use only API {args.min_sdk} or older")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
