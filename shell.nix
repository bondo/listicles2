# Dev shell for the rules deploy (M1-96, owner decision 7136806608 on #373): Node.js from the nixpkgs that flake.lock pins, and
# firebase-tools from firebase/package-lock.json (`npm ci`), so there is no second version that can drift.
# Two entry points, one definition:
#   nix-shell --run "firebase --version"                       no experimental features needed
#   nix develop -c firebase --version                          flake.nix imports this file; needs nix-command and flakes
# Without flakes the pin is read from flake.lock (url and narHash), so both entry points use the same nixpkgs.
let
  locked = (builtins.fromJSON (builtins.readFile ./flake.lock)).nodes.nixpkgs.locked;
in
{ pkgs ? import
    (builtins.fetchTarball {
      url = locked.url;
      sha256 = locked.narHash;
    })
    { }
}:
pkgs.mkShell {
  # Node 22 is the major CI uses (scripts/check_ci_hardening.py).
  packages = [ pkgs.nodejs_22 ];
  shellHook = ''
    tally_root=$PWD
    while [ "$tally_root" != / ] && [ ! -f "$tally_root/flake.nix" ]; do tally_root=$(dirname "$tally_root"); done
    tally_fb="$tally_root/firebase"
    if [ -f "$tally_fb/package-lock.json" ]; then
      if ! cmp -s "$tally_fb/package-lock.json" "$tally_fb/node_modules/.tally-package-lock.json"; then
        echo "nix shell: npm ci in firebase/ (firebase-tools from package-lock.json)" >&2
        (cd "$tally_fb" && npm ci --ignore-scripts --silent --no-audit --no-fund) >&2 \
          && cp "$tally_fb/package-lock.json" "$tally_fb/node_modules/.tally-package-lock.json"
      fi
      export PATH="$tally_fb/node_modules/.bin:$PATH"
    fi
    unset tally_root tally_fb
  '';
}
