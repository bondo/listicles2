"""Tests for scripts/status_publish.py against a real bare repository. Run: python3 -I scripts/test_status_publish.py"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import status_publish  # noqa: E402  # justified: must follow the sys.path insert above
import status_visual  # noqa: E402  # justified: must follow the sys.path insert above

SCRIPT = Path(__file__).resolve().parent / "status_publish.py"
ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_TERMINAL_PROMPT": "0"}


def svg(stamp="2026-11-13 12:00 UTC", body="one"):
    return (f'<svg xmlns="http://www.w3.org/2000/svg"><text>{body}</text>'
            f'<text id="{status_visual.STAMP_ID}">updated {stamp}</text></svg>\n')


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **ENV})
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


class Publish(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.origin = root / "origin.git"
        self.work = root / "work"
        git(root, "init", "-q", "--bare", str(self.origin))
        git(root, "init", "-q", str(self.work))
        git(self.work, "remote", "add", "origin", str(self.origin))
        patcher = mock.patch.dict(os.environ, ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.svg, self.json = root / "status.svg", root / "status.json"

    def publish(self, stamp="2026-11-13 12:00 UTC", body="one", md=None, graph=None):
        self.svg.write_text(svg(stamp, body))
        self.json.write_text(f'{{"generated_at": "{stamp}"}}\n')
        if md is not None:
            (self.svg.parent / "status.md").write_text(md)
        if graph is not None:
            (self.svg.parent / "status-graph.svg").write_text(graph)
        return status_publish.publish(str(self.work), str(self.svg), str(self.json))

    def count(self):
        out = git(self.origin, "rev-list", "--count", "refs/heads/status")
        return int(out)

    def test_creates_an_orphan_branch_when_missing(self):
        self.assertEqual(self.publish(), "created")
        self.assertEqual(self.count(), 1)
        self.assertEqual(git(self.origin, "show", "refs/heads/status:status.svg"), svg().strip())
        self.assertIn("generated_at", git(self.origin, "show", "refs/heads/status:status.json"))
        self.assertEqual(git(self.origin, "log", "-1", "--format=%P", "refs/heads/status"), "")
        self.assertEqual(sorted(git(self.origin, "ls-tree", "--name-only", "refs/heads/status").split()),
                         ["status.json", "status.svg"])

    def test_publishes_the_detail_page_found_next_to_the_svg(self):
        self.assertEqual(self.publish(md="# page\n"), "created")
        self.assertEqual(git(self.origin, "show", "refs/heads/status:status.md"), "# page")
        self.assertEqual(sorted(git(self.origin, "ls-tree", "--name-only", "refs/heads/status").split()),
                         ["status.json", "status.md", "status.svg"])

    def test_an_explicit_md_path_is_used(self):
        other = Path(self.tmp.name) / "elsewhere.md"
        other.write_text("# other\n")
        self.svg.write_text(svg())
        self.json.write_text("{}")
        self.assertEqual(status_publish.publish(str(self.work), str(self.svg), str(self.json), md_path=str(other)), "created")
        self.assertEqual(git(self.origin, "show", "refs/heads/status:status.md"), "# other")

    def test_an_explicit_md_path_that_cannot_be_read_is_an_error(self):
        self.svg.write_text(svg())
        self.json.write_text("{}")
        with self.assertRaises(status_publish.PublishError):
            status_publish.publish(str(self.work), str(self.svg), str(self.json), md_path="/nonexistent.md")

    def test_without_a_page_nothing_changes_for_the_old_layout(self):
        self.assertEqual(self.publish(), "created")
        self.assertEqual(self.publish(stamp="2026-11-13 12:30 UTC"), "unchanged")

    def test_stamp_only_change_with_the_same_page_makes_no_commit(self):
        self.publish(md="# page\n")
        self.assertEqual(self.publish(stamp="2026-11-13 12:30 UTC", md="# page\n"), "unchanged")
        self.assertEqual(self.count(), 1)

    def test_a_changed_page_alone_is_a_real_change(self):
        self.publish(md="# page\n")
        self.assertEqual(self.publish(md="# page two\n"), "updated")
        self.assertEqual(self.count(), 2)
        self.assertEqual(git(self.origin, "show", "refs/heads/status:status.md"), "# page two")

    def test_adding_a_page_to_a_branch_that_has_none_is_a_real_change(self):
        self.publish()
        self.assertEqual(self.publish(md="# page\n"), "updated")

    def test_publishing_without_a_page_keeps_the_page_already_on_the_branch(self):
        self.publish(md="# page\n")
        (self.svg.parent / "status.md").unlink()
        self.assertEqual(self.publish(body="two"), "updated")
        self.assertEqual(git(self.origin, "show", "refs/heads/status:status.md"), "# page")
        self.assertEqual(git(self.origin, "ls-tree", "--name-only", "refs/heads/status").split(), ["status.json", "status.md", "status.svg"])

    def test_without_a_page_anywhere_the_branch_still_has_no_page(self):
        self.publish()
        self.assertEqual(self.publish(body="two"), "updated")
        self.assertEqual(git(self.origin, "ls-tree", "--name-only", "refs/heads/status").split(), ["status.json", "status.svg"])

    def test_publishes_the_graph_found_next_to_the_svg(self):
        self.assertEqual(self.publish(graph="<svg>g</svg>\n"), "created")
        self.assertEqual(git(self.origin, "show", "refs/heads/status:status-graph.svg"), "<svg>g</svg>")
        self.assertEqual(git(self.origin, "ls-tree", "--name-only", "refs/heads/status").split(),
                         ["status-graph.svg", "status.json", "status.svg"])

    def test_the_graph_is_published_with_the_page_too(self):
        self.publish(md="# page\n", graph="<svg>g</svg>\n")
        self.assertEqual(git(self.origin, "ls-tree", "--name-only", "refs/heads/status").split(),
                         ["status-graph.svg", "status.json", "status.md", "status.svg"])

    def test_an_unchanged_graph_makes_no_commit_and_a_changed_one_does(self):
        self.publish(graph="<svg>g</svg>\n")
        self.assertEqual(self.publish(stamp="2026-11-13 12:30 UTC", graph="<svg>g</svg>\n"), "unchanged")
        self.assertEqual(self.count(), 1)
        self.assertEqual(self.publish(graph="<svg>g2</svg>\n"), "updated")
        self.assertEqual(self.count(), 2)
        self.assertEqual(git(self.origin, "show", "refs/heads/status:status-graph.svg"), "<svg>g2</svg>")

    def test_a_graph_change_alone_is_a_real_change_even_with_the_same_page(self):
        self.publish(md="# page\n", graph="<svg>g</svg>\n")
        self.assertEqual(self.publish(md="# page\n", graph="<svg>other</svg>\n"), "updated")

    def test_adding_a_graph_to_a_branch_that_has_none_is_a_real_change(self):
        self.publish(md="# page\n")
        self.assertEqual(self.publish(md="# page\n", graph="<svg>g</svg>\n"), "updated")

    def test_publishing_without_a_graph_keeps_the_graph_already_on_the_branch(self):
        self.publish(graph="<svg>g</svg>\n")
        (self.svg.parent / "status-graph.svg").unlink()
        self.assertEqual(self.publish(body="two"), "updated")
        self.assertEqual(git(self.origin, "show", "refs/heads/status:status-graph.svg"), "<svg>g</svg>")

    def test_the_graph_is_compared_exactly_not_ignoring_a_stamp(self):
        stamped = svg("2026-11-13 12:00 UTC", "g")
        self.publish(graph=stamped)
        self.assertEqual(self.publish(graph=svg("2026-11-13 13:00 UTC", "g")), "updated")

    def test_an_explicit_graph_path_is_used_and_an_unreadable_one_is_an_error(self):
        other = Path(self.tmp.name) / "elsewhere.svg"
        other.write_text("<svg>x</svg>\n")
        self.svg.write_text(svg())
        self.json.write_text("{}")
        self.assertEqual(status_publish.publish(str(self.work), str(self.svg), str(self.json), graph_path=str(other)), "created")
        self.assertEqual(git(self.origin, "show", "refs/heads/status:status-graph.svg"), "<svg>x</svg>")
        with self.assertRaises(status_publish.PublishError):
            status_publish.publish(str(self.work), str(self.svg), str(self.json), graph_path="/nonexistent.svg")

    def test_stamp_only_change_makes_no_commit(self):
        self.publish()
        self.assertEqual(self.publish(stamp="2026-11-13 12:30 UTC"), "unchanged")
        self.assertEqual(self.count(), 1)
        self.assertIn("12:00", git(self.origin, "show", "refs/heads/status:status.svg"))

    def test_real_change_adds_a_fast_forward_commit(self):
        self.publish()
        first = git(self.origin, "rev-parse", "refs/heads/status")
        self.assertEqual(self.publish(stamp="2026-11-13 13:00 UTC", body="two"), "updated")
        self.assertEqual(self.count(), 2)
        self.assertEqual(git(self.origin, "log", "-1", "--format=%P", "refs/heads/status"), first)
        self.assertIn("two", git(self.origin, "show", "refs/heads/status:status.svg"))

    def test_picks_up_a_branch_pushed_by_someone_else_and_builds_on_it(self):
        self.publish()
        other = Path(self.tmp.name) / "other"
        git(self.tmp.name, "clone", "-q", "-b", "status", str(self.origin), str(other))
        (other / "README.txt").write_text("hi")
        git(other, "add", "README.txt")
        git(other, "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-q", "-m", "other")
        git(other, "push", "-q", "origin", "status")
        self.assertEqual(self.publish(stamp="2026-11-13 13:00 UTC", body="two"), "updated")
        self.assertEqual(self.count(), 3)  # root, the other commit, ours

    def test_unreachable_remote_is_an_error_not_a_reason_to_create_the_branch(self):
        git(self.work, "remote", "set-url", "origin", str(Path(self.tmp.name) / "nope.git"))
        with self.assertRaises(status_publish.PublishError):
            self.publish()

    def test_missing_input_file_is_an_error(self):
        with self.assertRaises(status_publish.PublishError):
            status_publish.publish(str(self.work), "/nonexistent.svg", "/nonexistent.json")

    def test_refuses_to_publish_other_branches(self):
        self.svg.write_text(svg())
        self.json.write_text("{}")
        for bad in ("main", "master", "refs/heads/main", "a b", "-x"):
            with self.subTest(bad), self.assertRaises(status_publish.PublishError):
                status_publish.publish(str(self.work), str(self.svg), str(self.json), branch=bad)

    def test_cli_reports_the_outcome(self):
        self.svg.write_text(svg())
        self.json.write_text("{}")
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--repo", str(self.work), "--svg", str(self.svg),
                            "--json", str(self.json)], capture_output=True, text=True, env={**os.environ, **ENV})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("created", r.stdout)
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--repo", str(self.work), "--svg", "/nonexistent.svg",
                            "--json", str(self.json)], capture_output=True, text=True, env={**os.environ, **ENV})
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
