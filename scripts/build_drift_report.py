#!/usr/bin/env python3
"""Create JSON and Markdown drift reports from Git outputs and GitHub PR API data."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def lines(path: Path) -> list[str]:
    return [line for line in read(path).splitlines() if line]


def parse_numstat(raw: str) -> list[dict]:
    entries = []
    for line in raw.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        added, removed, name = parts
        try:
            additions = None if added == "-" else int(added)
            deletions = None if removed == "-" else int(removed)
        except ValueError as error:
            raise ValueError(f"Invalid numstat entry: {line!r}") from error
        entries.append({"path": name, "additions": additions, "deletions": deletions})
    return entries


def parse_commits(raw: str, prs: dict) -> list[dict]:
    commits = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        parts = line.split("\x1f", 4)
        if len(parts) != 5 or not parts[0]:
            raise ValueError(f"Invalid commits entry on line {line_number}")
        sha, author, email, authored_at, subject = parts
        pull_requests = prs.get(sha, [])
        if not isinstance(pull_requests, list):
            raise ValueError(f"Pull-request mapping for commit {sha} must be a list")
        commits.append({"sha": sha, "author": author, "email": email,
                        "authored_at": authored_at, "subject": subject,
                        "pull_requests": pull_requests})
    return commits


def markdown(report: dict) -> str:
    output = ["# Repository drift report", "", f"- **Baseline:** `{report['baseline']}`", f"- **Target:** `{report['target']}`", f"- **Generated (UTC):** {report['generated_at']}", f"- **Drift detected:** {'yes' if report['drift_detected'] else 'no'}", "",
              "## Diff summary", "", "```text", report["diff"]["shortstat"] or "No changed files.", report["diff"]["stat"] or "", "```", "",
              "## Changed files", "", "| Status | File | Additions | Deletions |", "| --- | --- | ---: | ---: |"]
    nums = {item["path"]: item for item in report["diff"]["numstat"]}
    for row in report["diff"]["name_status"]:
        status, path = (row.split("\t", 1) + [""])[:2]
        count = nums.get(path, {})
        safe_status = status.replace("\\", "\\\\").replace("`", "\\`").replace("|", "\\|")
        safe_path = path.replace("\\", "\\\\").replace("`", "\\`").replace("|", "\\|").replace("\n", "\\n").replace("\r", "\\r")
        output.append(f"| `{safe_status}` | `{safe_path}` | {count.get('additions', '')} | {count.get('deletions', '')} |")
    if not report["diff"]["name_status"]:
        output.append("| — | No changed files | 0 | 0 |")
    output.extend(["", "## Commits and merged pull requests", ""])
    for commit in report["commits"]:
        output.extend([f"### `{commit['sha']}` — {commit['subject']}",
                       f"Author: {commit['author']} <{commit['email']}> · {commit['authored_at']}"])
        if not commit["pull_requests"]:
            output.append("\nNo merged pull request was returned by the GitHub API for this commit.")
        for pr in commit["pull_requests"]:
            reviewers = ", ".join(pr.get("reviewers", [])) or "Not available"
            output.append(f"\n- PR [#{pr['number']}]({pr['url']}) — {pr['title']}\n"
                          f"  - Creator: {pr['creator']}\n  - Merged: {pr.get('merged_at') or 'Not available'}\n  - Reviewers: {reviewers}")
        output.append("")
    output.extend(["## Precise name/status output", "", "```text", report["diff"]["name_status_raw"] or "No changed files.", "```", ""])
    return "\n".join(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    data = args.input_dir
    try:
        prs = json.loads(read(data / "pull-requests.json") or "{}")
    except json.JSONDecodeError as error:
        raise SystemExit(f"Invalid pull-request mapping JSON: {error}") from error
    if not isinstance(prs, dict):
        raise SystemExit("Pull-request mapping must be a JSON object")
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "baseline": args.baseline,
              "target": args.target, "diff": {"name_status_raw": read(data / "name-status.txt").rstrip(),
              "name_status": lines(data / "name-status.txt"), "numstat": parse_numstat(read(data / "numstat.txt")),
              "stat": read(data / "stat.txt").rstrip(), "shortstat": read(data / "shortstat.txt").rstrip()},
              "commits": parse_commits(read(data / "commits.txt"), prs)}
    report["drift_detected"] = bool(report["diff"]["name_status"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "drift-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "drift-report.md").write_text(markdown(report), encoding="utf-8")

if __name__ == "__main__":
    main()
