#!/usr/bin/env python3
"""SessionEnd hook: sum token usage from the session transcript into metrics/sessions/<id>.json (PLAN 9.4).

Hook input (stdin JSON): session_id, transcript_path, cwd, reason. Never fails the session: errors go to stderr, exit 0.
Env tags set at spawn: LISTICLES_ROLE, LISTICLES_PR, LISTICLES_TASK. Output dir: LISTICLES_METRICS_DIR, else <project root>/metrics/sessions
(project root = CLAUDE_PROJECT_DIR, else the git root of cwd, else cwd).
Transcript facts (verified): assistant records carry message.id, message.model and message.usage; the same message id
repeats once per content block, so only the LAST record per id counts. Subagent transcripts live in
<transcript without .jsonl>/subagents/*.jsonl and are summed separately under "subagents".
"""

import glob
import json
import os
import subprocess
import sys

FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def usage_of(path):
    last = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                m = o.get("message")
                if o.get("type") == "assistant" and isinstance(m, dict) and isinstance(m.get("usage"), dict):
                    last[m.get("id") or o.get("uuid")] = (m.get("model", "unknown"), m["usage"])
    except OSError:
        return {"messages": 0, "total": dict.fromkeys(FIELDS, 0), "by_model": {}}
    by_model, total = {}, dict.fromkeys(FIELDS, 0)
    for model, u in last.values():
        row = by_model.setdefault(model, dict.fromkeys(FIELDS, 0))
        for k in FIELDS:
            v = u.get(k)
            v = v if isinstance(v, int) else 0
            row[k] += v
            total[k] += v
    return {"messages": len(last), "total": total, "by_model": by_model}


def project_root(cwd):
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and os.path.isdir(env):
        return env
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return cwd


def main():
    try:
        data = json.load(sys.stdin)
        sid = str(data["session_id"])
        tp = data["transcript_path"]
    except (ValueError, KeyError, TypeError):
        print("session_end_metrics: bad hook input", file=sys.stderr)
        return
    cwd = data.get("cwd") or os.getcwd()
    out_dir = os.environ.get("LISTICLES_METRICS_DIR") or os.path.join(project_root(cwd), "metrics", "sessions")
    main_u = usage_of(tp)
    subs = [usage_of(p) for p in sorted(glob.glob(os.path.join(tp[:-6], "subagents", "*.jsonl")))] if tp.endswith(".jsonl") else []
    sub_total = dict.fromkeys(FIELDS, 0)
    for s in subs:
        for k in FIELDS:
            sub_total[k] += s["total"][k]
    try:
        b = subprocess.run(["git", "branch", "--show-current"], cwd=cwd, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        b = ""
    rec = {
        "session_id": sid,
        "end_reason": data.get("reason"),
        "branch": b,
        "role": os.environ.get("LISTICLES_ROLE"),
        "pr": os.environ.get("LISTICLES_PR"),
        "task": os.environ.get("LISTICLES_TASK"),
        "main": main_u,
        "subagents": {"transcripts": len(subs), "total": sub_total},
    }
    try:
        os.makedirs(out_dir, exist_ok=True)
        safe = "".join(c for c in sid if c.isalnum() or c in "-_")
        with open(os.path.join(out_dir, f"{safe}.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2)
            f.write("\n")
    except OSError as e:
        print(f"session_end_metrics: {e}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break session shutdown
        print(f"session_end_metrics: {e}", file=sys.stderr)
    sys.exit(0)
