#!/usr/bin/env python3
"""Fetch what scripts/status_visual.py needs from the GitHub REST API into one JSON file (via `gh api`, read-only).

Usage: python3 -I scripts/status_fetch.py --repo OWNER/NAME --out input.json   (GH_TOKEN or GITHUB_TOKEN in the environment)

Only issues and PRs by OWNER, MEMBER or COLLABORATOR authors are kept (outsiders' needs-owner questions are only counted).
Fetches open PRs (draft flag, behind main, CI state from check runs of the head commit) and issues labelled
owner-todo (open and closed), needs-owner, blocked and follow-up (open). Arguments reach `gh` as a list, never a shell.
Exit 2 on any API or usage error: a failed fetch must not render an empty status.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
ISSUE_LABELS = (("owner-todo", "all"), ("needs-owner", "open"), ("blocked", "open"), ("follow-up", "open"))
TRUSTED = ("OWNER", "MEMBER", "COLLABORATOR")
OWN_CHECK = "publish"  # the status workflow's own job: it must not decide a PR's CI state
FAILED = ("failure", "timed_out", "cancelled", "action_required", "startup_failure", "stale")


class FetchError(Exception):
    pass


def gh_api(path):
    """GET a REST path with gh; list endpoints are paginated and flattened into one list."""
    res = subprocess.run(["gh", "api", "--paginate", "--slurp", path], capture_output=True, text=True)
    if res.returncode != 0:
        raise FetchError(f"gh api {path}: {res.stderr.strip()[:200] or 'failed'}")
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        raise FetchError(f"gh api {path}: not JSON") from None
    if isinstance(data, list) and all(isinstance(p, list) for p in data):
        return [x for page in data for x in page]
    if isinstance(data, list) and data and all(isinstance(p, dict) for p in data):
        if any("check_runs" in p for p in data):
            return {"check_runs": [r for p in data for r in p.get("check_runs", [])]}
        return data[0] if len(data) == 1 else data
    return data


def ci_state(runs):
    runs = [r for r in runs if r.get("name") != OWN_CHECK]
    if not runs:
        return "none"
    if any(r.get("conclusion") in FAILED for r in runs):
        return "failing"
    if any(r.get("status") != "completed" for r in runs):
        return "pending"
    return "passing"


def trusted(pr, repo):
    """Same-repository PRs, or PRs whose author has Write-or-better: an outsider's fork PR never reaches the README."""
    head = (pr.get("head") or {}).get("repo") or {}
    return str(head.get("full_name", "")).lower() == repo.lower() or pr.get("author_association") in TRUSTED


def fetch(api, repo, sleep=time.sleep):
    if not isinstance(repo, str) or not REPO.fullmatch(repo) or ".." in repo:
        raise FetchError("--repo must look like OWNER/NAME")
    prs = []
    for p in (p for p in api(f"repos/{repo}/pulls?state=open&per_page=100") if trusted(p, repo)):
        n, sha = int(p["number"]), p["head"]["sha"]
        detail = api(f"repos/{repo}/pulls/{n}")
        if detail.get("mergeable_state") == "unknown":  # GitHub computes it lazily: ask once more
            sleep(2)
            detail = api(f"repos/{repo}/pulls/{n}")
        runs = api(f"repos/{repo}/commits/{sha}/check-runs?per_page=100").get("check_runs", [])
        prs.append({"number": n, "title": p.get("title", ""), "draft": p.get("draft") is True,
                    "behind": detail.get("mergeable_state") == "behind",
                    "merge_unknown": detail.get("mergeable_state") == "unknown", "ci": ci_state(runs)})
    issues, outside = {}, set()
    for label, state in ISSUE_LABELS:
        for i in api(f"repos/{repo}/issues?state={state}&labels={label}&per_page=100"):
            if "pull_request" in i:
                continue
            if i.get("author_association") not in TRUSTED:
                # The question issue form labels every outsider's issue needs-owner: count those, never show or use them.
                if label == "needs-owner" and i.get("state", "open") == "open":
                    outside.add(int(i["number"]))
            else:
                issues[int(i["number"])] = {
                    "number": int(i["number"]), "title": i.get("title", ""), "state": i.get("state", "open"),
                    "state_reason": i.get("state_reason"), "created_at": i.get("created_at"),
                    "labels": [x["name"] if isinstance(x, dict) else x for x in i.get("labels", [])]}
    return {"fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "prs": prs,
            "outside_questions": len(outside), "issues": [issues[k] for k in sorted(issues)]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fetch status inputs from the GitHub REST API.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    try:
        data = fetch(gh_api, args.repo)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
    except (FetchError, OSError, KeyError, TypeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
