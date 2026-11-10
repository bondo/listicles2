#!/usr/bin/env python3
"""Claude Code PreToolUse guard (PLAN section 5.3). Exit 2 = deny (stderr is shown to the agent).

Denies:
  * git commit/push --no-verify, hook-path overrides
  * git push --force / -f / +refspec, and any push to main/master
  * destructive worktree commands (reset --hard, checkout -f/--/., restore, clean -f, stash, ...)
    while the working tree has uncommitted changes; reset --hard is always denied on main/master
  * edits to process files (CLAUDE.md, REVIEW.md, agents/, .claude/, scripts/guards.sh, ...)
    unless the session was started with LISTICLES_TASK=tooling

Best effort by nature (shell is expressive). CODEOWNERS and branch protection are the real control.
Fails closed: an unparseable git command is denied.
"""

import json
import os
import re
import shlex
import subprocess
import sys

PROTECTED = (
    "CLAUDE.md",
    "REVIEW.md",
    "agents/",
    ".claude/",
    ".github/",
    ".githooks/",
    "scripts/guards.sh",
    "scripts/install-hooks.sh",
    "scripts/hooks/",
)
SHARED = {"main", "master"}
SEPARATORS = {";", "&&", "||", "|", "&", "\n", "(", ")", "{", "}"}
WRITE_HINT = re.compile(
    r"(^|[\s;&|(])(sed\s+(-[a-zA-Z]*i|--in-place)|perl\s+-[a-zA-Z]*i|tee|mv|cp|rm|truncate|dd|chmod|install|ln|patch)\b"
    r"|>>?\s*\S|git\s+(checkout|restore|apply|rm|mv|clean|stash)\b|\bopen\s*\(|write_text|write_bytes"
)


def deny(msg):
    print(f"BLOCKED by scripts/hooks/pretooluse_guard.py: {msg}", file=sys.stderr)
    sys.exit(2)


def git_out(cwd, *args):
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def dirty(cwd):
    out = git_out(cwd, "status", "--porcelain")
    return out is None or out != ""  # unknown state counts as dirty


def branch(cwd):
    return git_out(cwd, "branch", "--show-current") or ""


def is_protected(path, cwd):
    if not path:
        return False
    root = git_out(cwd, "rev-parse", "--show-toplevel") or cwd
    p = os.path.normpath(os.path.join(cwd, path))
    rel = os.path.relpath(os.path.realpath(p), os.path.realpath(root))
    if rel.startswith(".."):
        return False
    for pat in PROTECTED:
        if pat.endswith("/"):
            if rel == pat[:-1] or rel.startswith(pat):
                return True
        elif rel == pat:
            return True
    return False


def segments(command):
    """Split into simple commands, recursing into `bash -c '...'` style arguments."""
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=";&|(){}")
        lex.whitespace_split = True
        lex.commenters = ""
        toks = list(lex)
    except ValueError:
        return None
    segs, cur = [], []
    for t in toks:
        if t in SEPARATORS or set(t) <= set(";&|(){}"):
            if cur:
                segs.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        segs.append(cur)
    out = []
    for s in segs:
        out.append(s)
        for t in s:
            if re.search(r"\bgit\b", t) and re.search(r"\s", t):
                inner = segments(t)
                if inner is None:
                    return None
                out.extend(inner)
    return out


def strip_wrappers(seg):
    """Drop env assignments and wrappers (env, command, sudo, nohup, time, exec) before the program."""
    i = 0
    while i < len(seg):
        t = seg[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t) or t in {"env", "command", "sudo", "nohup", "time", "exec", "builtin", "nice"}:
            i += 1
        elif t.startswith("-") and i > 0 and seg[i - 1] in {"env", "sudo", "nice"}:
            i += 1
        else:
            break
    return seg[i:]


def check_git(seg, cwd):
    # Global options before the subcommand.
    i, gcwd, cfg = 1, cwd, []
    while i < len(seg) and seg[i].startswith("-"):
        o = seg[i]
        if o == "-C" and i + 1 < len(seg):
            gcwd = os.path.normpath(os.path.join(cwd, seg[i + 1]))
            i += 1
        elif o == "-c" and i + 1 < len(seg):
            cfg.append(seg[i + 1])
            i += 1
        elif o.startswith("--git-dir") or o.startswith("--work-tree"):
            if "=" not in o:
                i += 1
        i += 1
    for c in cfg:
        if re.match(r"(?i)core\.hookspath", c):
            deny("overriding core.hooksPath bypasses the git hooks")
    if i >= len(seg):
        return
    sub, args = seg[i], seg[i + 1 :]
    flags = [a for a in args if a.startswith("-")]
    cur = branch(gcwd)

    if sub in ("commit", "push", "merge", "am", "cherry-pick", "rebase"):
        if "--no-verify" in args or (sub in ("commit", "merge") and any(re.fullmatch(r"-[a-zA-Z]*n[a-zA-Z]*", f) for f in flags)):
            deny(f"git {sub} --no-verify skips the hooks; fix what the hook reports instead")
    if sub == "config" and any(re.match(r"(?i)core\.hookspath", a) for a in args):
        deny("changing core.hooksPath disables the hooks (use scripts/install-hooks.sh)")
    if sub == "push":
        if any(f in ("--force", "-f", "--mirror") or re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", f) for f in flags):
            deny("git push --force is not allowed (use --force-with-lease on your own branch if you must)")
        pos = [a for a in args if not a.startswith("-")]
        refspecs = pos[1:] if pos else []  # first positional is the remote
        if any(a.startswith("+") for a in refspecs):
            deny("forced refspec (+ref) is not allowed")
        for r in refspecs:
            dst = r.split(":")[-1].replace("refs/heads/", "")
            if dst in SHARED:
                deny("pushing to main/master is not allowed; open a PR from your branch")
        if "--delete" in args or "-d" in args:
            if any(a.replace("refs/heads/", "") in SHARED for a in pos):
                deny("deleting main/master is not allowed")
        if not refspecs and "--all" not in args and cur in SHARED:
            deny("pushing main/master is not allowed; work on a branch")
        if "--all" in args or "--mirror" in args:
            deny("push --all/--mirror can touch main; push your branch explicitly")

    destructive = False
    if sub == "reset" and "--hard" in args:
        if cur in SHARED:
            deny("git reset --hard on main/master is not allowed")
        destructive = True
    elif sub == "checkout" and (any(f in ("-f", "--force") for f in flags) or "--" in args or "." in args):
        destructive = True
    elif sub == "switch" and any(f in ("-f", "--force", "--discard-changes") for f in flags):
        destructive = True
    elif sub == "restore" and "--staged" not in args:
        destructive = True
    elif sub == "clean" and any(re.fullmatch(r"-[a-zA-Z]*[fx][a-zA-Z]*|--force", f) for f in flags):
        destructive = True
    elif sub == "stash" and not (args and args[0] in ("list", "show", "apply", "branch")):
        if args and args[0] in ("drop", "clear"):
            deny("git stash drop/clear destroys work")
        destructive = True
    elif sub == "update-ref" and "-d" in args:
        destructive = True
    if destructive and dirty(gcwd):
        deny(
            f"git {sub} with uncommitted changes can lose work (a previous session did). "
            "Commit first (a WIP commit is fine), then retry."
        )


def check_bash(command, cwd):
    segs = segments(command)
    if segs is None:
        if re.search(r"\bgit\b", command):
            deny("could not parse this git command; simplify it")
        segs = []
    for seg in segs:
        seg = strip_wrappers(seg)
        if seg and os.path.basename(seg[0]) == "git":
            check_git(seg, cwd)
    if os.environ.get("LISTICLES_TASK") != "tooling" and WRITE_HINT.search(command):
        for pat in PROTECTED:
            if re.search(r"(^|[\s'\"=/])" + re.escape(pat.rstrip("/")) + (r"(/|\b)" if pat.endswith("/") else r"\b"), command):
                deny(f"this command looks like it writes to the process file/dir {pat}; those need a tooling task")


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        deny("unreadable hook input")
    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}
    cwd = data.get("cwd") or os.getcwd()
    if tool == "Bash":
        check_bash(inp.get("command", ""), cwd)
    elif tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = inp.get("file_path") or inp.get("notebook_path") or ""
        if os.environ.get("LISTICLES_TASK") != "tooling" and is_protected(path, cwd):
            deny(f"{path} is a process file (CLAUDE.md, REVIEW.md, agents/, .claude/, .github/, hooks). "
                 "Only sessions started with LISTICLES_TASK=tooling may edit it; ask the owner.")
    sys.exit(0)


if __name__ == "__main__":
    main()
