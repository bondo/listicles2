{
  description = "Tally dev shell: Node.js and the firebase-tools pinned in firebase/package-lock.json (M1-96)";

  # One nixpkgs pin (this URL plus the narHash in flake.lock; shell.nix reads the same lock). A release tarball, not a github:
  # input, because the tarball URL is permanent. Update: replace the URL with a newer
  # https://releases.nixos.org/nixos/<release>/nixos-<release>.<n>.<rev>/nixexprs.tar.xz and run `nix flake lock`.
  inputs.nixpkgs.url = "https://releases.nixos.org/nixos/26.05/nixos-26.05.15079.0dc498bfe49b/nixexprs.tar.xz";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forEachSystem = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      devShells = forEachSystem (pkgs: {
        default = import ./shell.nix { inherit pkgs; };
      });
    };
}
