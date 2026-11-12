#!/usr/bin/env bash
# Claude Code status line: model, branch, context %. Also records the context % for the context-guard hook
# (scripts/hooks/context_guard.py) when it runs (interactive CLI only; headless sessions use the transcript instead).
# Input: status JSON on stdin (context_window.used_percentage, session_id, model.display_name, workspace.current_dir).
in=$(cat)
pct=$(printf '%s' "$in" | jq -r '.context_window.used_percentage // empty' 2>/dev/null)
sid=$(printf '%s' "$in" | jq -r '.session_id // empty' 2>/dev/null)
model=$(printf '%s' "$in" | jq -r '.model.display_name // "?"' 2>/dev/null)
dir=$(printf '%s' "$in" | jq -r '.workspace.current_dir // .cwd // "."' 2>/dev/null)
br=$(git -C "$dir" branch --show-current 2>/dev/null)
if [ -n "$pct" ] && [ -n "$sid" ] && [[ "$sid" =~ ^[A-Za-z0-9_-]+$ ]]; then
  d="${TMPDIR:-/tmp}/listicles-ctx"
  mkdir -p "$d" 2>/dev/null && printf '%s' "${pct%.*}" >"$d/$sid" 2>/dev/null
fi
p=${pct%.*}
printf '%s | %s | ctx %s%%' "$model" "${br:-no-branch}" "${p:-?}"
limit=${LISTICLES_CONTEXT_THRESHOLD:-50}
[[ "$limit" =~ ^[0-9]+$ ]] && [ "$limit" -gt 0 ] || limit=50  # garbage falls back to 50
[ -n "$p" ] && [ "$p" -ge "$limit" ] 2>/dev/null && printf ' | HANDOFF NOW'
echo
