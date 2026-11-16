#!/usr/bin/env bash
# Runs shellcheck (-S warning) on shell files, actionlint and zizmor (--offline) on workflows, using the linters pinned in
# scripts/linters.pins. Anything missing or at another version is (re)installed by scripts/install_linters.sh, which
# checks the sha256 of every archive first. No config files, no thresholds, no ignores: a finding fails the run.
# Usage: scripts/lint_workflows.sh                    all tracked shell files (*.sh, .githooks/*) and .github/workflows
#        scripts/lint_workflows.sh shell FILE...      shellcheck only
#        scripts/lint_workflows.sh workflows DIR      actionlint and zizmor on DIR (the tests use a temp directory)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
bin=.tools/bin
die() { echo "lint_workflows: $*" >&2; exit 1; }

pinned() { grep -E "^$1 " scripts/linters.pins | head -1 | sed -E 's#.*/download/v?([0-9][0-9.]*)/.*#\1#'; }
installed() {
  case "$1" in
    shellcheck) "$bin/shellcheck" --version 2>/dev/null | awk '/^version:/ {print $2}' ;;
    actionlint) "$bin/actionlint" -version 2>/dev/null | head -1 ;;
    zizmor) "$bin/zizmor" --version 2>/dev/null | awk '{print $2}' ;;
  esac
}
current() {
  local t
  for t in shellcheck actionlint zizmor; do
    [ -x "$bin/$t" ] && [ -n "$(pinned "$t")" ] && [ "$(installed "$t")" = "$(pinned "$t")" ] || return 1
  done
}
current || { ./scripts/install_linters.sh >&2 || die "could not install the pinned linters"; }
current || die "installed linters do not match scripts/linters.pins"

run_shell() { "$bin/shellcheck" -S warning -x -- "$@"; }
run_workflows() {
  local dir="$1" files=()
  [ -d "$dir" ] || { echo "lint_workflows: no such directory: $dir" >&2; return 1; }
  shopt -s nullglob
  files=("$dir"/*.yml "$dir"/*.yaml)
  shopt -u nullglob
  [ "${#files[@]}" -gt 0 ] || { echo "lint_workflows: no workflow files in $dir" >&2; return 1; }
  local rc=0
  "$bin/actionlint" "${files[@]}" || rc=1
  "$bin/zizmor" --offline --no-ignores --strict-collection --no-progress "$dir" || rc=1
  return "$rc"
}

case "${1:-all}" in
  shell)
    shift
    [ "$#" -gt 0 ] || die "shell needs at least one file"
    run_shell "$@"
    ;;
  workflows)
    [ "$#" -eq 2 ] || die "workflows needs exactly one directory"
    run_workflows "$2"
    ;;
  all)
    [ "$#" -le 1 ] || die "unexpected arguments"
    rc=0
    mapfile -t sh_files < <(git ls-files '*.sh' '.githooks/*')
    [ "${#sh_files[@]}" -gt 0 ] || die "no shell files found"
    run_shell "${sh_files[@]}" || rc=1
    run_workflows .github/workflows || rc=1
    exit "$rc"
    ;;
  *) die "unknown mode '$1' (shell FILE... | workflows DIR | no arguments)" ;;
esac
