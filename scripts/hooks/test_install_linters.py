"""Tests for scripts/install_linters.sh and scripts/linters.pins (checksum-pinned shellcheck, actionlint, zizmor).

The real archives are never downloaded here: the installer is copied into a temp tree together with a pins file that points at
local fixture archives (file:// URLs are accepted only with LINTERS_ALLOW_FILE_URLS=1; the repo's pins file is https only).

Run: python3 -I -m unittest discover -s scripts/hooks"""

import hashlib
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
INSTALLER = os.path.join(ROOT, "scripts", "install_linters.sh")
PINS = os.path.join(ROOT, "scripts", "linters.pins")
APPROVED = {  # owner approval 2026-11-15, recorded on issue #15
    "shellcheck": ("8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198", "v0.11.0", "x86_64"),
    "actionlint": ("8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8", "1.7.12", "amd64"),
    "zizmor": ("bb110cc765eca9cd7efb2e284a956be5974c60027b0970f16397d86208a9957b", "v1.32.0", "x86_64-unknown-linux-gnu"),
}
# (name, archive file name, compression, member path)
FIXTURE = [
    ("shellcheck", "shellcheck.tar.xz", "xz", "shellcheck-v0.11.0/shellcheck"),
    ("actionlint", "actionlint.tar.gz", "gz", "actionlint"),
    ("zizmor", "zizmor.tar.gz", "gz", "zizmor"),
]


def make_archive(path, comp, member, payload, extra=None):
    with tarfile.open(path, f"w:{comp}") as t:
        for name, data in [(member, payload)] + list((extra or {}).items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            t.addfile(info, io.BytesIO(data))


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Tree:
    """A temp project tree: scripts/install_linters.sh + a fixture pins file + local archives."""

    def __init__(self, test):
        self.root = tempfile.mkdtemp()
        test.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        os.makedirs(os.path.join(self.root, "scripts"))
        os.makedirs(os.path.join(self.root, "arch"))
        shutil.copy(INSTALLER, os.path.join(self.root, "scripts", "install_linters.sh"))
        self.lines = []
        for name, fname, comp, member in FIXTURE:
            p = os.path.join(self.root, "arch", fname)
            make_archive(p, comp, member, f"#!/bin/sh\necho fake {name}\n".encode(), extra={"evil": b"#!/bin/sh\necho evil\n"})
            self.lines.append([name, sha(p), member, "file://" + p])
        self.write_pins()

    def write_pins(self, raw=None):
        text = raw if raw is not None else "# fixture\n" + "".join(" ".join(line) + "\n" for line in self.lines)
        with open(os.path.join(self.root, "scripts", "linters.pins"), "w") as f:
            f.write(text)

    def run(self, file_urls=True):
        env = {"PATH": os.environ["PATH"], "HOME": self.root}
        if file_urls:
            env["LINTERS_ALLOW_FILE_URLS"] = "1"
        return subprocess.run(["bash", os.path.join(self.root, "scripts", "install_linters.sh")], cwd=self.root, env=env,
                              capture_output=True, text=True)

    def installed(self):
        d = os.path.join(self.root, ".tools", "bin")
        return sorted(os.listdir(d)) if os.path.isdir(d) else []


class Installer(unittest.TestCase):
    def test_installs_verified_binaries_and_only_those(self):
        t = Tree(self)
        r = t.run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(t.installed(), ["actionlint", "shellcheck", "zizmor"])
        for n in t.installed():
            p = os.path.join(t.root, ".tools", "bin", n)
            self.assertTrue(os.access(p, os.X_OK))
            self.assertEqual(os.stat(p).st_mode & 0o022, 0, "not group/other writable")
            with open(p) as f:
                self.assertIn(f"fake {n}", f.read())
        self.assertEqual(t.run().returncode, 0, "idempotent")

    def test_checksum_mismatch_refuses_and_installs_nothing(self):
        for which in range(3):
            t = Tree(self)
            t.lines[which][1] = "0" * 64
            t.write_pins()
            r = t.run()
            self.assertNotEqual(r.returncode, 0, which)
            self.assertIn("mismatch", r.stderr.lower())
            self.assertEqual(t.installed(), [], "all-or-nothing: a bad archive blocks the good ones too")

    def test_tampered_archive_refused(self):
        t = Tree(self)
        make_archive(os.path.join(t.root, "arch", "actionlint.tar.gz"), "gz", "actionlint", b"#!/bin/sh\necho tampered\n")
        r = t.run()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(t.installed(), [])

    def test_bad_pins_refused(self):
        good = Tree(self).lines[0]
        sha_, member, url = good[1], good[2], good[3]
        bad = [
            "",  # no tools at all
            f"shellcheck {sha_} {member}\n",  # missing url
            f"shellcheck {sha_[:-1]} {member} {url}\n",  # short sha
            f"shellcheck {sha_.upper()} {member} {url}\n",  # not lower-case hex
            f"shellcheck {'g' * 64} {member} {url}\n",
            f"shellcheck {sha_} {member} {url} extra\n",
            f"shell/check {sha_} {member} {url}\n",  # name must not contain a slash
            f"../shellcheck {sha_} {member} {url}\n",
            f"shellcheck {sha_} ../{member} {url}\n",  # member must stay inside the archive
            f"shellcheck {sha_} /{member} {url}\n",
            f"shellcheck {sha_} {member} http://example.com/x.tar.gz\n",
            f"shellcheck {sha_} {member} ftp://example.com/x.tar.gz\n",
            f"shellcheck {sha_} {member} {url}\nshellcheck {sha_} {member} {url}\n",  # duplicate name
        ]
        for raw in bad:
            t = Tree(self)
            t.write_pins(raw)
            r = t.run()
            self.assertNotEqual(r.returncode, 0, repr(raw))
            self.assertEqual(t.installed(), [], repr(raw))

    def test_file_urls_need_the_explicit_test_switch(self):
        t = Tree(self)
        r = t.run(file_urls=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(t.installed(), [])

    def test_missing_member_refused_and_extra_members_not_installed(self):
        t = Tree(self)
        t.lines[0][2] = "shellcheck-v0.11.0/not-there"
        t.write_pins()
        self.assertNotEqual(t.run().returncode, 0)
        self.assertEqual(t.installed(), [])
        t = Tree(self)
        self.assertEqual(t.run().returncode, 0)
        self.assertNotIn("evil", t.installed())

    def test_script_syntax_and_strict_mode(self):
        self.assertEqual(subprocess.run(["bash", "-n", INSTALLER]).returncode, 0)
        with open(INSTALLER, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("set -euo pipefail", text)
        self.assertNotRegex(text, r"(?m)^\s*(eval|sudo)\b")
        self.assertNotRegex(text, r"\|\s*(ba)?sh\b", "never pipe a download into a shell")


class RepoPins(unittest.TestCase):
    def entries(self):
        out = {}
        with open(PINS, encoding="utf-8") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    name, digest, member, url = line.split()
                    self.assertNotIn(name, out)
                    out[name] = (digest, member, url)
        return out

    def test_exactly_the_three_approved_archives(self):
        e = self.entries()
        self.assertEqual(set(e), set(APPROVED))
        for name, (digest, version, arch) in APPROVED.items():
            got_digest, member, url = e[name]
            self.assertEqual(got_digest, digest, name)
            self.assertTrue(url.startswith("https://github.com/"), url)
            self.assertIn(f"/releases/download/{version if name != 'actionlint' else 'v' + version}/", url)
            self.assertIn(arch, url)
            self.assertIn("linux", url.lower())
            self.assertTrue(member.endswith(name), member)

    def test_dest_is_git_ignored(self):
        with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as f:
            self.assertIn(".tools/", [line.strip() for line in f])

    def test_installer_uses_https_only_by_default(self):
        with open(INSTALLER, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("proto='=https'", text)
        self.assertRegex(text, r'--proto "\$proto"')


if __name__ == "__main__":
    unittest.main()
