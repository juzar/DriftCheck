"""Regression tests for the report-producing command-line scripts."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


builder = load_script("build_drift_report")
fetcher = load_script("fetch_github_pull_requests")


class BuildReportTests(unittest.TestCase):
    def test_rejects_malformed_commit_input(self):
        with self.assertRaisesRegex(ValueError, "line 1"):
            builder.parse_commits("not a commit\n", {})

    def test_numstat_rejects_non_numeric_counts(self):
        with self.assertRaisesRegex(ValueError, "Invalid numstat"):
            builder.parse_numstat("one\t0\tfile.txt\n")

    def test_rejects_non_list_pull_request_mapping(self):
        raw = "abc\x1fA\x1fa@example.test\x1f2026-01-01T00:00:00+00:00\x1fsubject\n"
        with self.assertRaisesRegex(ValueError, "must be a list"):
            builder.parse_commits(raw, {"abc": {}})

    def test_markdown_escapes_table_delimiters_in_paths(self):
        report = {
            "baseline": "base", "target": "head", "generated_at": "now", "drift_detected": True,
            "diff": {"shortstat": "1 file changed", "stat": "", "name_status_raw": "M\tbad|name",
                     "name_status": ["M\tbad|`name"], "numstat": [{"path": "bad|`name", "additions": 1, "deletions": 0}]},
            "commits": [],
        }
        self.assertIn("`bad\\|\\`name`", builder.markdown(report))


class FetchPullRequestsTests(unittest.TestCase):
    def test_unexpected_api_response_is_a_warning_and_output_is_created(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commits = root / "commits.txt"
            output = root / "nested" / "pulls.json"
            commits.write_text("abc123\x1fauthor\n", encoding="utf-8")
            with patch.object(fetcher, "request", side_effect=ValueError("unexpected response")), patch.object(
                sys, "argv", ["fetch", "--repository", "owner/repo", "--commits-file", str(commits), "--output", str(output)]
            ):
                fetcher.main()
            self.assertEqual({"abc123": []}, json.loads(output.read_text(encoding="utf-8")))

    def test_request_rejects_non_list_json(self):
        with patch.object(fetcher, "urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = object()
            with patch.object(fetcher.json, "load", return_value={"message": "rate limited"}):
                with self.assertRaisesRegex(ValueError, "unexpected response"):
                    fetcher.request("https://example.test", "")

    def test_malformed_pull_response_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commits, output = root / "commits.txt", root / "pulls.json"
            commits.write_text("abc123\x1fauthor\n", encoding="utf-8")
            with patch.object(fetcher, "request", side_effect=[[{"merged_at": "now"}]]), patch.object(
                sys, "argv", ["fetch", "--repository", "owner/repo", "--commits-file", str(commits), "--output", str(output)]
            ):
                fetcher.main()
            self.assertEqual({"abc123": []}, json.loads(output.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
