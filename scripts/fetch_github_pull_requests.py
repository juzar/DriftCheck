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
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, help="owner/repository")
    parser.add_argument("--commits-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--api-url", default="https://api.github.com")
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN", "")
    result = {}
    for line in args.commits_file.read_text(encoding="utf-8").splitlines():
        sha = line.split("\x1f", 1)[0]
        try:
            pulls = request(f"{args.api_url}/repos/{args.repository}/commits/{sha}/pulls", token)
        except (HTTPError, URLError) as error:
            detail = getattr(error, "code", str(error))
            print(f"::warning::Could not map {sha} to a pull request: {detail}", file=sys.stderr)
            result[sha] = []
            continue
        mapped = []
        for pull in pulls:
            if not pull.get("merged_at"):
                continue
            number = pull["number"]
            reviewers = []
            try:
                reviews = request(f"{args.api_url}/repos/{args.repository}/pulls/{number}/reviews", token)
                reviewers = sorted({review["user"]["login"] for review in reviews if review.get("user")})
            except (HTTPError, URLError) as error:
                detail = getattr(error, "code", str(error))
                print(f"::warning::Could not retrieve reviewers for PR #{number}: {detail}", file=sys.stderr)
            mapped.append({"number": number, "title": pull["title"], "creator": pull["user"]["login"],
                           "url": pull["html_url"], "merged_at": pull["merged_at"], "reviewers": reviewers})
        result[sha] = mapped
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
