#!/usr/bin/env bash
# Installs the owner-approved linters (shellcheck, actionlint, zizmor) into .tools/bin/ (git-ignored).
# Every archive is downloaded, its sha256 compared with scripts/linters.pins, and only then is anything extracted.
# Any mismatch or malformed pin aborts with nothing installed. The binaries are never run here.
set -euo pipefail

here="$(CDPATH='' cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"
pins="$here/linters.pins"
dest="$root/.tools/bin"
die() { echo "install_linters: $*" >&2; exit 1; }

# file:// URLs exist for the unit tests only; the repo's pins file is https only.
proto='=https'
if [ "${LINTERS_ALLOW_FILE_URLS:-}" = 1 ]; then
  proto='=https,file'
else
  [ "$(uname -s)-$(uname -m)" = "Linux-x86_64" ] || die "the pinned archives are Linux x86_64 only (this is $(uname -s)-$(uname -m))"
fi

names=(); shas=(); members=(); urls=()
while read -r name sha member url extra; do
  case "$name" in '' | '#'*) continue ;; esac
  [ -n "$url" ] && [ -z "${extra:-}" ] || die "pins line for '$name' needs exactly: name sha256 member url"
  [[ "$name" =~ ^[a-z][a-z0-9-]*$ ]] || die "bad tool name '$name'"
  [[ "$sha" =~ ^[0-9a-f]{64}$ ]] || die "bad sha256 for '$name' (64 lower-case hex digits)"
  [[ "$member" =~ ^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$ ]] && [[ "$member" != *..* ]] || die "bad archive member for '$name'"
  case "$url" in
    https://*) ;;
    file://*) [ "${LINTERS_ALLOW_FILE_URLS:-}" = 1 ] || die "file:// URL for '$name' is not allowed" ;;
    *) die "URL for '$name' must be https" ;;
  esac
  for seen in ${names[@]+"${names[@]}"}; do [ "$seen" != "$name" ] || die "duplicate tool '$name'"; done
  names+=("$name"); shas+=("$sha"); members+=("$member"); urls+=("$url")
done < "$pins"
[ "${#names[@]}" -gt 0 ] || die "no tools in $pins"

# Work under .tools (same filesystem as .tools/bin) so the final step is a rename.
mkdir -p "$root/.tools"
tmp="$(mktemp -d "$root/.tools/.install.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

for i in "${!names[@]}"; do
  curl -fsSL --retry 5 --proto "$proto" --proto-redir "$proto" -o "$tmp/$i.archive" "${urls[$i]}" || die "download failed for ${names[$i]}"
  got="$(sha256sum "$tmp/$i.archive" | cut -d' ' -f1)"
  [ "$got" = "${shas[$i]}" ] || die "sha256 mismatch for ${names[$i]}: expected ${shas[$i]}, got $got; nothing installed"
done

# All archives verified: extract only the one named member of each, still before touching the destination.
for i in "${!names[@]}"; do
  mkdir "$tmp/x$i"
  tar -xf "$tmp/$i.archive" -C "$tmp/x$i" -- "${members[$i]}" || die "member '${members[$i]}' not found in ${names[$i]} archive"
  [ -f "$tmp/x$i/${members[$i]}" ] && [ ! -L "$tmp/x$i/${members[$i]}" ] || die "'${members[$i]}' is not a regular file"
done

# Stage every binary first (an error here leaves .tools/bin untouched), then rename each into place.
mkdir -p "$tmp/stage" "$dest"
for i in "${!names[@]}"; do
  install -m 0755 "$tmp/x$i/${members[$i]}" "$tmp/stage/${names[$i]}" || die "staging ${names[$i]} failed; nothing replaced"
done
# bin/actionlint is a wrapper that pins the installed shellcheck and disables pyflakes (real binary in libexec): PATH is irrelevant.
if [ -f "$tmp/stage/actionlint" ]; then
  mv "$tmp/stage/actionlint" "$tmp/stage/actionlint.real"
  printf '#!/bin/sh\nd=$(CDPATH= cd -- "${0%%/*}" && pwd)\nexec "$d/../libexec/actionlint" "-shellcheck=$d/shellcheck" -pyflakes= "$@"\n' > "$tmp/stage/actionlint"
  chmod 0755 "$tmp/stage/actionlint"
  mkdir -p "$root/.tools/libexec"
  mv -f "$tmp/stage/actionlint.real" "$root/.tools/libexec/actionlint"
fi
for i in "${!names[@]}"; do
  mv -f "$tmp/stage/${names[$i]}" "$dest/${names[$i]}"
  echo "installed ${names[$i]} (sha256 ${shas[$i]})"
done
