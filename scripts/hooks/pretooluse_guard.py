#!/usr/bin/env python3
"""Claude Code PreToolUse guard (PLAN section 5.3). Exit 2 = deny (stderr is shown to the agent).

Denies:
  * git commit/push/merge/am --no-verify (also abbreviated), hook-path and alias overrides (-c, config, GIT_CONFIG_*)
  * git push --force / -f / +refspec, and any push to main/master (also HEAD:heads/main, upstream-tracked bare pushes)
  * destructive worktree commands (reset --hard, checkout -f/--/<tree> <path>, restore, clean -f, stash, ...)
    while the working tree has uncommitted changes; reset --hard is always denied on main/master
  * writes to process files (CLAUDE.md, REVIEW.md, agents/, .claude/, scripts/guards.sh, ...) unless the session
    was started with LISTICLES_TASK=tooling; writes to .git/config and .git/hooks/ are never allowed

How it works: the command is tokenised like a shell (quotes, heredocs, newlines, $(...), redirects, wrappers such as
timeout/sudo/env/xargs/bash -c) and each simple command is checked. Quoted text and heredoc bodies are data, not commands.
Paths are resolved against the project root (CLAUDE_PROJECT_DIR, this script's repo, the git root of the cwd and of the file),
never only the hook's cwd.

Best effort by nature (shell is expressive). CODEOWNERS and branch protection are the real control.
Fails closed: an unparseable command that mentions git or a protected path is denied.
"""

import json
import os
import fnmatch
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
ALWAYS = (".git/config", ".git/hooks/")  # no session may write these
SHARED = {"main", "master"}
SCRIPT_ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "ash"}
INTERPRETERS = re.compile(r"^(python[0-9.]*|node|nodejs|ruby|perl|php|deno|bun)$")
RESERVED = {"if", "then", "else", "elif", "fi", "do", "done", "while", "until", "for", "in", "case", "esac", "!", "{", "}", "function",
            "select"}
# name -> (options that take a value, number of leading positional arguments to skip)
WRAPPERS = {
    "env": ({"-u", "-C", "--unset", "--chdir", "-S", "--split-string"}, 0),
    "sudo": ({"-u", "-g", "-h", "-p", "-C", "-U", "-r", "-t", "-D", "-R", "--user", "--group", "--host"}, 0),
    "doas": ({"-u", "-C"}, 0),
    "nice": ({"-n", "--adjustment"}, 0),
    "ionice": ({"-c", "-n", "-p", "-t"}, 0),
    "timeout": ({"-s", "-k", "--signal", "--kill-after"}, 1),
    "nohup": (set(), 0),
    "command": (set(), 0),
    "exec": ({"-a"}, 0),
    "builtin": (set(), 0),
    "setsid": (set(), 0),
    "stdbuf": ({"-i", "-o", "-e"}, 0),
    "unbuffer": (set(), 0),
    "busybox": (set(), 0),
    "watch": ({"-n", "-d"}, 0),
    "flock": ({"-w", "-E", "--timeout", "--conflict-exit-code"}, 1),
    "xargs": ({"-I", "-n", "-P", "-d", "-E", "-L", "-s", "-a", "-R", "-S", "--arg-file"}, 0),
    "time": ({"-f", "-o", "--format", "--output"}, 0),
    "strace": ({"-o", "-e", "-p", "-s", "-u", "-E", "-a", "-b", "-I", "-P", "-X", "-O", "-S"}, 0),
    "ltrace": ({"-o", "-e", "-p", "-s", "-u", "-a", "-n", "-l"}, 0),
    "chrt": (set(), 1),
    "taskset": ({"-c", "--cpu-list"}, 1),  # the mask is a positional unless -c/--cpu-list is used
    "caffeinate": ({"-t", "-w"}, 0),
}
GIT_COMMON = {"status", "log", "diff", "add", "commit", "push", "fetch", "pull", "branch", "checkout", "switch", "restore", "reset", "show",
              "merge", "rebase", "stash", "clean", "rm", "mv", "config", "remote", "tag", "cherry-pick", "am", "apply", "blame", "grep",
              "ls-files", "rev-parse", "init", "clone", "describe", "worktree", "update-ref", "read-tree", "symbolic-ref", "ls-remote",
              "reflog", "shortlog", "bisect", "archive", "show-ref", "for-each-ref", "cat-file", "merge-base", "rev-list", "notes"}
RISKY_CONFIG = re.compile(r"(?i)^(core\.hookspath|alias\.|include(if\..*)?\.path|remote\..*\.push|push\.default)")
RISKY_CONFIG_ANY = re.compile(r"(?i)(core\.hookspath|alias\.|include(if\..*)?\.path|remote\..*\.push|push\.default)")  # anywhere in a value
CONFIG_FILE_VARS = {"GIT_CONFIG", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"}
HOME_GIT = re.compile(r"(^|/)\.gitconfig$|(^|/)\.config/git(/|$)")
ALL_ARGS_MUTATORS = {"rm", "rmdir", "unlink", "touch", "truncate", "chmod", "chown", "chgrp", "tee", "patch", "shred", "mv", "mkdir"}
DEST_LAST_MUTATORS = {"cp", "ln", "install", "rsync"}
CODE_WRITES = re.compile(
    r"open\s*\([^,)]+,\s*(?:mode\s*=\s*)?['\"][rwxabt+]*[wax+][rwxabt+]*['\"]|write_text|write_bytes|writeFile|File\.write"
    r"|(?<!stdout)(?<!stderr)\.write\s*\(|\bFileUtils\.")
PROCESS_CALLS = re.compile(r"subprocess|os\.system|os\.popen|popen|execSync|execFileSync|child_process|spawn|\bsystem\s*\(|\bexec\s*\(|%x")
SENSITIVE_SUBS = {"reset", "push", "checkout", "restore", "clean", "stash", "commit", "config", "switch", "rm"}
TOOLING = os.environ.get("LISTICLES_TASK") == "tooling"


def deny(msg):
    print(f"BLOCKED by scripts/hooks/pretooluse_guard.py: {msg}", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------- git helpers

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


# ---------------------------------------------------------------- protected paths

def project_roots(cwd, extra=()):
    roots = []
    for p in (os.environ.get("CLAUDE_PROJECT_DIR"), SCRIPT_ROOT, git_out(cwd, "rev-parse", "--show-toplevel"), *extra):
        if p:
            r = os.path.realpath(p)
            if r not in roots:
                roots.append(r)
    return roots


def _kind(rel):
    for pat in ALWAYS:
        if rel == pat.rstrip("/") or (pat.endswith("/") and rel.startswith(pat)):
            return "always"
    for pat in PROTECTED:
        if rel == pat.rstrip("/") or (pat.endswith("/") and rel.startswith(pat)):
            return "process"
    return None


def _suffix_kind(path):
    if HOME_GIT.search(path):
        return "always"
    for pats, kind in ((ALWAYS, "always"), (PROTECTED, "process")):
        for pat in pats:
            core = re.escape(pat.rstrip("/"))
            if re.search(r"(^|/)" + core + (r"(/|$)" if pat.endswith("/") else "$"), path):
                return kind
    return None


def protection(path, cwd):
    """'always' (git internals), 'process' (process files) or None."""
    if not path:
        return None
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        path = path.replace("${CLAUDE_PROJECT_DIR}", proj).replace("$CLAUDE_PROJECT_DIR", proj)
    path = path.replace("${PWD}", cwd).replace("$PWD", cwd)
    if path.startswith("~"):
        path = os.path.expanduser(path)
    if "$" in path or "`" in path:  # unknown expansion: judge by the tail of the path, conservatively
        return _suffix_kind(path)
    abs_ = os.path.normpath(os.path.join(cwd, path))
    if HOME_GIT.search(os.path.realpath(abs_)):
        return "always"
    d = abs_
    while d and not os.path.isdir(d) and d != os.path.dirname(d):
        d = os.path.dirname(d)
    real = os.path.realpath(abs_)
    for root in project_roots(cwd, [git_out(d, "rev-parse", "--show-toplevel")] if os.path.isdir(d) else []):
        rel = os.path.relpath(real, root)
        if rel == ".." or rel.startswith(".." + os.sep):
            continue
        k = _kind(rel.replace(os.sep, "/"))
        if k:
            return k
    return None


def guard_path(path, cwd, what="write to"):
    k = protection(path, cwd)
    if k == "always":
        deny(f"{what} {path}: git config and hooks must not be edited (hooks are installed by scripts/install-hooks.sh)")
    if k == "process" and not TOOLING:
        deny(f"{what} {path}: it is a process file (CLAUDE.md, REVIEW.md, agents/, .claude/, .github/, hooks). "
             "Only sessions started with LISTICLES_TASK=tooling may edit it; ask the owner.")


# ---------------------------------------------------------------- shell tokeniser

class Cmd:
    def __init__(self):
        self.words, self.writes, self.subs, self.heredocs = [], [], [], []  # heredocs also holds here-strings
        self.group = None  # "open"/"close" marker for ( ) groups: a subshell's cd must not leak
        self.piped = None  # the command whose output feeds this one through a pipe

    def empty(self):
        return not (self.words or self.writes or self.subs or self.heredocs or self.group)


HEREDOC_START = re.compile(r"<<-?[ \t]*(['\"]?)\\?([A-Za-z_][A-Za-z0-9_]*)\1")


def find_backtick(src, i):
    n = len(src)
    while i < n:
        if src[i] == "\\":
            i += 2
            continue
        if src[i] == "`":
            return i
        i += 1
    raise ValueError("unterminated backtick")


def find_close(src, i):
    """Index of the ')' that closes a '$(' whose body starts at i. Aware of quotes and heredocs."""
    depth, n, start = 1, len(src), i
    while i < n:
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            j = src.find("'", i + 1)
            if j < 0:
                raise ValueError("unterminated quote")
            i = j + 1
            continue
        if c == '"':
            i += 1
            while i < n and src[i] != '"':
                i += 2 if src[i] == "\\" else 1
            if i >= n:
                raise ValueError("unterminated quote")
            i += 1
            continue
        if c == "<" and src.startswith("<<", i) and not src.startswith("<<<", i):
            m = HEREDOC_START.match(src, i)
            if m:
                nl = src.find("\n", m.end())
                pos = n if nl < 0 else nl + 1
                while pos < n:
                    e = src.find("\n", pos)
                    line = src[pos:] if e < 0 else src[pos:e]
                    pos = n if e < 0 else e + 1
                    if line.rstrip("\r").lstrip("\t" if "-" in m.group(0)[:3] else "") == m.group(2):
                        break
                i = pos
                continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                if re.search(r"\bcase\b[^;]*\bin\b", src[start:i]):  # a case pattern's ')' would end the $( early
                    raise ValueError("case statement inside $(")
                return i
        i += 1
    raise ValueError("unterminated $(")


def extract_subs(text):
    subs, i = [], 0
    while i < len(text):
        if text[i] == "\\":
            i += 2
        elif text.startswith("$(", i):
            j = find_close(text, i + 2)
            subs.append(text[i + 2:j])
            i = j + 1
        elif text[i] == "`":
            j = find_backtick(text, i + 1)
            subs.append(text[i + 1:j])
            i = j + 1
        else:
            i += 1
    return subs


def ansi_c(s):
    def rep(m):
        t = m.group(1)
        simple = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"', "e": "\x1b", "a": "\a", "b": "\b"}
        if t in simple:
            return simple[t]
        if t[0] == "x":
            return chr(int(t[1:], 16))
        if t[0] in "uU":
            return chr(int(t[1:], 16))
        return chr(int(t, 8) & 0xFF)
    return re.sub(r"\\(x[0-9a-fA-F]{1,2}|u[0-9a-fA-F]{1,4}|U[0-9a-fA-F]{1,8}|[0-7]{1,3}|.)", rep, s)


def lex(src):
    """Split a shell command string into simple commands. Raises ValueError when it cannot be parsed."""
    cmds, cur = [], Cmd()
    word, in_word, quoted, pending = [], False, False, None
    heredocs = []
    i, n = 0, len(src)

    def end_cmd():
        nonlocal cur, pending
        pending = None
        if not cur.empty():
            cmds.append(cur)
        cur = Cmd()

    def flush():
        nonlocal word, in_word, quoted, pending
        if not in_word:
            return
        text, q = "".join(word), quoted
        word, in_word, quoted = [], False, False
        if pending:
            kind, pending = pending, None
            if kind == "write":
                if not re.fullmatch(r"\d+-?|-", text):
                    cur.writes.append(text)
            elif kind == "herestring":
                cur.heredocs.append(text)
            elif kind[0] == "heredoc":
                heredocs.append((text, q, kind[1], cur))
            return
        cur.words.append(text)

    while i < n:
        c = src[i]
        if c == "\\":
            if i + 1 < n:
                if src[i + 1] != "\n":
                    word.append(src[i + 1])
                    in_word = quoted = True
                i += 2
            else:
                i += 1
        elif c == "'":
            j = src.find("'", i + 1)
            if j < 0:
                raise ValueError("unterminated quote")
            word.append(src[i + 1:j])
            in_word = quoted = True
            i = j + 1
        elif c == '"':
            i += 1
            while True:
                if i >= n:
                    raise ValueError("unterminated quote")
                c = src[i]
                if c == '"':
                    i += 1
                    break
                if c == "\\":
                    if i + 1 < n and src[i + 1] in '$`"\\\n':
                        if src[i + 1] != "\n":
                            word.append(src[i + 1])
                        i += 2
                    else:
                        word.append(c)
                        i += 1
                elif src.startswith("$(", i):
                    j = find_close(src, i + 2)
                    cur.subs.append(src[i + 2:j])
                    word.append(src[i:j + 1])
                    i = j + 1
                elif c == "`":
                    j = find_backtick(src, i + 1)
                    cur.subs.append(src[i + 1:j])
                    word.append(src[i:j + 1])
                    i = j + 1
                else:
                    word.append(c)
                    i += 1
            in_word = quoted = True
        elif src.startswith("$'", i):
            j = i + 2
            while j < n and src[j] != "'":
                j += 2 if src[j] == "\\" else 1
            if j >= n:
                raise ValueError("unterminated quote")
            word.append(ansi_c(src[i + 2:j]))
            in_word = quoted = True
            i = j + 1
        elif src.startswith("$(", i):
            j = find_close(src, i + 2)
            cur.subs.append(src[i + 2:j])
            word.append(src[i:j + 1])
            in_word = True
            i = j + 1
        elif c == "`":
            j = find_backtick(src, i + 1)
            cur.subs.append(src[i + 1:j])
            word.append(src[i:j + 1])
            in_word = True
            i = j + 1
        elif src.startswith("${", i):
            j = src.find("}", i)
            if j < 0:
                raise ValueError("unterminated ${")
            word.append(src[i:j + 1])
            cur.subs.extend(extract_subs(src[i:j + 1]))
            in_word = True
            i = j + 1
        elif c in " \t\r":
            flush()
            i += 1
        elif c == "\n":
            flush()
            end_cmd()
            i += 1
            for delim, literal, strip, owner in heredocs:
                lines = []
                while i < n:
                    e = src.find("\n", i)
                    line = src[i:] if e < 0 else src[i:e]
                    i = n if e < 0 else e + 1
                    if (line.rstrip("\r").lstrip("\t") if strip else line.rstrip("\r")) == delim:
                        break
                    lines.append(line)
                body = "\n".join(lines)
                owner.heredocs.append(body)
                if not literal:
                    owner.subs.extend(extract_subs(body))
            heredocs = []
        elif c == "#" and not in_word:
            while i < n and src[i] != "\n":
                i += 1
        elif c in ";|" or (c == "&" and not src.startswith("&>", i)) or c in "()":
            flush()
            ended = cur if not cur.empty() else None
            end_cmd()
            is_pipe = c == "|" and not src.startswith("||", i)
            if c in "()":
                marker = Cmd()
                marker.group = "open" if c == "(" else "close"
                cmds.append(marker)
            i += 1
            while i < n and src[i] in ";&|":
                i += 1
            if is_pipe and ended is not None:
                cur.piped = ended
        elif c in "<>&":
            if c != "&" and src.startswith("(", i + 1):  # process substitution: the '(' separates commands
                flush()
                i += 1
                continue
            if in_word and not quoted and "".join(word).isdigit():
                word, in_word = [], False  # fd prefix such as the 2 in 2>&1
            else:
                flush()
            m = re.compile(r"&>>|&>|<<<|<<-|<<|<>|<&|<|>>|>&|>\||>").match(src, i)
            op = m.group(0)
            i += len(op)
            if op in ("<<", "<<-"):
                pending = ("heredoc", op == "<<-")
            elif op == "<<<":
                pending = "herestring"
            elif op in ("<", "<&"):
                pending = "read"
            else:
                pending = "write"
        else:
            word.append(c)
            in_word = True
            i += 1
    flush()
    end_cmd()
    return cmds


# ---------------------------------------------------------------- option helpers

def opt(arg, name, minlen=4):
    """True if arg is the long option `name` or an abbreviation of it (git accepts unambiguous prefixes)."""
    if not arg.startswith("--"):
        return False
    key = arg.split("=", 1)[0]
    return len(key) >= minlen and name.startswith(key)


def split_args(args):
    """(flags, positionals); everything after -- is positional."""
    flags, pos = [], []
    for k, a in enumerate(args):
        if a == "--":
            pos.extend(args[k + 1:])
            break
        (flags if a.startswith("-") and len(a) > 1 else pos).append(a)
    return flags, pos


def has_short(args, letter, takes_value):
    """True if a short-option cluster contains `letter` before any option that takes a value."""
    k = 0
    while k < len(args):
        a = args[k]
        if a == "--":
            return False
        if a.startswith("-") and not a.startswith("--") and len(a) > 1:
            for idx, ch in enumerate(a[1:]):
                if ch == letter:
                    return True
                if ch in takes_value:
                    if idx == len(a) - 2:
                        k += 1
                    break
        k += 1
    return False


def push_positionals(args):
    """Positionals of git push, skipping the values of options that take one (-o ci.skip must not become the remote)."""
    out, k = [], 0
    while k < len(args):
        a = args[k]
        if a == "--":
            out.extend(args[k + 1:])
            break
        if a in ("-o", "--push-option", "--repo", "--receive-pack", "--exec"):
            k += 1
        elif not a.startswith("-"):
            out.append(a)
        k += 1
    return out


def norm_ref(ref):
    return re.sub(r"^(refs/)?(heads/)?", "", ref)


# ---------------------------------------------------------------- git checks

def check_git(words, state, assigns_dirty=False):
    cwd = state["cwd"]
    i, gcwd, cfg, custom = 1, cwd, [], assigns_dirty
    while i < len(words) and words[i].startswith("-"):
        o = words[i]
        if o == "-C" and i + 1 < len(words):
            gcwd = os.path.normpath(os.path.join(gcwd, words[i + 1]))
            i += 1
        elif o == "-c" and i + 1 < len(words):
            cfg.append(words[i + 1])
            i += 1
        elif o.startswith("-c") and len(o) > 2 and not o.startswith("--"):
            cfg.append(o[2:])
        elif o.startswith("--config-env"):
            if "=" in o:
                cfg.append(o.split("=", 1)[1])
            elif i + 1 < len(words):
                cfg.append(words[i + 1])
                i += 1
        elif o in ("--git-dir", "--work-tree", "--namespace", "--super-prefix", "--attr-source"):
            custom = custom or o != "--namespace"
            i += 1
        elif o.startswith(("--git-dir=", "--work-tree=")):
            custom = True
        i += 1
    for c in cfg:
        if RISKY_CONFIG.match(c):
            deny("this -c override can bypass the git hooks, hide a blocked command in an alias, or change what push targets")
    if i >= len(words):
        return
    sub, args = words[i], words[i + 1:]
    if "$" in sub or "`" in sub:
        deny("the git subcommand is built from a variable or substitution; write it out")
    flags, pos = split_args(args)
    cur = branch(gcwd)
    if state.get("xargs") and sub in SENSITIVE_SUBS:
        deny(f"git {sub} gets its arguments from xargs, which cannot be checked; write the arguments out")
    if sub not in GIT_COMMON:
        alias = git_out(gcwd, "config", "--get", f"alias.{sub}")
        if alias:
            if state.get("alias_depth", 0) >= 3:
                deny("git alias nesting is too deep to check")
            st = dict(state, alias_depth=state.get("alias_depth", 0) + 1, vars=dict(state["vars"]))
            if alias.startswith("!"):
                check_command_string(alias[1:] + " " + " ".join(shlex.quote(a) for a in args), st, state.get("depth", 0) + 1)
            else:
                try:
                    check_git(["git", *shlex.split(alias), *args], st)
                except ValueError:
                    deny("could not parse this git alias; write the command out")
            return

    if sub in ("commit", "push", "merge", "am", "cherry-pick", "rebase"):
        if any(opt(f, "--no-verify", 6) for f in flags) or (
                sub in ("commit", "am") and has_short(args, "n", "mFCctS")):
            deny(f"git {sub} --no-verify skips the hooks; fix what the hook reports instead")
    if sub == "config":
        read_only = any(opt(f, n, 4) for f in flags for n in ("--get", "--get-all", "--get-regexp", "--list", "--get-urlmatch")) or "-l" in flags
        read_only = read_only or (len(pos) <= 1 and not any(f in ("--add", "--replace-all") or opt(f, "--replace-all", 4) for f in flags))
        if any(re.match(r"(?i)core\.hookspath", a) for a in args):
            deny("changing or querying core.hooksPath is not allowed (hooks are installed by scripts/install-hooks.sh)")
        if not read_only and any(RISKY_CONFIG.match(a) for a in pos):
            deny("changing core.hooksPath, aliases, include.path or push targets in git config can disable the hooks or hide a blocked "
                 "command (hooks are installed by scripts/install-hooks.sh)")
    if sub == "push":
        if any(opt(f, "--force", 4) or opt(f, "--mirror", 4) or re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", f) for f in flags):
            deny("git push --force is not allowed (use --force-with-lease on your own branch if you must)")
        if any(opt(f, "--all", 4) for f in flags):
            deny("push --all/--mirror can touch main; push your branch explicitly")
        ppos = push_positionals(args)
        refspecs = ppos[1:]  # first positional is the remote
        if any(a.startswith("+") for a in refspecs):
            deny("forced refspec (+ref) is not allowed")
        for r in refspecs:
            if r == ":":
                deny("the matching refspec ':' pushes every branch that exists on both sides, main included")
            if "$" in r or "`" in r:
                deny("the push refspec is built from a variable or substitution; write the branch out")
            dst = norm_ref(r.split(":")[-1])
            if dst in ("HEAD", "@"):
                dst = cur
            if dst in SHARED or dst == "*" or (re.search(r"[*?\[]", dst) and any(fnmatch.fnmatch(sh, dst) for sh in SHARED)):
                deny("pushing to main/master is not allowed; open a PR from your branch")
        if not refspecs:
            up = norm_ref(git_out(gcwd, "config", "--get", f"branch.{cur}.merge") or "") if cur else ""
            if cur in SHARED or up in SHARED:
                deny("pushing main/master is not allowed; work on a branch")

    destructive = False
    if sub == "reset" and any(opt(f, "--hard", 4) for f in flags):
        if cur in SHARED:
            deny("git reset --hard on main/master is not allowed")
        destructive = True
    elif sub == "checkout":
        creating = any(f in ("-b", "-B") or opt(f, "--orphan", 4) for f in flags)
        if not creating:
            _, cpos = split_args(args)
            if (any(f == "-f" or opt(f, "--force", 4) or f == "-p" or opt(f, "--patch", 4) or opt(f, "--ours", 4) or opt(f, "--theirs", 4)
                    or opt(f, "--pathspec-from-file", 4) for f in flags) or "--" in args or len(cpos) >= 2):
                destructive = True
            elif len(cpos) == 1:
                t = cpos[0]
                is_ref = git_out(gcwd, "rev-parse", "--verify", "-q", t + "^{commit}") is not None
                if t == "." or re.search(r"[*?\[]", t) or (not is_ref and os.path.exists(os.path.join(gcwd, t))):
                    destructive = True
    elif sub == "switch" and any(f == "-f" or opt(f, "--force", 4) or opt(f, "--discard-changes", 4) for f in flags):
        destructive = True
    elif sub == "restore":
        staged = any(f in ("-S",) or opt(f, "--staged", 4) for f in flags)
        worktree = any(f == "-W" or opt(f, "--worktree", 4) for f in flags)
        if not staged or worktree:
            destructive = True
    elif sub == "clean" and any(re.fullmatch(r"-[a-zA-Z]*[fx][a-zA-Z]*", f) or opt(f, "--force", 4) for f in flags):
        destructive = True
    elif sub == "rm" and any(f == "-f" or opt(f, "--force", 4) for f in flags):
        destructive = True
    elif sub == "stash" and not (args and args[0] in ("list", "show", "apply", "branch")):
        if args and args[0] in ("drop", "clear"):
            deny("git stash drop/clear destroys work")
        destructive = True
    elif (sub == "update-ref" and "-d" in args) or (sub == "read-tree" and any(opt(f, "--reset", 4) for f in flags)):
        destructive = True
    if (not destructive and sub in ("reset", "checkout", "restore", "clean", "stash", "switch", "rm")
            and any(a.startswith(("$", "`")) for a in args)):
        destructive = True  # an option may hide in the expansion (git reset $(echo --hard)); only matters when there is work to lose
    if destructive and (custom or dirty(gcwd)):
        deny(f"git {sub} with uncommitted changes can lose work (a previous session did). "
             "Commit first (a WIP commit is fine), then retry.")

    if sub in ("checkout", "restore", "rm", "mv", "switch", "clean"):
        for a in args:
            if not a.startswith("-"):
                guard_path(a if os.path.isabs(a) else os.path.join(os.path.relpath(gcwd, cwd) if gcwd != cwd else ".", a), cwd,
                           f"git {sub} would overwrite")


# ---------------------------------------------------------------- command checks

def unwrap(words):
    """Strip env assignments, reserved words and wrapper commands.
    Returns (assignments, rest, nested command strings, wrapper names)."""
    assigns, nested, i, seen = [], [], 0, set()
    while i < len(words):
        w = words[i]
        if ASSIGN.match(w):
            assigns.append(w)
            i += 1
            continue
        if w in RESERVED:
            i += 1
            continue
        base = os.path.basename(w)
        if base == "script":  # script -qc 'cmd' /dev/null runs cmd
            for k in range(i + 1, len(words)):
                a = words[k]
                if a.startswith("--command="):
                    nested.append(a.split("=", 1)[1])
                elif (a == "--command" or (a.startswith("-") and not a.startswith("--") and "c" in a[1:])) and k + 1 < len(words):
                    nested.append(words[k + 1])
            return assigns, [], nested, seen
        if base in WRAPPERS:
            opts, npos = WRAPPERS[base]
            seen.add(base)
            i += 1
            while i < len(words) and words[i].startswith("-") and words[i] != "--":
                o = words[i]
                i += 1
                if o in opts and i < len(words):
                    if base == "env" and o in ("-S", "--split-string"):
                        nested.append(words[i])
                    if base == "taskset":
                        npos = 0
                    i += 1
            if i < len(words) and words[i] == "--":
                i += 1
            if base != "env":
                i += npos
            continue
        break
    return assigns, words[i:], nested, seen


def check_assign(a):
    name, val = a.split("=", 1)
    if name in CONFIG_FILE_VARS:
        deny(f"{name} swaps git's config file, which can disable the hooks or hide aliases")
    if name.startswith("GIT_CONFIG") and RISKY_CONFIG_ANY.search(val):
        deny("GIT_CONFIG_* must not override core.hooksPath, include.path, push targets or define aliases")


def write_targets(prog, args):
    flags, pos = split_args(args)
    if prog in ALL_ARGS_MUTATORS:
        return pos
    if prog in DEST_LAST_MUTATORS:
        for k, a in enumerate(args):
            if a in ("-t", "--target-directory") and k + 1 < len(args):
                return [args[k + 1]]
            if a.startswith("--target-directory="):
                return [a.split("=", 1)[1]]
        return pos[-1:] if len(pos) >= 2 else []
    if prog == "dd":
        return [a[3:] for a in args if a.startswith("of=")]
    inplace = {
        "sed": lambda a: re.fullmatch(r"-[A-Za-z]*i[A-Za-z0-9.~_-]*", a) or opt(a, "--in-place", 4),
        "gsed": lambda a: re.fullmatch(r"-[A-Za-z]*i[A-Za-z0-9.~_-]*", a) or opt(a, "--in-place", 4),
        "perl": lambda a: re.fullmatch(r"-[A-Za-z]*i[A-Za-z0-9.~_-]*", a),
        "ruby": lambda a: re.fullmatch(r"-[A-Za-z]*i[A-Za-z0-9.~_-]*", a),
        "awk": lambda a: a == "inplace",
        "gawk": lambda a: a == "inplace",
    }
    if prog in inplace and any(inplace[prog](a) for a in args if a not in ("--",)):
        return pos
    return []


def child(state, **extra):
    return dict(state, vars=dict(state["vars"]), **extra)


def expand(w, state):
    """Substitute variables assigned earlier in the same command line (H=--hard; git reset $H) and a few known values."""
    def rep(m):
        name = m.group(1) or m.group(2)
        if name in state["vars"]:
            return state["vars"][name]
        if name == "PWD":
            return state["cwd"]
        if name == "CLAUDE_PROJECT_DIR" and os.environ.get("CLAUDE_PROJECT_DIR"):
            return os.environ["CLAUDE_PROJECT_DIR"]
        return m.group(0)
    for q in ("$(git branch --show-current)", "$(git rev-parse --abbrev-ref HEAD)"):
        if q in w:
            w = w.replace(q, branch(state["cwd"]) or q)
    return re.sub(r"\$\{(\w+)\}|\$(\w+)", rep, w)


def check_command_string(command, state, depth=0):
    if depth > 8:
        deny("command nesting is too deep to check")
    try:
        cmds = lex(command)
    except ValueError:
        if re.search(r"\bgit\b|CLAUDE\.md|REVIEW\.md|\.claude|\.github|\.githooks|agents/|scripts/|\.git/", command):
            deny("could not parse this command (unbalanced quote or substitution); simplify it")
        return
    stack = []
    for cmd in cmds:
        if cmd.group == "open":
            stack.append((state["cwd"], state["known"]))
            continue
        if cmd.group == "close":
            if stack:
                state["cwd"], state["known"] = stack.pop()
            continue
        for s in cmd.subs:
            check_command_string(s, child(state), depth + 1)
        check_simple(cmd, state, depth)


def stdin_texts(cmd):
    """Text this command reads on stdin: here-strings, heredocs and what echo/printf/cat pipe into it."""
    out = list(cmd.heredocs)
    p, hops = cmd.piped, 0
    while p is not None and hops < 4 and p.words:
        base = os.path.basename(p.words[0])
        if base in ("echo", "printf"):
            out.append(" ".join(p.words[1:]).replace("\\n", "\n"))
            break
        if base != "cat":
            break
        out.extend(p.heredocs)
        p, hops = p.piped, hops + 1
    return out


def check_literals(code, state, depth):
    """String literals in interpreter code that run a git command (subprocess.run(['git', 'push', '--force']))."""
    lits = [a or b for a, b in re.findall(r"'([^']*)'|\"([^\"]*)\"", code)]
    cands = [lit for lit in lits if re.search(r"\bgit\b", lit)]
    cands += [" ".join(lits[k:]) for k, lit in enumerate(lits) if lit == "git"]
    for c in cands:
        try:
            lex(c)
        except ValueError:
            continue
        check_command_string(c, child(state), depth + 1)


def check_simple(cmd, state, depth):
    for t in cmd.writes:
        guard_target(expand(t, state), state, "redirect to")
    assigns, words, nested, wrappers = unwrap(cmd.words)
    for a in assigns:
        check_assign(a)
    for s in nested:
        check_command_string(s, child(state), depth + 1)
    if not words:
        for a in assigns:  # a plain assignment statement: remember literal values
            name, val = a.split("=", 1)
            if "$" in val or "`" in val:
                state["vars"].pop(name, None)
            else:
                state["vars"][name] = val
        return
    words = [words[0]] + [expand(w, state) for w in words[1:]]
    prog, args = os.path.basename(words[0]), words[1:]
    if "$" in words[0] or "`" in words[0]:
        if any(a in SENSITIVE_SUBS for a in args[:3]):
            deny("the command name is built from a variable or substitution; write it out")
        return
    if prog in ("cd", "pushd"):
        tgt = [a for a in args if not a.startswith("-")]
        t = tgt[-1] if tgt else "~"
        if t == "$(git rev-parse --show-toplevel)":
            state["cwd"] = git_out(state["cwd"], "rev-parse", "--show-toplevel") or state["cwd"]
        elif "$" in t or "`" in t:
            state["known"] = False
        else:
            state["cwd"] = os.path.normpath(os.path.join(state["cwd"], os.path.expanduser(t)))
        return
    if prog == "git":
        check_git([words[0]] + args, child(state, xargs="xargs" in wrappers, depth=depth))
        return
    if prog in ("export", "declare", "typeset", "readonly", "local"):
        for a in args:
            if ASSIGN.match(a):
                check_assign(a)
        return
    texts = stdin_texts(cmd)
    if prog in SHELLS:
        ran_c = False
        for k, a in enumerate(args):
            if a.startswith("-") and not a.startswith("--") and "c" in a[1:] and k + 1 < len(args):
                check_command_string(args[k + 1], child(state), depth + 1)
                ran_c = True
                break
        for body in (cmd.heredocs if ran_c else texts):
            check_command_string(body, child(state), depth + 1)
        return
    if prog == "eval":
        check_command_string(" ".join(args), child(state), depth + 1)
        return
    if prog == "find":
        j = 0
        while j < len(args):
            if args[j] in ("-exec", "-execdir", "-ok", "-okdir"):
                k, inner = j + 1, []
                while k < len(args) and args[k] not in (";", "+"):
                    inner.append(args[k])
                    k += 1
                sub = Cmd()
                sub.words = inner
                check_simple(sub, child(state), depth + 1)
                j = k
            j += 1
        if "-delete" in args:
            for a in args:
                if a.startswith(("-", "(", "!")):
                    break
                guard_target(a, state, "find -delete under")
        return
    if INTERPRETERS.match(prog):
        code = " ".join(args + texts)
        if CODE_WRITES.search(code):
            for pat in PROTECTED + ALWAYS:
                if re.search(r"(^|[\s'\"=/])" + re.escape(pat.rstrip("/")) + (r"(/|\b)" if pat.endswith("/") else r"\b"), code):
                    if pat in ALWAYS or not TOOLING:
                        deny(f"inline code looks like it writes to the protected path {pat}")
        if PROCESS_CALLS.search(code):
            check_literals(code, state, depth)
    for t in write_targets(prog, args):
        guard_target(t, state)


def guard_target(path, state, what="write to"):
    """guard_path, but after a cd whose target could not be resolved a relative path cannot be judged: deny it."""
    if not state["known"] and path and not os.path.isabs(path) and not path.startswith(("~", "$")):
        deny(f"{what} {path}: an earlier cd target is built from a variable or substitution; write the directory out")
    guard_path(path, state["cwd"], what)


def check_bash(command, cwd):
    check_command_string(command, {"cwd": cwd, "known": True, "vars": {}})


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
        guard_path(inp.get("file_path") or inp.get("notebook_path") or "", cwd, "edit of")
    sys.exit(0)


def run_guarded():
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # fail closed: a crashing guard must not look like an allow (exit 1 would not block)
        deny(f"internal error ({type(e).__name__}: {e}); report this to the owner")


if __name__ == "__main__":
    run_guarded()
