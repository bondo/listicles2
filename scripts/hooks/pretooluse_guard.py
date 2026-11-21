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

import hashlib
import json
import os
import fnmatch
import re
import shlex
import stat
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
    "scripts/merge_ready.py",  # the merge agent runs it
    "scripts/test_merge_ready.py",
    "scripts/mark-ready.sh",  # the project allow rules approve these paths; see PINNED_WRAPPERS below
    "scripts/update-branch.sh",
    "scripts/hooks/",
    ".tools/",  # linter binaries that the allow rules in .claude/settings.json run
    "scripts/install_linters.sh",
    "scripts/linters.pins",
)
# The allow rules `Bash(scripts/mark-ready.sh *)` and `Bash(scripts/update-branch.sh *)` approve any command that starts with that text. So: a
# file with such a name is a process file in every directory, and a command that runs one is allowed only as exactly `scripts/<name> <arguments>`
# from the project root (the arguments are fixed per wrapper, see PINNED_WRAPPERS).
# Writes to the file cannot all be caught by name (sed -i scripts/*.sh, cp -t scripts, tar, git apply), so its content is checked when it runs:
# the wrapper must be a regular file, not a symlink, with exactly its SHA-256. A legitimate edit of a wrapper updates its pin in the same
# reviewed tooling PR (test_guard_mark_ready.py and test_guard_update_branch.py fail until it does).
MARK_READY_SHA256 = "9bc1e6b9ce8936afb95ef3ab4516383bf101bb18aeaa9615582288c25a46a3ac"
UPDATE_BRANCH_SHA256 = "49e41a93b49dee859123e8636c61e7c0d845321f6b05c4cf3086a25426b6e24a"
MARK_READY = "mark-ready.sh"
PR_NUMBER = re.compile(r"[1-9][0-9]{0,5}")
HEX40 = re.compile(r"[0-9a-f]{40}")
# wrapper file name -> (the pinned SHA-256, the argument patterns); the exact call is `scripts/<name> <arg> <arg>...`
PINNED_WRAPPERS = {MARK_READY: (MARK_READY_SHA256, (PR_NUMBER,)), "update-branch.sh": (UPDATE_BRANCH_SHA256, (PR_NUMBER, HEX40))}
# R5-02: a word that names a wrapper, also after unquoting (`scripts/mark-ready.sh\\ 1` is one word): a path component that is exactly
# a wrapper name, then whitespace, a slash or the end. Names such as mark-ready.sh.md or xmark-ready.sh do not match.
WRAPPER_WORD = re.compile(r"(^|/)(" + "|".join(map(re.escape, PINNED_WRAPPERS)) + r")(\s|/|$)")
# R2-01 of #237: a program is routed to the exact-call check by the START of its name (no boundary), because quotes and a line continuation make bash
# run `scripts/mark-ready.sh12` for `scripts/mark-ready.sh""<backslash-newline>12`, a file the boundary form above does not recognise.
WRAPPER_PREFIX = re.compile(r"(^|/)(" + "|".join(map(re.escape, PINNED_WRAPPERS)) + r")")
ALWAYS = (".git/config", ".git/hooks/")  # no session may write these
SHARED = {"main", "master"}
SCRIPT_ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")  # NAME=value and NAME+=value (bash appends)
ASSIGN_PARTS = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(\+?)=(.*)$", re.S)
INDEXED = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\[")  # bash never applies NAME[k]=v in front of a command, but still runs the command
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "ash"}
INTERPRETERS = re.compile(r"^(python[0-9.]*|node|nodejs|ruby|perl|php|deno|bun)$")
RESERVED = {"if", "then", "else", "elif", "fi", "do", "done", "while", "until", "for", "in", "case", "esac", "!", "{", "}", "function",
            "select", "coproc"}
# name -> (options that take a value, number of leading positional arguments to skip)
WRAPPERS = {
    "env": ({"-u", "-C", "--unset", "--chdir", "-S", "--split-string"}, 0),
    "sudo": ({"-u", "-g", "-h", "-p", "-C", "-U", "-r", "-t", "-D", "-R", "--user", "--group", "--host"}, 0),
    "doas": ({"-u", "-C"}, 0),
    "nice": ({"-n", "--adjustment"}, 0),
    "ionice": ({"-c", "-n", "-p"}, 0),  # -t (ignore) takes no value
    "timeout": ({"-s", "-k", "--signal", "--kill-after"}, 1),
    "nohup": (set(), 0),
    "coproc": (set(), 0),
    "command": (set(), 0),
    "exec": ({"-a"}, 0),
    "builtin": (set(), 0),
    "setsid": (set(), 0),
    "stdbuf": ({"-i", "-o", "-e", "--input", "--output", "--error"}, 0),
    "noglob": (set(), 0),  # zsh's precommand modifier, which Claude Code strips before matching Bash rules (R3-01 of #237)
    "unbuffer": (set(), 0),
    "busybox": (set(), 0),
    "watch": ({"-n", "-d"}, 0),
    "flock": ({"-w", "-E", "--timeout", "--conflict-exit-code"}, 1),
    "xargs": ({"-I", "-n", "-P", "-d", "-E", "-L", "-s", "-a", "-R", "-S", "--arg-file", "--max-args", "--max-procs", "--max-chars", "--delimiter",
              "--process-slot-var"}, 0),
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
RISKY_CONFIG = re.compile(r"(?i)^(core\.hookspath|alias\.|include(if\..*)?\.path|remote\..*\.(push|mirror)|push\.default)")
RISKY_CONFIG_ANY = re.compile(r"(?i)(core\.hookspath|alias\.|include(if\..*)?\.path|remote\..*\.(push|mirror)|push\.default)")  # anywhere in a value
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
    if WRAPPER_WORD.search(path):
        return "process"
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        path = path.replace("${CLAUDE_PROJECT_DIR}", proj).replace("$CLAUDE_PROJECT_DIR", proj)
    path = path.replace("${PWD}", cwd).replace("$PWD", cwd)
    if path.startswith("~"):
        path = os.path.expanduser(path)
    if "$" in path or "`" in path:  # unknown expansion: judge by the tail of the path, conservatively
        bare = re.sub(r"\$\{[^}]*\}|\$\([^)]*\)|\$[A-Za-z_][A-Za-z0-9_]*|`[^`]*`", "", path)  # R1-04: an unset variable is empty
        kinds = {_suffix_kind(path), _suffix_kind(bare)}
        return "always" if "always" in kinds else "process" if "process" in kinds else None
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
        self.gettext = False  # a word starts with $"...", which bash translates when it parses the line
        self.prog_first = False  # the first word is a program, never an assignment (find -exec, a command name from a variable)

    def empty(self):
        return not (self.words or self.writes or self.subs or self.heredocs or self.group)


BRANCH_SUBS = ("$(git branch --show-current)", "$(git rev-parse --abbrev-ref HEAD)")
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
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
    depth, n = 1, len(src)
    at_cmd, in_case, after_time = True, False, False  # `case` only starts a statement in command position; quotes and heredoc bodies are skipped below
    while i < n:
        c = src[i]
        if c in " \t":
            i += 1
            continue
        was_cmd = at_cmd
        at_cmd = c in ";&|(\n{!"  # '!' negates a pipeline: the next word is still in command position
        if c == "-" and after_time:  # time -p
            while i < n and src[i] not in " \t\n":
                i += 1
            at_cmd = True
            continue
        after_time = False
        if c.isalpha() or c == "_":
            w = WORD.match(src, i).group(0)
            if was_cmd and w == "case":
                in_case = True
            elif in_case and w == "in":
                raise ValueError("case statement inside $(")  # its patterns' ')' would end the $( early
            at_cmd = w in ("then", "do", "else", "elif", "if", "while", "until") or (was_cmd and w == "time")
            after_time = was_cmd and w == "time"
            i += len(w)
            continue
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
        simple = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"', "e": "\x1b", "E": "\x1b", "a": "\a", "b": "\b", "f": "\f", "v": "\v",
                  "?": "?"}
        if t in simple:
            return simple[t]
        if t[0] == "c" and len(t) == 2:
            return chr(ord(t[1]) & 0x1F)
        if len(t) == 1 and t not in "01234567":
            return "\\" + t  # an unknown escape keeps its backslash, as in bash
        if t[0] == "x":
            return chr(int(t[1:], 16))
        if t[0] in "uU":
            try:
                return chr(int(t[1:], 16))
            except ValueError:
                return m.group(0)  # out of range: bash keeps the text, and the lexer must not fail where bash does not
        return chr(int(t, 8) & 0xFF)
    return re.sub(r"\\(x[0-9a-fA-F]{1,2}|u[0-9a-fA-F]{1,4}|U[0-9a-fA-F]{1,8}|[0-7]{1,3}|c.|.)", rep, s)


class Word(str):
    glob = False  # the word has an unquoted { } * ? [ ~ @ + ! that the shell expands after the guard has read it
    asg = None  # the text up to its first = is unquoted, so bash takes the word as an assignment (None: not from lex)
    ud = False  # the word has an unquoted $, so bash splits what it expands to on blanks


def lex(src):
    """Split a shell command string into simple commands. Raises ValueError when it cannot be parsed."""
    cmds, cur = [], Cmd()
    word, in_word, quoted, pending, ug = [], False, False, None, False
    qs, ud = None, False  # where the first quoted character sits in the word; an unquoted $ was seen
    heredocs = []
    i, n = 0, len(src)

    def end_cmd():
        nonlocal cur, pending
        pending = None
        if not cur.empty():
            cmds.append(cur)
        cur = Cmd()

    def qmark():
        nonlocal qs
        tail = "".join(word)
        m = re.search(r"\$([A-Za-z_][A-Za-z0-9_]*)$", tail)
        if m:  # R1-08: $A"ce" is $A followed by ce, not a variable named Ace
            word[:] = [tail[:m.start()] + "${" + m.group(1) + "}"]
        if qs is None:
            qs = sum(map(len, word))

    def flush():
        nonlocal word, in_word, quoted, pending, ug, qs, ud
        if not in_word:
            return
        text, q, g, u = "".join(word), quoted, ug, ud
        asg = "=" in text and (qs is None or text.index("=") < qs)
        word, in_word, quoted, ug, qs, ud = [], False, False, False, None, False
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
        cur.words.append(Word(text))
        cur.words[-1].glob, cur.words[-1].asg, cur.words[-1].ud = g, asg, u

    while i < n:
        c = src[i]
        if c == "\\":
            if i + 1 < n:
                if src[i + 1] != "\n":
                    qmark()
                    word.append(src[i + 1])
                    in_word = quoted = True
                i += 2
            else:
                i += 1
        elif c == "'":
            j = src.find("'", i + 1)
            if j < 0:
                raise ValueError("unterminated quote")
            qmark()
            word.append(src[i + 1:j])
            in_word = quoted = True
            i = j + 1
        elif c == '"':
            qmark()
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
            qmark()
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
            in_word = ud = True
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
            if src.startswith('$"', i):  # R1-11: the second $ of $$ is the PID, not a $"..." opener (only judged before any quote in the word)
                tail = "".join(word)
                if qs is not None or (len(tail) - len(tail.rstrip("$"))) % 2 == 0:
                    cur.gettext = True
            word.append(c)
            in_word = True
            ug = ug or c in "{}*?[~@+!"
            ud = ud or c == "$"
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
        if re.search(r"[$`]", c.split("=", 1)[0]):  # R1-07: core.hooks${x}Path
            deny("a git -c key built from a variable or substitution cannot be checked; write the key out")
        if RISKY_CONFIG.match(c):
            deny("this -c override can bypass the git hooks, hide a blocked command in an alias, or change what push targets")
    if i >= len(words):
        return
    sub, args = words[i], words[i + 1:]
    if "$" in sub or "`" in sub:
        deny("the git subcommand is built from a variable or substitution; write it out")
    flags, pos = split_args(args)
    flags = [re.split(r"[$`]", f, maxsplit=1)[0] for f in flags]  # R1-03: --force$Q is --force followed by whatever $Q holds
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

    if sub in ("commit", "push", "merge", "am", "cherry-pick", "rebase") and (
            any(opt(f, "--no-verify", 6) for f in flags) or (sub in ("commit", "am") and has_short(args, "n", "mFCctS"))):
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
            raw = r.split(":")[-1]  # globs match full ref names: refs/h* reaches refs/heads/main although norm_ref shortens it
            glob = re.search(r"[*?\[]", raw) and any(
                fnmatch.fnmatch(full, pat) for sh in SHARED for full in (sh, "refs/heads/" + sh) for pat in (raw, dst))
            if dst in SHARED or dst == "*" or glob:
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
    elif (sub == "clean" and any(re.fullmatch(r"-[a-zA-Z]*[fx][a-zA-Z]*", f) or opt(f, "--force", 4) for f in flags)) or (
            sub == "rm" and any(f == "-f" or opt(f, "--force", 4) for f in flags)):
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

def is_assign(w, mode):
    """mode "shell": the shell takes a word as an assignment only when its name and the = are unquoted ("FOO=x" and FOO\\=x are command
    names). mode "env" (right after env or sudo): the program takes every word with an = as one, whatever its name or quotes. mode "prog"
    (after nice, timeout, xargs, find -exec ...): the word is the program, bash runs it as a file name (R1-01)."""
    if mode == "env":
        return "=" in w and not w.startswith("-")
    return mode == "shell" and bool(ASSIGN.match(w)) and getattr(w, "asg", None) is not False


def long_value_option(o, opts):
    """R4-03: an option that takes a value, also written as an unambiguous prefix of its long name (getopt_long: --out for --output)."""
    return o in opts or (o.startswith("--") and "=" not in o and any(k.startswith(o) for k in opts if k.startswith("--")))


def unwrap(words, mode="shell"):
    """Strip env assignments, reserved words and wrapper commands.
    Returns (assignments, rest, nested command strings, wrapper names)."""
    assigns, nested, i, seen = [], [], 0, set()
    while i < len(words):
        w = words[i]
        if is_assign(w, mode):
            assigns.append(w)
            i += 1
            continue
        if w in RESERVED:
            i += 1
            if w in ("function", "coproc") and i + 1 < len(words) and (w == "function" or words[i + 1] in ("{", "(")):
                i += 1  # `function NAME {` and `coproc NAME {`: the name is not the command (R5-01)
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
            mode = "shell" if base == "time" else "env" if base in ("env", "sudo", "doas") else "prog"
            i += 1
            while i < len(words) and words[i].startswith("-") and words[i] != "--":
                o = words[i]
                i += 1
                val, split = None, False  # R1-06: the value of this option, from the word itself or the next word
                if o.startswith("--"):
                    key, eq, attached = o.partition("=")
                    if long_value_option(key, opts):
                        val = attached if eq else words[i] if i < len(words) else None
                        i += 0 if eq or val is None else 1
                        split = base == "env" and "--split-string".startswith(key)
                else:
                    for k, ch in enumerate(o[1:], 2):  # a cluster such as -vu FOO: the first letter that takes a value ends it
                        if "-" + ch in opts:
                            val = o[k:] if o[k:] else words[i] if i < len(words) else None
                            i += 0 if o[k:] or val is None else 1
                            split = base == "env" and ch == "S"
                            break
                if val is not None:
                    if split:
                        nested.append(val)
                    if base == "taskset":
                        npos = 0
            if i < len(words) and words[i] == "--":
                i += 1
            if base != "env":
                i += npos
            continue
        break
    return assigns, words[i:], nested, seen


LINTER_FLAGS = {  # flags that run a program (actionlint), rewrite files (zizmor --fix) or create directories
    "actionlint": re.compile(r"^--?(shellcheck|pyflakes|init-config)(=|$)"),
    "zizmor": re.compile(r"^--?(fix|cache-dir|lsp)(=|$)"),
}


def check_linter(prog, args):
    """The allow rules would approve these flags, and shell syntax that expands into them after the guard has looked."""
    for a in args:
        if LINTER_FLAGS[prog].match(a):
            deny(f"{prog} {a.split('=')[0]} runs programs, rewrites files or creates directories the allow rule does not cover")
        if "$" in a or "`" in a or (getattr(a, "glob", False) and not re.match(r"[A-Za-z0-9._/]", a)):
            deny(f"{prog} arguments built from $, backticks, ~, braces, globs or extglob cannot be checked; write them out")


def check_assign(a):
    name, plus, val = ASSIGN_PARTS.match(a).groups()
    if name in CONFIG_FILE_VARS:
        deny(f"{name} swaps git's config file, which can disable the hooks or hide aliases")
    if name.startswith("GIT_CONFIG") and plus:  # R4-06: bash joins X=a X+=b, and += may append to a value the guard cannot see
        deny("GIT_CONFIG_* built with += cannot be checked; assign the whole value with =")
    if (name == "GIT_CONFIG_PARAMETERS" or name.startswith("GIT_CONFIG_KEY_")) and re.search(r"[$`]", val):  # R1-07
        deny("GIT_CONFIG_* keys built from a variable or substitution cannot be checked; write them out")
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
    for q in BRANCH_SUBS:
        if q in w:
            w = w.replace(q, branch(state["cwd"]) or q)
    out = Word(re.sub(r"\$\{(\w+)\}|\$(\w+)", rep, w))
    out.glob = getattr(w, "glob", False)
    return out


def check_command_string(command, state, depth=0):
    if depth > 8:
        deny("command nesting is too deep to check")
    try:
        cmds = lex(command)
    except ValueError:
        flat = re.sub(r"\\\r?\n|['\"\\$]", "", command)  # quotes and continuations hide a name from the raw text (R3-03 of #237)
        if "$" in command or "`" in command or re.search(  # R4-05: an expansion or $'\xHH' can spell any name
                r"\bgit\b|CLAUDE\.md|REVIEW\.md|\.claude|\.github|\.githooks|agents/|scripts/|\.git/|mark-ready|update-branch", command + " " + flat):
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


def wrapper_is_pinned(root, name=MARK_READY):
    """R3-01: scripts/ is not a symlink, the wrapper is a regular file (not a symlink), and its SHA-256 is the pinned one."""
    scripts = os.path.join(root, "scripts")
    path = os.path.join(scripts, name)
    try:
        if os.path.islink(scripts) or not stat.S_ISREG(os.lstat(path).st_mode):
            return False
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest() == PINNED_WRAPPERS[name][0]
    except OSError:
        return False


def check_mark_ready(cmd, assigns, words, wrappers, state):
    """R2-01/R2-02/R3-01/R4-01: the exact call only, as the whole command, of the pinned wrapper. Raw words are judged, so $(...), backticks,
    $VAR, globs and braces never pass the argument checks. Runs when the command's first word is a wrapper name (mark-ready.sh or
    update-branch.sh); `bash scripts/mark-ready.sh N` is not matched by the allow rule."""
    here = os.path.realpath(state["cwd"])
    name = WRAPPER_PREFIX.search(words[0]).group(2)
    arg_patterns = PINNED_WRAPPERS[name][1]
    call = "scripts/" + name
    shape = f"`{call} " + ("<PR number> <40-hex sha>" if len(arg_patterns) == 2 else "<PR number>") + "`"
    # R4-01: the hash below is taken before anything else in the line runs
    whole = re.compile(re.escape(call) + "".join(" " + p.pattern for p in arg_patterns))
    if whole.fullmatch(state.get("whole", "").strip(" \t\n")) is None:
        deny(f"run the wrapper only as the whole command, exactly {shape}: nothing before, after or beside it "
             "(no ; && || | & newline, group, subshell, wrapper or nesting), because the guard checks the script before the rest of the line runs")
    exact = (words[0] == call and len(words) == len(arg_patterns) + 1 and all(p.fullmatch(w) for p, w in zip(arg_patterns, words[1:], strict=True))
             and not assigns and not wrappers and not (cmd.writes or cmd.heredocs or cmd.subs)
             and state["known"] and here in project_roots(state["cwd"]))
    if not exact:
        deny(f"run the wrapper only as exactly {shape} from the project root: no other path, no cd or env prefix, "
             "no wrapper, redirect or substitution (the project allow rule approves that text, so the guard narrows it)")
    if not wrapper_is_pinned(here, name):
        deny(f"{call} is missing, a symlink, or not the pinned version (SHA-256 in pretooluse_guard.py); "
             "only a tooling session may change the wrapper, together with the pin")


def split_words(e, state):
    """What bash makes of an unquoted expansion: fields split on IFS (blanks unless a literal IFS was set earlier on the line)."""
    ifs = state.get("ifs")
    if ifs is None:
        return e.split()
    return [p for p in re.split("[" + "".join(map(re.escape, ifs)) + "]", e) if p] if ifs else [e]


def check_simple(cmd, state, depth):
    if depth > 8:
        deny("command nesting is too deep to check")
    if cmd.gettext:  # R5-01: bash looks $"..." up in a message catalog when it parses the line, so its value cannot be known here
        deny('a $"..." word is translated by bash when it parses the line, so the guard cannot read it; write "..." without the $')
    for t in cmd.writes:
        guard_target(expand(t, state), state, "redirect to")
    assigns, words, nested, wrappers = unwrap(cmd.words, "prog" if cmd.prog_first else "shell")
    for a in assigns:
        if ASSIGN.match(a):  # after env or sudo every word with an = is one (A.B=1), but only NAME=v can be read
            check_assign(expand(a, state))
    for s in nested:
        check_command_string(s, child(state), depth + 1)
    if words and WRAPPER_PREFIX.search(words[0]):
        check_mark_ready(cmd, assigns, words, wrappers, state)
        return
    if len(words) > 1 and INDEXED.match(words[0]):  # R4-04: FOO[a[1]]=1 git push ... runs git; the subscript cannot be parsed reliably
        deny("an indexed assignment such as NAME[k]=v in front of a command is not an assignment in bash, but the command still runs; remove it")
    if not words:
        for a in assigns:  # a plain assignment statement: remember literal values
            name, plus, val = ASSIGN_PARTS.match(a).groups()
            if name == "IFS":  # R1-08: a literal IFS changes how an unquoted expansion splits; a computed one cannot be read
                val = expand(Word(val), state)
                state["ifs"], state["ifs_unknown"] = val, bool(re.search(r"[$`]", val))
            if plus:  # NAME+=v appends to a value we know (R1-03: also text that still holds an expansion); an unknown one is forgotten
                old = state["vars"].get(name)
                if old is None:
                    state["vars"].pop(name, None)
                else:
                    state["vars"][name] = old + expand(Word(val), state)
            elif val in BRANCH_SUBS:
                state["vars"][name] = branch(state["cwd"]) or val
            elif "$" in val or "`" in val:
                state["vars"].pop(name, None)
            else:
                state["vars"][name] = val
        return
    rest = []
    for w in words[1:]:
        e = expand(w, state)
        if getattr(w, "ud", False) and e != w:  # an unquoted expansion is split on blanks (P="--force origin"; git push $P) and may vanish
            for part in split_words(e, state):
                rest.append(Word(part))
                rest[-1].glob = e.glob
        else:
            rest.append(e)
    first = expand(words[0], state)
    if getattr(words[0], "ud", False) and first != words[0]:  # R1-08: X="git push"; $X --force origin work
        sub = Cmd()
        sub.words, sub.heredocs, sub.piped, sub.prog_first = [Word(p) for p in split_words(first, state)] + rest, cmd.heredocs, cmd.piped, True
        if sub.words:
            check_simple(sub, state, depth + 1)
        return
    words = [words[0]] + rest
    prog, args = os.path.basename(words[0]), words[1:]
    if "$" in words[0] or "`" in words[0]:
        if any(a in SENSITIVE_SUBS for a in args[:3]):
            deny("the command name is built from a variable or substitution; write it out")
        return
    if prog in LINTER_FLAGS:
        check_linter(prog, args)
    if prog == "shopt" and "extglob" in args:
        deny("shopt extglob makes patterns such as @(...) expand into flags the guard cannot see")
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
        if state.get("ifs_unknown"):
            deny("IFS is set to a value the guard cannot read, so it cannot tell how git's arguments split; write the value out")
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
    if prog == "trap":  # the first non-option argument is a command string the shell runs later (R5-01)
        for body in [a for a in args if not a.startswith("-")][:1]:
            check_command_string(body, child(state), depth + 1)
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
                sub.words, sub.prog_first = inner, True
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
                hit = re.search(r"(^|[\s'\"=/])" + re.escape(pat.rstrip("/")) + (r"(/|\b)" if pat.endswith("/") else r"\b"), code)
                if hit and (pat in ALWAYS or not TOOLING):
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
    if re.search("(" + "|".join(map(re.escape, PINNED_WRAPPERS)) + r")\\\r?\n", command):  # R5-02: `mark-ready.sh\<newline>1` joins to a different word
        deny("a line continuation right after a wrapper name is not allowed; write the exact call, e.g. `scripts/mark-ready.sh <PR number>`")
    check_command_string(command, {"cwd": cwd, "known": True, "vars": {}, "whole": command})


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
