#!/usr/bin/env python3
"""Map commits to merged GitHub pull requests using GitHub's REST API."""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request(url: str, token: str):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "drift-report-workflow"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise ValueError(f"GitHub API returned an unexpected response for {url}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, help="owner/repository")
    parser.add_argument("--commits-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--api-url", default="https://api.github.com")
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN", "")
    result = {}
    for line_number, line in enumerate(args.commits_file.read_text(encoding="utf-8").splitlines(), start=1):
        sha = line.split("\x1f", 1)[0]
        if not sha:
            print(f"::warning::Ignoring commits-file entry with no SHA on line {line_number}", file=sys.stderr)
            continue
        try:
            pulls = request(f"{args.api_url}/repos/{args.repository}/commits/{sha}/pulls", token)
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            detail = getattr(error, "code", str(error))
            print(f"::warning::Could not map {sha} to a pull request: {detail}", file=sys.stderr)
            result[sha] = []
            continue
        mapped = []
        for pull in pulls:
            if not isinstance(pull, dict):
                print(f"::warning::Ignoring malformed pull-request response for commit {sha}", file=sys.stderr)
                continue
            if not pull.get("merged_at"):
                continue
            number = pull.get("number")
            user = pull.get("user")
            if not isinstance(number, int) or not isinstance(user, dict) or not user.get("login") or not pull.get("title") or not pull.get("html_url"):
                print(f"::warning::Ignoring incomplete pull-request response for commit {sha}", file=sys.stderr)
                continue
            reviewers = []
            try:
                reviews = request(f"{args.api_url}/repos/{args.repository}/pulls/{number}/reviews", token)
                reviewers = sorted({review["user"]["login"] for review in reviews
                                    if isinstance(review, dict) and isinstance(review.get("user"), dict)
                                    and review["user"].get("login")})
            except (HTTPError, URLError, TimeoutError, ValueError) as error:
                detail = getattr(error, "code", str(error))
                print(f"::warning::Could not retrieve reviewers for PR #{number}: {detail}", file=sys.stderr)
            mapped.append({"number": number, "title": pull["title"], "creator": pull["user"]["login"],
                           "url": pull["html_url"], "merged_at": pull["merged_at"], "reviewers": reviewers})
        result[sha] = mapped
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
