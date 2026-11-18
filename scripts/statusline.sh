#!/usr/bin/env bash
# Claude Code status line: model, branch, context %. Also records the context % for the context-guard hook
# (scripts/hooks/context_guard.py) when it runs (interactive CLI only; headless sessions use the transcript instead).
# Records the % and, when the JSON has it, the window size in $TMPDIR/listicles-ctx/<session_id>[.window].
# Input: status JSON on stdin (context_window.used_percentage, context_window.context_window_size, session_id,
# model.display_name, workspace.current_dir).
# Handoff stages (same numbers as the hook and agents/roles.yaml): "HANDOFF SOON" from 60% of a 1M window (40% of a window of
# up to 200k tokens), "HANDOFF NOW" from 80% (60%). LISTICLES_CONTEXT_THRESHOLD replaces the hard stage and drops the soft one.
in=$(cat)
pct=$(printf '%s' "$in" | jq -r '.context_window.used_percentage // empty' 2>/dev/null)
sid=$(printf '%s' "$in" | jq -r '.session_id // empty' 2>/dev/null)
model=$(printf '%s' "$in" | jq -r '.model.display_name // "?"' 2>/dev/null)
dir=$(printf '%s' "$in" | jq -r '.workspace.current_dir // .cwd // "."' 2>/dev/null)
br=$(git -C "$dir" branch --show-current 2>/dev/null)
win=$(printf '%s' "$in" | jq -r '.context_window.context_window_size // empty' 2>/dev/null)
if [ -n "$pct" ] && [ -n "$sid" ] && [[ "$sid" =~ ^[A-Za-z0-9_-]+$ ]]; then
  d="${TMPDIR:-/tmp}/listicles-ctx"
  if mkdir -p "$d" 2>/dev/null; then
    printf '%s' "${pct%.*}" >"$d/$sid" 2>/dev/null
    # The real window size goes next to the %, so the hook uses the window this status line judges by (R1-01).
    # No valid window in this JSON: drop a window recorded earlier, so the hook never judges by a stale one (R2-01).
    if [[ "$win" =~ ^[0-9]+$ ]] && [ "$win" -gt 0 ]; then printf '%s' "$win" >"$d/$sid.window" 2>/dev/null; else rm -f "$d/$sid.window"; fi
  fi
fi
p=${pct%.*}
printf '%s | %s | ctx %s%%' "$model" "${br:-no-branch}" "${p:-?}"
[[ "$win" =~ ^[0-9]+$ ]] && [ "$win" -gt 0 ] || win=${LISTICLES_CONTEXT_WINDOW:-}
[[ "$win" =~ ^[0-9]+$ ]] && [ "$win" -gt 0 ] || win=1000000  # unknown or garbage: the 1M window the models here use
if [ "$win" -le 200000 ]; then soft=40; hard=60; else soft=60; hard=80; fi
limit=${LISTICLES_CONTEXT_THRESHOLD:-}
if [[ "$limit" =~ ^[0-9]+$ ]] && [ "$limit" -gt 0 ]; then soft=""; hard=$limit; fi  # garbage keeps the window defaults
if [ -n "$p" ] && [ "$p" -ge "$hard" ] 2>/dev/null; then
  printf ' | HANDOFF NOW'
elif [ -n "$p" ] && [ -n "$soft" ] && [ "$p" -ge "$soft" ] 2>/dev/null; then
  printf ' | HANDOFF SOON'
fi
echo
