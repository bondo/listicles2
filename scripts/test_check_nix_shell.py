"""Tests for scripts/check_nix_shell.py (M1-96, owner decision 7136806608 on #373). Run: python3 -I scripts/test_check_nix_shell.py

The Nix dev shell exists so the owner can run the rules deploy (M1.md R7) on a workstation with only Nix: `nix develop -c firebase ...`
must run the firebase-tools version pinned in firebase/package-lock.json. The shell reuses that lockfile (`npm ci`) instead of holding a
second pin; if a second pin of firebase-tools is ever written into flake.nix, it must equal the lockfile's. Two entry
points share one definition (shell.nix): `nix develop` (flake) and `nix-shell` (no experimental features; the owner's workstation has
flakes disabled), both on the nixpkgs locked in flake.lock. The static check needs no network; the live check runs both and compares
`firebase --version` with the lockfile.
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
    '{\n  inputs.nixpkgs.url = "' + URL + '";\n'
    '  outputs = { self, nixpkgs }:\n    let\n'
    '      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];\n    in {\n'
    "      devShells = forEachSystem (pkgs: {\n        default = import ./shell.nix { inherit pkgs; };\n      });\n    };\n}\n"
)
GOOD_SHELL = (
    "{ pkgs ? import (builtins.fetchTarball { url = locked.url; sha256 = locked.narHash; }) { } }:\n"
    'let locked = (builtins.fromJSON (builtins.readFile ./flake.lock)).nodes.nixpkgs.locked; in\n'
    "pkgs.mkShell {\n  packages = [ pkgs.nodejs_22 ];\n  shellHook = ''\n"
    '    (cd "$tally_fb" && npm ci --ignore-scripts --silent)\n'
    '    cmp -s "$tally_fb/package-lock.json" "$tally_fb/node_modules/.tally-package-lock.json"\n'
    "  '';\n}\n"
)
GOOD_LOCK = json.dumps(
    {
        "nodes": {
            "nixpkgs": {
                "locked": {"lastModified": 1, "narHash": "sha256-abc=", "type": "tarball", "url": URL},
                "original": {"type": "tarball", "url": URL},
            },
            "root": {"inputs": {"nixpkgs": "nixpkgs"}},
        },
        "root": "root",
        "version": 7,
    }
)
GOOD_PKG = json.dumps({"packages": {"": {}, "node_modules/firebase-tools": {"version": "15.36.0"}}})
GOOD_VERIFY = (
    "step nix-shell-tests python3 -I scripts/test_check_nix_shell.py\n"
    "step nix-shell python3 -I scripts/check_nix_shell.py\n"
    "if command -v nix >/dev/null 2>&1; then\n  step nix-shell-live python3 -I scripts/check_nix_shell.py --live\nfi\n"
)
SHA = "a" * 64
INSTALL_STEP = (
    "      - name: Nix\n        run: |\n"
    "          f=nix-2.34.6-x86_64-linux\n"
    "          curl -sSfL --proto '=https' --proto-redir '=https' --retry 3 \"https://releases.nixos.org/nix/nix-2.34.6/$f.tar.xz\" -o \"$f.tar.xz\"\n"
    f'          echo "{SHA}  $f.tar.xz" | sha256sum --check --status -\n'
    '          tar -xJf "$f.tar.xz"\n'
    '          sh "$f/install" --no-daemon --yes --no-channel-add\n'
)
GOOD_CI = (
    "  nix:\n    steps:\n"
    + INSTALL_STEP +
    "      - name: nix shell tests\n        run: python3 -I scripts/test_check_nix_shell.py\n"
    "      - name: nix shell static\n        run: python3 -I scripts/check_nix_shell.py\n"
    "      - name: nix shell live\n        run: python3 -I scripts/check_nix_shell.py --live\n"
)


class RealFiles(unittest.TestCase):
    def test_repository_is_wired(self):
        found = c.problems(
            read("flake.nix"),
            read("shell.nix"),
            read("flake.lock"),
            read("firebase", "package-lock.json"),
            read("scripts", "verify.sh"),
            read(".github", "workflows", "ci.yml"),
        )
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

    def test_node_must_come_from_nixpkgs(self):
        self.assertTrue(self.check(shell=GOOD_SHELL.replace("pkgs.nodejs_22", "pkgs.hello")))

    def test_shell_must_install_from_the_lockfile_with_ignore_scripts(self):
        self.assertTrue(self.check(shell=GOOD_SHELL.replace("npm ci", "npm install")))
        self.assertTrue(self.check(shell=GOOD_SHELL.replace(" --ignore-scripts", "")))
        self.assertTrue(self.check(shell=GOOD_SHELL.replace("package-lock.json", "other.json")))

    def test_a_second_pin_that_drifted_fails(self):
        for pin in ("firebase-tools@15.35.0", "firebase-tools-15.35.0", 'firebase-tools = "14.0.0"'):
            with self.subTest(pin=pin):
                drifted = GOOD_SHELL.replace("packages = [ pkgs.nodejs_22 ];", f'packages = [ pkgs.nodejs_22 ]; extra = "{pin}";')
                self.assertTrue(self.check(shell=drifted))
                self.assertTrue(self.check(flake=GOOD_FLAKE.replace("default =", f'# pinned: {pin}\n        default =') + f' extra = "{pin}";'))

    def test_a_second_pin_equal_to_the_lockfile_is_allowed(self):
        same = GOOD_SHELL.replace("packages = [ pkgs.nodejs_22 ];", 'packages = [ pkgs.nodejs_22 ]; extra = "firebase-tools@15.36.0";')
        self.assertEqual(self.check(shell=same), [])

    def test_lockfile_version_change_is_followed(self):
        pinned = GOOD_SHELL.replace("packages = [ pkgs.nodejs_22 ];", 'packages = [ pkgs.nodejs_22 ]; extra = "firebase-tools@15.36.0";')
        bumped = json.dumps({"packages": {"node_modules/firebase-tools": {"version": "15.37.0"}}})
        self.assertTrue(self.check(shell=pinned, pkg=bumped))

    def test_package_lock_without_firebase_tools_fails_closed(self):
        self.assertTrue(self.check(pkg=json.dumps({"packages": {"": {}}})))
        self.assertTrue(self.check(pkg="not json"))
        self.assertTrue(self.check(pkg=json.dumps({"packages": {"node_modules/firebase-tools": {"version": "latest"}}})))

    def test_flake_lock_must_pin_nixpkgs_by_hash(self):
        lock = json.loads(GOOD_LOCK)
        del lock["nodes"]["nixpkgs"]["locked"]["narHash"]
        self.assertTrue(self.check(lock=json.dumps(lock)))
        self.assertTrue(self.check(lock="not json"))
        self.assertTrue(self.check(lock=""))
        no_nixpkgs = json.loads(GOOD_LOCK)
        del no_nixpkgs["nodes"]["nixpkgs"]
        self.assertTrue(self.check(lock=json.dumps(no_nixpkgs)))

    def test_flake_lock_must_match_the_input_url(self):
        # Changing the URL in flake.nix without `nix flake lock` leaves the old tarball locked.
        self.assertTrue(self.check(flake=GOOD_FLAKE.replace("26.05.1.abc", "26.05.2.def")))

    def test_input_must_be_an_immutable_tarball_not_a_channel(self):
        channel = "https://channels.nixos.org/nixos-26.05/nixexprs.tar.xz"
        self.assertTrue(self.check(flake=GOOD_FLAKE.replace(URL, channel), lock=GOOD_LOCK.replace(URL, channel)))

    def test_flake_must_use_the_shared_shell(self):
        self.assertTrue(self.check(flake=GOOD_FLAKE.replace("import ./shell.nix", "import ./other.nix")))
        self.assertTrue(self.check(flake=GOOD_FLAKE.replace("default = import ./shell.nix { inherit pkgs; };", "default = pkgs.mkShell { };")))

    def test_shell_nix_is_required_and_must_read_the_flake_lock(self):
        # Without flakes, shell.nix must still use the nixpkgs flake.lock pins: a second pin could drift.
        self.assertTrue(self.check(shell=""))
        self.assertTrue(self.check(shell=GOOD_SHELL.replace("./flake.lock", "./other.lock")))
        self.assertTrue(self.check(shell=GOOD_SHELL.replace("builtins.fetchTarball", "builtins.fetchGit")))
        self.assertTrue(self.check(shell=GOOD_SHELL.replace("sha256 = locked.narHash;", "")))
        self.assertTrue(self.check(shell=GOOD_SHELL.replace("builtins.fromJSON", "builtins.fromTOML")))

    def test_shell_nix_must_not_hard_code_a_nixpkgs_hash_or_url(self):
        self.assertTrue(self.check(shell=GOOD_SHELL.replace("url = locked.url;", f'url = "{URL}";')))

    def test_verify_wiring_is_required(self):
        self.assertTrue(self.check(verify=""))
        self.assertTrue(self.check(verify=GOOD_VERIFY.replace("step nix-shell-tests", "# step nix-shell-tests")))
        self.assertTrue(self.check(verify=GOOD_VERIFY.replace("step nix-shell python3", "step other python3")))
        self.assertTrue(self.check(verify=GOOD_VERIFY.replace("  step nix-shell-live python3 -I scripts/check_nix_shell.py --live\n", "")))
        self.assertTrue(self.check(verify=GOOD_VERIFY.replace("--live\n", "--live || true\n")))

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

    def test_good_step_passes(self):
        self.assertEqual(self.check(INSTALL_STEP), [])

    def test_the_step_is_required(self):
        self.assertTrue(self.check(""))
        self.assertTrue(self.check(INSTALL_STEP.replace("releases.nixos.org/nix/", "example.org/nix/")))

    def test_each_download_flag_is_required(self):
        for flag in ("--proto '=https' ", "--proto-redir '=https' ", "--retry 3 "):
            with self.subTest(flag=flag):
                self.assertTrue(self.edit(flag, ""))

    def test_download_must_be_https(self):
        self.assertTrue(self.edit("https://releases", "http://releases"))

    def test_checksum_line_is_required_and_a_full_sha256(self):
        self.assertTrue(self.edit(f'          echo "{SHA}  $f.tar.xz" | sha256sum --check --status -\n', ""))
        self.assertTrue(self.edit(SHA, SHA[:63]))
        self.assertTrue(self.edit(SHA, "g" * 64))
        self.assertTrue(self.edit("sha256sum --check --status -", "cat"))
        self.assertTrue(self.edit(f'          echo "{SHA}', f'          # echo "{SHA}'))

    def test_short_check_flag_is_accepted(self):
        self.assertEqual(self.edit("sha256sum --check --status -", "sha256sum -c -"), [])

    def test_checksum_must_run_before_the_installer(self):
        sha = f'          echo "{SHA}  $f.tar.xz" | sha256sum --check --status -\n'
        install = '          sh "$f/install" --no-daemon --yes --no-channel-add\n'
        self.assertTrue(self.check(INSTALL_STEP.replace(sha, "").replace(install, install + sha)))

    def test_a_failing_checksum_must_not_be_ignored(self):
        self.assertTrue(self.edit("sha256sum --check --status -", "sha256sum --check --status - || true"))

    def test_url_version_and_file_name_must_agree(self):
        self.assertTrue(self.edit("nix-2.34.6/", "nix-2.34.5/"))
        self.assertTrue(self.edit("f=nix-2.34.6-", "f=nix-2.34.5-"))


class DeployDocs(unittest.TestCase):
    """R1-02: firebase/.firebaserc exists (default project demo-tally), so the deploy docs must not say there is none."""

    def test_real_docs_are_consistent_with_the_repository(self):
        found = c.deploy_docs_problems(read("docs", "milestones", "M1.md"), os.path.exists(os.path.join(ROOT, "firebase", ".firebaserc")))
        self.assertEqual(found, [])

    def test_claiming_no_firebaserc_while_one_exists_fails(self):
        self.assertTrue(c.deploy_docs_problems("There is no `.firebaserc`, so every command names the project.\n--project tally-c1a15\n", True))
        self.assertTrue(c.deploy_docs_problems("There is **no** `.firebaserc` here\n--project tally-c1a15\n", True))

    def test_the_claim_is_fine_when_there_really_is_none(self):
        self.assertEqual(c.deploy_docs_problems("There is no `.firebaserc`, so name the project: --project tally-c1a15\n", False), [])

    def test_the_docs_must_name_the_project_and_warn_about_the_demo_default(self):
        self.assertTrue(c.deploy_docs_problems("Run the deploy.\n", True))
        self.assertTrue(c.deploy_docs_problems("--project tally-c1a15 only\n", True))
        self.assertEqual(c.deploy_docs_problems("`firebase/.firebaserc` default is demo-tally, so use --project tally-c1a15\n", True), [])


class Live(unittest.TestCase):
    FLAKE_CMD = ["nix", "--extra-experimental-features", "nix-command flakes", "develop", "-c", "firebase", "--version"]
    SHELL_CMD = ["nix-shell", "--run", "firebase --version"]

    def runner(self, out="15.36.0\n", rc=0, err="", drifted=None):
        """A fake runner; `drifted` names the command (FLAKE_CMD or SHELL_CMD) that prints 15.35.0 instead."""
        calls = []

        def run(cmd):
            calls.append(cmd)
            if cmd == drifted:
                return 0, "15.35.0\n", ""
            return rc, out, err

        run.calls = calls
        return run

    def test_matching_version_passes_and_runs_both_entry_points(self):
        run = self.runner()
        self.assertEqual(c.live_problems("15.36.0", run), [])
        self.assertEqual(run.calls, [self.FLAKE_CMD, self.SHELL_CMD])

    def test_install_noise_before_the_version_is_ignored(self):
        self.assertEqual(c.live_problems("15.36.0", self.runner(out="nix shell: npm ci in firebase/\n15.36.0\n")), [])

    def test_drifted_version_fails_in_either_entry_point(self):
        self.assertTrue(c.live_problems("15.36.0", self.runner(out="15.35.0\n")))
        self.assertTrue(c.live_problems("15.36.0", self.runner(out="115.36.0\n")))
        for cmd in (self.FLAKE_CMD, self.SHELL_CMD):
            with self.subTest(cmd=cmd[0]):
                self.assertEqual(len(c.live_problems("15.36.0", self.runner(drifted=cmd))), 1)

    def test_failure_or_empty_output_fails(self):
        self.assertTrue(c.live_problems("15.36.0", self.runner(rc=1, out="", err="boom")))
        self.assertTrue(c.live_problems("15.36.0", self.runner(out="")))

    def test_missing_nix_fails_instead_of_skipping(self):
        def run(cmd):
            raise FileNotFoundError("nix")

        self.assertTrue(c.live_problems("15.36.0", run))


if __name__ == "__main__":
    unittest.main()
