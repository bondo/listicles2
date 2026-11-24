"""Checks the Nix dev shell for the rules deploy (M1-96, owner decision 7136806608 on #373). Run: python3 -I scripts/check_nix_shell.py [--live]

`nix develop -c firebase ...` on a workstation with only Nix must run the firebase-tools version pinned in firebase/package-lock.json
(owner step R7 in docs/milestones/M1.md). The shell holds Node.js from a pinned nixpkgs and installs firebase-tools from that lockfile
(`npm ci --ignore-scripts`), so there is no second pin. If a second firebase-tools version is ever written into flake.nix or shell.nix it
must equal the lockfile's. Two entry points share the definition in shell.nix: `nix develop` (flake.nix imports it) and `nix-shell` (no
experimental features; the owner's workstation has flakes disabled), and shell.nix reads the nixpkgs pin from flake.lock.

Static (default, no network): flake.nix has devShells.default for x86_64-linux, x86_64-darwin and aarch64-darwin, built from shell.nix,
which installs from the lockfile and fetches the tarball flake.lock pins; flake.lock pins the nixpkgs URL in flake.nix by hash; verify.sh
and ci.yml run this check and its tests.
--live: runs both entry points (`firebase --version`) and compares each with the lockfile (needs nix and the nixpkgs and npm hosts; the CI
`firebase` job runs it, verify.sh runs it when nix is installed).
"""

import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SYSTEMS = ("x86_64-linux", "x86_64-darwin", "aarch64-darwin")
# Flakes are enabled per call, so the check does not depend on the machine's nix.conf; nix-shell needs no experimental feature.
LIVE_CMDS = (
    ["nix", "--extra-experimental-features", "nix-command flakes", "develop", "-c", "firebase", "--version"],
    ["nix-shell", "--run", "firebase --version"],
)
TARBALL = re.compile(r"^https://releases\.nixos\.org/nixos/[\w.-]+/nixos-[\w.-]+/nixexprs\.tar\.xz$")  # a release, never a moving channel
PIN = re.compile(r"firebase-tools(?:@|-|\s*=\s*\"?)v?(\d+\.\d+\.\d+)")
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
VERIFY_STEPS = (
    r"step\s+nix-shell-tests\s+python3 -I scripts/test_check_nix_shell\.py",
    r"step\s+nix-shell\s+python3 -I scripts/check_nix_shell\.py",
    r"step\s+nix-shell-live\s+python3 -I scripts/check_nix_shell\.py --live",
)
CI_RUNS = ("scripts/test_check_nix_shell.py", "scripts/check_nix_shell.py", "scripts/check_nix_shell.py --live")


def active(text):
    return "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith(("//", "#")))


def pinned_version(package_lock):
    """firebase-tools version in firebase/package-lock.json; None when the file or the entry cannot be read."""
    try:
        version = json.loads(package_lock)["packages"]["node_modules/firebase-tools"]["version"]
    except (ValueError, KeyError, TypeError):
        return None
    return version if isinstance(version, str) and VERSION.match(version) else None


def input_url(flake):
    m = re.search(r'inputs\.nixpkgs\.url\s*=\s*"([^"]+)"', flake)
    return m.group(1) if m else None


def lock_problems(flake, lock):
    try:
        nodes = json.loads(lock)["nodes"]
        entry = nodes["nixpkgs"]
        locked, original = entry["locked"], entry["original"]
    except (ValueError, KeyError, TypeError):
        return ["flake.lock is missing, unreadable or has no locked nixpkgs input (run `nix flake lock`)"]
    out = []
    if not str(locked.get("narHash", "")).startswith("sha256-"):
        out.append("flake.lock: nixpkgs has no sha256 narHash")
    url = input_url(flake)
    if url is None:
        out.append("flake.nix has no inputs.nixpkgs.url")
    elif not TARBALL.match(url):
        out.append("flake.nix: nixpkgs must be a releases.nixos.org release tarball (permanent URL), not a channel or branch")
    elif url != locked.get("url") or url != original.get("url"):
        out.append("flake.lock does not lock the nixpkgs URL in flake.nix (run `nix flake lock`)")
    return out


def shell_problems(shell, pinned):
    sh = active(shell)
    out = []
    if not re.search(r"pkgs\.nodejs_\d+\b", sh):
        out.append("shell.nix: the shell must hold Node.js from the pinned nixpkgs (pkgs.nodejs_N)")
    if "package-lock.json" not in sh or not re.search(r"\bnpm ci\b", sh):
        out.append("shell.nix: the shell hook must install firebase-tools from firebase/package-lock.json with `npm ci`")
    elif "--ignore-scripts" not in sh:
        out.append("shell.nix: `npm ci` must run with --ignore-scripts (as CI and verify.sh do)")
    for needle, what in (
        ("builtins.fromJSON", "parse flake.lock"),
        ("builtins.readFile ./flake.lock", "read ./flake.lock"),
        ("builtins.fetchTarball", "fetch the locked tarball"),
        ("url = locked.url;", "take the url from flake.lock (no second nixpkgs pin)"),
        ("sha256 = locked.narHash;", "take the hash from flake.lock (no second nixpkgs pin)"),
    ):
        if needle not in sh:
            out.append(f"shell.nix must {what} (`{needle}`): without flakes it would use another nixpkgs than flake.lock")
    for found in PIN.findall(sh):
        if found != pinned:
            out.append(f"shell.nix pins firebase-tools {found} but firebase/package-lock.json pins {pinned}: drop the second pin")
    return out


def problems(flake, shell, lock, package_lock, verify, ci):
    out = []
    pinned = pinned_version(package_lock)
    if pinned is None:
        out.append("firebase/package-lock.json has no readable firebase-tools version (packages[node_modules/firebase-tools])")
    f = active(flake)
    if not re.search(r"\bdevShells\b", f) or not re.search(r"\bdefault\s*=", f):
        out.append("flake.nix has no devShells.default")
    for system in SYSTEMS:
        if f'"{system}"' not in f:
            out.append(f"flake.nix does not list the system {system}")
    if not re.search(r"\bdefault\s*=\s*import \./shell\.nix\b", f):
        out.append("flake.nix: devShells.default must be `import ./shell.nix { inherit pkgs; }` (one definition for both entry points)")
    for found in PIN.findall(f):
        if found != pinned:
            out.append(f"flake.nix pins firebase-tools {found} but firebase/package-lock.json pins {pinned}: drop the second pin")
    out += shell_problems(shell, pinned)
    out += lock_problems(flake, lock)
    v, w = active(verify), active(ci)
    for step in VERIFY_STEPS:
        if not re.search(rf"(?m)^\s*{step}\s*$", v):
            out.append(f"verify.sh does not run `{step.replace(chr(92), '').replace(r's+', ' ')}`")
    for script in CI_RUNS:
        if not re.search(rf"(?m)^\s*(?:-\s+)?run:\s+python3 -I {re.escape(script)}\s*$", w):
            out.append(f"ci.yml does not run `python3 -I {script}`")
    return out


def live_problems(pinned, run):
    """run(cmd) -> (returncode, stdout, stderr); a missing nix is a problem, never a skip."""
    out = []
    for cmd in LIVE_CMDS:
        label = "nix develop" if "develop" in cmd else "nix-shell"
        try:
            rc, stdout, stderr = run(cmd)
        except FileNotFoundError:
            return [f"{cmd[0]} is not installed: the live check cannot run (CI installs it; do not skip)"]
        lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
        if rc != 0 or not lines:
            out.append(f"`{label}` failed (exit {rc}): {(stderr or stdout).strip()[-400:]}")
        elif lines[-1] != pinned:
            out.append(f"`{label}` runs firebase-tools {lines[-1]} but firebase/package-lock.json pins {pinned}")
    return out


def run_command(cmd):
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    return p.returncode, p.stdout, p.stderr


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def main(argv):
    if argv not in ([], ["--live"]):
        print("usage: check_nix_shell.py [--live]", file=sys.stderr)
        return 2
    if argv:
        pinned = pinned_version(read("firebase", "package-lock.json"))
        found = ["firebase/package-lock.json has no readable firebase-tools version"] if pinned is None else live_problems(pinned, run_command)
    else:
        found = problems(
            read("flake.nix"),
            read("shell.nix"),
            read("flake.lock"),
            read("firebase", "package-lock.json"),
            read("scripts", "verify.sh"),
            read(".github", "workflows", "ci.yml"),
        )
    for p in found:
        print(f"nix-shell: {p}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
