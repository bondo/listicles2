"""Checks the Nix dev shell for the rules deploy (M1-96, owner decision 7136806608 on #373). Run: python3 -I scripts/check_nix_shell.py [--live]

`nix develop` (flake.nix) and `nix-shell` (no experimental features; flakes are disabled on the owner's workstation) share shell.nix: Node.js
from the nixpkgs flake.lock pins, firebase-tools by `npm ci --ignore-scripts` from firebase/package-lock.json, so there is no second pin (one
written into flake.nix or shell.nix must equal the lockfile's). Static (default, no network): the files above, flake.lock, verify.sh and ci.yml
are wired, the ci.yml Nix installer step keeps its https-only curl flags and a sha256 check before the install (as the gitleaks download does
in scripts/check_ci_hardening.py), and M1.md R7 does not claim there is no firebase/.firebaserc (it names only the demo project).
--live: runs both entry points and compares `firebase --version` with the lockfile (the CI `firebase` job runs it, verify.sh when nix exists).
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SYSTEMS = ("x86_64-linux", "aarch64-linux", "x86_64-darwin", "aarch64-darwin")
# Flakes are enabled per call, so the check does not depend on the machine's nix.conf; nix-shell needs no experimental feature.
LIVE_CMDS = (
    ["nix", "--extra-experimental-features", "nix-command flakes", "develop", "-c", "firebase", "--version"],
    ["nix-shell", "--run", "firebase --version"],
)
TARBALL = re.compile(r"^https://releases\.nixos\.org/nixos/[\w.-]+/nixos-[\w.-]+/nixexprs\.tar\.xz$")  # a release, never a moving channel
PIN = re.compile(r"firebase-tools(?:@|-|\s*=\s*\"?)v?(\d+\.\d+\.\d+)")
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
VERIFY_STEPS = (
    "step nix-shell-tests python3 -I scripts/test_check_nix_shell.py",
    "step nix-shell python3 -I scripts/check_nix_shell.py",
    "step nix-shell-live python3 -I scripts/check_nix_shell.py --live",
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


def pin_problems(name, text, pinned):
    return [f"{name} pins firebase-tools {v} but firebase/package-lock.json pins {pinned}: drop the second pin" for v in PIN.findall(text) if v != pinned]


def shell_problems(shell, pinned):
    sh = active(shell)
    out = pin_problems("shell.nix", sh, pinned)
    if not re.search(r"pkgs\.nodejs_\d+\b", sh):
        out.append("shell.nix: the shell must hold Node.js from the pinned nixpkgs (pkgs.nodejs_N)")
    if "package-lock.json" not in sh or not re.search(r"\bnpm ci\b", sh):
        out.append("shell.nix: the shell hook must install firebase-tools from firebase/package-lock.json with `npm ci`")
    elif "--ignore-scripts" not in sh:
        out.append("shell.nix: `npm ci` must run with --ignore-scripts (as CI and verify.sh do)")
    for needle in ("builtins.fromJSON", "builtins.readFile ./flake.lock", "builtins.fetchTarball", "url = locked.url;", "sha256 = locked.narHash;"):
        if needle not in sh:
            out.append(f"shell.nix must contain `{needle}`: without flakes it would use another nixpkgs than flake.lock")
    return out


def installer_problems(ci):
    """The CI step that downloads the Nix release tarball and runs its installer (M1-96 review R1-01)."""
    steps = re.split(r"(?m)^\s*- (?=\w+:)", active(ci))
    step = next((t for t in steps if "/nix/nix-" in t and "install" in t), None)
    if step is None:
        return ["ci.yml has no step that installs Nix from the pinned release tarball (releases.nixos.org/nix/nix-X.Y.Z/...)"]
    out = []
    m = re.search(r"curl\b[^\n]*", step)
    curl = m.group(0) if m else ""
    if not re.search(r'https://releases\.nixos\.org/nix/nix-(\d+\.\d+\.\d+)/', curl):
        out.append("ci.yml: the Nix installer must be downloaded with curl from https://releases.nixos.org/nix/nix-X.Y.Z/")
    for flag in ("--proto", "--proto-redir"):
        if not re.search(rf"{flag}\s+'?=https'?(?=\s)", curl):
            out.append(f"ci.yml: the Nix installer download needs curl {flag} =https")
    if not re.search(r"--retry\s+\d+", curl):
        out.append("ci.yml: the Nix installer download needs curl --retry")
    sha = re.search(r'(?m)^[^#\n]*echo\s+"[0-9a-f]{64}\s+\S+"\s*\|\s*sha256sum\s+(?:-c|--check)\b[^\n]*$', step)
    if sha is None:
        out.append("ci.yml: the Nix installer archive must be checked with `echo \"<64 hex sha256>  <file>\" | sha256sum --check`")
    else:
        if "||" in sha.group(0):
            out.append("ci.yml: the Nix installer checksum result must not be ignored (|| ...)")
        run = re.search(r"(?m)^[^#\n]*\binstall\b", step[sha.end():])
        before = re.search(r"(?m)^[^#\n]*\bsh\b[^\n]*/install\b", step[: sha.start()])
        if run is None or before:
            out.append("ci.yml: the Nix installer must run after its sha256 check")
    version = re.search(r"nix-(\d+\.\d+\.\d+)/", curl)
    name = re.search(r"(?m)^\s*f=nix-(\d+\.\d+\.\d+)-", step)
    if version and (name is None or name.group(1) != version.group(1)):
        out.append("ci.yml: the Nix installer file name (f=nix-X.Y.Z-...) and the download URL version differ")
    return out


def deploy_docs_problems(m1, firebaserc_exists):
    """docs/milestones/M1.md R7 (M1-96 review R1-02): firebase/.firebaserc names only the demo project, so the project is always passed."""
    out = []
    if "--project tally-c1a15" not in m1:
        out.append("docs/milestones/M1.md: the deploy command must pass --project tally-c1a15")
    if firebaserc_exists:
        if re.search(r"no\W{0,4}`\.firebaserc`", m1):
            out.append("docs/milestones/M1.md says there is no .firebaserc, but firebase/.firebaserc exists")
        if "demo-tally" not in m1:
            out.append("docs/milestones/M1.md: say that firebase/.firebaserc defaults to demo-tally, which is why --project is required")
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
    out += pin_problems("flake.nix", f, pinned) + shell_problems(shell, pinned) + lock_problems(flake, lock)
    v, w = active(verify), active(ci)
    for step in VERIFY_STEPS:
        if not re.search(rf"(?m)^\s*{re.escape(step)}\s*$", v):
            out.append(f"verify.sh does not run `{step}`")
    for script in CI_RUNS:
        if not re.search(rf"(?m)^\s*(?:-\s+)?run:\s+python3 -I {re.escape(script)}\s*$", w):
            out.append(f"ci.yml does not run `python3 -I {script}`")
    return out + installer_problems(ci)


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
        found += deploy_docs_problems(read("docs", "milestones", "M1.md"), os.path.exists(os.path.join(ROOT, "firebase", ".firebaserc")))
    for p in found:
        print(f"nix-shell: {p}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
