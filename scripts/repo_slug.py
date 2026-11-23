#!/usr/bin/env python3
"""The GitHub repository (OWNER/NAME) of this checkout, from one place (M1-85), so a repo rename needs no script change.

Order: $GITHUB_REPOSITORY when set and not empty (GitHub Actions; an invalid value fails, it never falls back), else the
`origin` remote of the checkout that holds this file, else an error. Git runs with the repository variables dropped and
no global or system config, so only the checkout's own .git/config names the remote. mark-ready.sh and update-branch.sh parse
the remote themselves with the same forms (their content is pinned, so they run no helper; test_mark_ready.py checks they agree).
Remote forms: https://github.com/O/N, git@github.com:O/N, ssh://git@github.com[:port]/O/N (each with or without .git), and
the cloud git proxy http://<user>@127.0.0.1:<port>/git/O/N. Standard library only.
Usage: scripts/repo_slug.py   prints OWNER/NAME; exit 1 with the reason on stderr, 2 on bad usage."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLUG = r"(?P<slug>[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100})"
USER = r"(?:[^@/\s]+@)?"
SCP_USER = r"(?:[^@/:\s]+@)?"  # in git@github.com:O/N a colon before the @ would make the text before it the host
FORMS = [re.compile(p + SLUG + r"/?") for p in (
    rf"https?://{USER}(?:www\.)?github\.com/",
    rf"{SCP_USER}github\.com:",
    rf"ssh://{USER}github\.com(?::\d{{1,5}})?/",
    rf"https?://{USER}(?:127\.0\.0\.1|localhost)(?::\d{{1,5}})?/git/",
)]
SLUG_RE = re.compile(SLUG)
REPO_GIT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_CEILING_DIRECTORIES",
                 "GIT_DISCOVERY_ACROSS_FILESYSTEM", "GIT_OBJECT_DIRECTORY", "GIT_INDEX_FILE", "GIT_NAMESPACE")


class RepoSlugError(Exception):
    pass


def valid(slug: str) -> bool:
    return bool(SLUG_RE.fullmatch(slug)) and slug.split("/")[1] not in (".", "..")


def slug_from_url(url: str) -> str | None:
    """OWNER/NAME from a GitHub remote URL in one of the forms above, else None."""
    for form in FORMS:
        m = form.fullmatch(url)
        if m:
            owner, name = m.group("slug").split("/")
            name = name[:-4] if name.endswith(".git") else name
            return f"{owner}/{name}" if name and valid(f"{owner}/{name}") else None
    return None


def origin_url(root: Path) -> str:
    env = {k: v for k, v in os.environ.items() if k not in REPO_GIT_VARS and not k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_CEILING_DIRECTORIES=str(Path(root).resolve().parent))
    try:
        p = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True, env=env, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RepoSlugError(f"could not run git for the origin remote: {e}") from None
    if p.returncode != 0:
        raise RepoSlugError(f"no origin remote in {root} (git: {p.stderr.strip()[:200]})")
    return p.stdout.rstrip("\n")


def resolve(environ: Mapping[str, str] | None = None, root: Path = ROOT) -> str:
    """The repository slug, or RepoSlugError with the reason."""
    env_slug = (os.environ if environ is None else environ).get("GITHUB_REPOSITORY", "")
    if env_slug:
        if not valid(env_slug):
            raise RepoSlugError(f"GITHUB_REPOSITORY is not OWNER/NAME: {env_slug[:100]!r}")
        return env_slug
    url = origin_url(root)
    slug = slug_from_url(url)
    if slug is None:
        shown = re.sub(r"//[^@/]*@", "//***@", url)[:200]  # never print a token in the URL
        raise RepoSlugError(f"the origin remote is not a GitHub repository URL this script knows: {shown!r}")
    return slug


def main(argv: list[str]) -> int:
    if argv:
        print("usage: scripts/repo_slug.py", file=sys.stderr)
        return 2
    try:
        print(resolve())
    except RepoSlugError as e:
        print(f"repo_slug: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
