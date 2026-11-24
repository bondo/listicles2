"""Tests for scripts/check_nix_shell.py (M1-96, owner decision 7136806608 on #373). Run: python3 -I scripts/test_check_nix_shell.py

`nix develop` and `nix-shell` (flakes disabled on the owner's workstation) share shell.nix and must run the firebase-tools version pinned in
firebase/package-lock.json (M1.md R7); the shell installs it from that lockfile, so a second pin may only equal it. The static check needs no
network; the live check runs both entry points and compares `firebase --version` with the lockfile.
"""

import json
import os
import runpy
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
c = types.SimpleNamespace(**runpy.run_path(os.path.join(HERE, "check_nix_shell.py")))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


URL = "https://releases.nixos.org/nixos/26.05/nixos-26.05.1.abc/nixexprs.tar.xz"
GOOD_FLAKE = (
    '{\n  inputs.nixpkgs.url = "' + URL + '";\n  outputs = { self, nixpkgs }: let\n'
    '      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];\n    in {\n'
    "      devShells = forEachSystem (pkgs: {\n        default = import ./shell.nix { inherit pkgs; };\n      });\n    };\n}\n"
)
GOOD_SHELL = (
    "{ pkgs ? import (builtins.fetchTarball { url = locked.url; sha256 = locked.narHash; }) { } }:\n"
    "let locked = (builtins.fromJSON (builtins.readFile ./flake.lock)).nodes.nixpkgs.locked; in\n"
    "pkgs.mkShell {\n  packages = [ pkgs.nodejs_22 ];\n  shellHook = ''\n"
    '    (cd "$tally_fb" && npm ci --ignore-scripts --silent)\n'
    '    cmp -s "$tally_fb/package-lock.json" "$tally_fb/node_modules/.tally-package-lock.json"\n'
    "  '';\n}\n"
)
GOOD_LOCK = json.dumps(
    {
        "nodes": {
            "nixpkgs": {"locked": {"narHash": "sha256-abc=", "type": "tarball", "url": URL}, "original": {"type": "tarball", "url": URL}},
            "root": {"inputs": {"nixpkgs": "nixpkgs"}},
        },
        "root": "root",
        "version": 7,
    }
)
GOOD_PKG = json.dumps({"packages": {"": {}, "node_modules/firebase-tools": {"version": "15.36.0"}}})
GOOD_VERIFY = (
    "step nix-shell-tests python3 -I scripts/test_check_nix_shell.py\nstep nix-shell python3 -I scripts/check_nix_shell.py\n"
    "if command -v nix >/dev/null 2>&1; then\n  step nix-shell-live python3 -I scripts/check_nix_shell.py --live\nfi\n"
)
SHA = "a" * 64
SHA_LINE = f'          echo "{SHA}  $f.tar.xz" | sha256sum --check --status -\n'
INSTALL_LINE = '          sh "$f/install" --no-daemon --yes --no-channel-add\n'
INSTALL_STEP = (
    "      - name: Nix\n        run: |\n          f=nix-2.34.6-x86_64-linux\n"
    "          curl -sSfL --proto '=https' --proto-redir '=https' --retry 3 \"https://releases.nixos.org/nix/nix-2.34.6/$f.tar.xz\" -o \"$f.tar.xz\"\n"
    + SHA_LINE
    + '          tar -xJf "$f.tar.xz"\n'
    + INSTALL_LINE
)
GOOD_CI = (
    "  nix:\n    steps:\n" + INSTALL_STEP + "      - name: nix shell tests\n        run: python3 -I scripts/test_check_nix_shell.py\n"
    "      - name: nix shell static\n        run: python3 -I scripts/check_nix_shell.py\n"
    "      - name: nix shell live\n        run: python3 -I scripts/check_nix_shell.py --live\n"
)
PIN_SLOT = "packages = [ pkgs.nodejs_22 ];"


class RealFiles(unittest.TestCase):
    def test_repository_is_wired(self):
        files = (("flake.nix",), ("shell.nix",), ("flake.lock",), ("firebase", "package-lock.json"), ("scripts", "verify.sh"))
        found = c.problems(*(read(*f) for f in files), read(".github", "workflows", "ci.yml"))
        self.assertEqual(found, [])

    def test_firebase_tools_is_pinned_in_the_lockfile(self):
        self.assertRegex(c.pinned_version(read("firebase", "package-lock.json")), r"^\d+\.\d+\.\d+$")


class Static(unittest.TestCase):
    def check(self, flake=None, lock=None, pkg=None, verify=None, ci=None, shell=None):
        return c.problems(
            GOOD_FLAKE if flake is None else flake,
            GOOD_SHELL if shell is None else shell,
            GOOD_LOCK if lock is None else lock,
            GOOD_PKG if pkg is None else pkg,
            GOOD_VERIFY if verify is None else verify,
            GOOD_CI if ci is None else ci,
        )

    def test_good_fixture_passes(self):
        self.assertEqual(self.check(), [])

    def test_missing_default_dev_shell_fails(self):
        self.assertTrue(self.check(flake=GOOD_FLAKE.replace("devShells", "packages")))
        self.assertTrue(self.check(flake=GOOD_FLAKE.replace("default = ", "other = ")))

    def test_every_required_system_is_needed(self):
        for system in ("x86_64-linux", "aarch64-linux", "x86_64-darwin", "aarch64-darwin"):
            with self.subTest(system=system):
                self.assertTrue(self.check(flake=GOOD_FLAKE.replace(f'"{system}"', "")))

    def test_system_only_in_a_comment_does_not_count(self):
        self.assertTrue(self.check(flake=GOOD_FLAKE.replace('"x86_64-linux" ', '\n      # "x86_64-linux"\n      ')))

    def test_shell_must_hold_node_and_install_from_the_lockfile_with_ignore_scripts(self):
        for old, new in (("pkgs.nodejs_22", "pkgs.hello"), ("npm ci", "npm install"), (" --ignore-scripts", ""), ("package-lock.json", "other.json")):
            with self.subTest(old=old):
                self.assertTrue(self.check(shell=GOOD_SHELL.replace(old, new)))

    def test_a_second_pin_that_drifted_fails(self):
        for pin in ("firebase-tools@15.35.0", "firebase-tools-15.35.0", 'firebase-tools = "14.0.0"'):
            with self.subTest(pin=pin):
                self.assertTrue(self.check(shell=GOOD_SHELL.replace(PIN_SLOT, f'{PIN_SLOT} extra = "{pin}";')))
                self.assertTrue(self.check(flake=GOOD_FLAKE.replace("default =", f"# pinned: {pin}\n        default =") + f' extra = "{pin}";'))

    def test_a_second_pin_must_equal_the_lockfile_and_follow_it(self):
        same = GOOD_SHELL.replace(PIN_SLOT, f'{PIN_SLOT} extra = "firebase-tools@15.36.0";')
        self.assertEqual(self.check(shell=same), [])
        bumped = json.dumps({"packages": {"node_modules/firebase-tools": {"version": "15.37.0"}}})
        self.assertTrue(self.check(shell=same, pkg=bumped))

    def test_package_lock_without_firebase_tools_fails_closed(self):
        self.assertTrue(self.check(pkg=json.dumps({"packages": {"": {}}})))
        self.assertTrue(self.check(pkg="not json"))
        self.assertTrue(self.check(pkg=json.dumps({"packages": {"node_modules/firebase-tools": {"version": "latest"}}})))

    def test_flake_lock_must_pin_nixpkgs_by_hash(self):
        no_hash, no_nixpkgs = json.loads(GOOD_LOCK), json.loads(GOOD_LOCK)
        del no_hash["nodes"]["nixpkgs"]["locked"]["narHash"]
        del no_nixpkgs["nodes"]["nixpkgs"]
        for lock in (json.dumps(no_hash), json.dumps(no_nixpkgs), "not json", ""):
            with self.subTest(lock=lock[:20]):
                self.assertTrue(self.check(lock=lock))

    def test_input_must_be_the_locked_immutable_tarball(self):
        # A changed URL without `nix flake lock` leaves the old tarball locked; a channel moves under the lock.
        self.assertTrue(self.check(flake=GOOD_FLAKE.replace("26.05.1.abc", "26.05.2.def")))
        channel = "https://channels.nixos.org/nixos-26.05/nixexprs.tar.xz"
        self.assertTrue(self.check(flake=GOOD_FLAKE.replace(URL, channel), lock=GOOD_LOCK.replace(URL, channel)))

    def test_flake_must_use_the_shared_shell(self):
        self.assertTrue(self.check(flake=GOOD_FLAKE.replace("import ./shell.nix", "import ./other.nix")))
        self.assertTrue(self.check(flake=GOOD_FLAKE.replace("default = import ./shell.nix { inherit pkgs; };", "default = pkgs.mkShell { };")))

    def test_shell_nix_is_required_and_must_use_the_nixpkgs_flake_lock_pins(self):
        # Without flakes, shell.nix must still use the nixpkgs flake.lock pins: a second pin could drift.
        self.assertTrue(self.check(shell=""))
        for old, new in (("./flake.lock", "./other.lock"), ("builtins.fetchTarball", "builtins.fetchGit"), ("sha256 = locked.narHash;", ""),
                         ("builtins.fromJSON", "builtins.fromTOML"), ("url = locked.url;", f'url = "{URL}";')):
            with self.subTest(old=old):
                self.assertTrue(self.check(shell=GOOD_SHELL.replace(old, new)))

    def test_verify_wiring_is_required(self):
        live = "  step nix-shell-live python3 -I scripts/check_nix_shell.py --live\n"
        for old, new in (("step nix-shell-tests", "# step nix-shell-tests"), ("step nix-shell python3", "step other python3"), (live, ""),
                         ("--live\n", "--live || true\n")):
            verify = GOOD_VERIFY.replace(old, new)
            with self.subTest(old=old):
                self.assertTrue(self.check(verify=verify))
        self.assertTrue(self.check(verify=""))

    def test_ci_wiring_is_required(self):
        self.assertTrue(self.check(ci=""))
        for script in ("test_check_nix_shell.py", "check_nix_shell.py --live"):
            with self.subTest(script=script):
                self.assertTrue(self.check(ci=GOOD_CI.replace(script, "other.py")))
        self.assertTrue(self.check(ci=GOOD_CI.replace("run: ", "run: # ")))


class Installer(unittest.TestCase):
    """R1-01: the CI step downloads and runs the Nix installer; its pin and protocol flags are what make that safe."""

    def check(self, step):
        return c.problems(GOOD_FLAKE, GOOD_SHELL, GOOD_LOCK, GOOD_PKG, GOOD_VERIFY, GOOD_CI.replace(INSTALL_STEP, step))

    def edit(self, old, new):
        self.assertIn(old, INSTALL_STEP)
        return self.check(INSTALL_STEP.replace(old, new))

    def test_good_step_passes_and_the_short_check_flag_is_accepted(self):
        self.assertEqual(self.check(INSTALL_STEP), [])
        self.assertEqual(self.edit("sha256sum --check --status -", "sha256sum -c -"), [])

    def test_the_step_is_required(self):
        self.assertTrue(self.check(""))
        self.assertTrue(self.check(INSTALL_STEP.replace("releases.nixos.org/nix/", "example.org/nix/")))

    def test_download_must_be_https_with_proto_flags_and_retry(self):
        for old, new in (("--proto '=https' ", ""), ("--proto-redir '=https' ", ""), ("--retry 3 ", ""), ("https://releases", "http://releases")):
            with self.subTest(old=old):
                self.assertTrue(self.edit(old, new))

    def test_checksum_line_is_required_full_sha256_and_not_ignored(self):
        for old, new in ((SHA_LINE, ""), (SHA, SHA[:63]), (SHA, "g" * 64), ("sha256sum --check --status -", "cat"),
                         (f'echo "{SHA}', f'# echo "{SHA}'), ("sha256sum --check --status -", "sha256sum --check --status - || true")):
            with self.subTest(old=old[:20], new=new[:20]):
                self.assertTrue(self.edit(old, new))

    def test_checksum_must_run_before_the_installer(self):
        self.assertTrue(self.check(INSTALL_STEP.replace(SHA_LINE, "").replace(INSTALL_LINE, INSTALL_LINE + SHA_LINE)))

    def test_url_version_and_file_name_must_agree(self):
        self.assertTrue(self.edit("nix-2.34.6/", "nix-2.34.5/"))
        self.assertTrue(self.edit("f=nix-2.34.6-", "f=nix-2.34.5-"))


class DeployDocs(unittest.TestCase):
    """R1-02: firebase/.firebaserc exists (default project demo-tally), so the deploy docs must not say there is none."""

    def problems(self, text, exists=True):
        return c.deploy_docs_problems(text, exists)

    def test_real_docs_are_consistent_with_the_repository(self):
        self.assertEqual(self.problems(read("docs", "milestones", "M1.md"), os.path.exists(os.path.join(ROOT, "firebase", ".firebaserc"))), [])

    def test_claiming_no_firebaserc_fails_only_while_one_exists(self):
        for text in ("There is no `.firebaserc`, so every command names the project.\n", "There is **no** `.firebaserc` here\n"):
            self.assertTrue(self.problems(text + "--project tally-c1a15\n"))
        self.assertEqual(self.problems("There is no `.firebaserc`: --project tally-c1a15\n", exists=False), [])

    def test_the_docs_must_name_the_project_and_warn_about_the_demo_default(self):
        self.assertTrue(self.problems("Run the deploy.\n"))
        self.assertTrue(self.problems("--project tally-c1a15 only\n"))
        self.assertEqual(self.problems("`firebase/.firebaserc` default is demo-tally, so use --project tally-c1a15\n"), [])


class Live(unittest.TestCase):
    FLAKE_CMD = ["nix", "--extra-experimental-features", "nix-command flakes", "develop", "-c", "firebase", "--version"]
    SHELL_CMD = ["nix-shell", "--run", "firebase --version"]

    def runner(self, out="15.36.0\n", rc=0, err="", drifted=None):
        """A fake runner; `drifted` names the command (FLAKE_CMD or SHELL_CMD) that prints 15.35.0 instead."""
        calls = []

        def run(cmd):
            calls.append(cmd)
            return (0, "15.35.0\n", "") if cmd == drifted else (rc, out, err)

        run.calls = calls
        return run

    def test_matching_version_passes_and_runs_both_entry_points(self):
        run = self.runner(out="nix shell: npm ci in firebase/\n15.36.0\n")  # install noise before the version is ignored
        self.assertEqual(c.live_problems("15.36.0", run), [])
        self.assertEqual(run.calls, [self.FLAKE_CMD, self.SHELL_CMD])

    def test_drifted_version_fails_in_either_entry_point(self):
        self.assertTrue(c.live_problems("15.36.0", self.runner(out="15.35.0\n")))
        self.assertTrue(c.live_problems("15.36.0", self.runner(out="115.36.0\n")))
        for cmd in (self.FLAKE_CMD, self.SHELL_CMD):
            with self.subTest(cmd=cmd[0]):
                self.assertEqual(len(c.live_problems("15.36.0", self.runner(drifted=cmd))), 1)

    def test_failure_empty_output_or_missing_nix_fails_instead_of_skipping(self):
        self.assertTrue(c.live_problems("15.36.0", self.runner(rc=1, out="", err="boom")))
        self.assertTrue(c.live_problems("15.36.0", self.runner(out="")))

        def run(cmd):
            raise FileNotFoundError("nix")

        self.assertTrue(c.live_problems("15.36.0", run))


if __name__ == "__main__":
    unittest.main()
