#!/usr/bin/env python3
"""Require a DCO sign-off for each human-authored pull-request commit."""

import re
import subprocess
import sys


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def main(base, head):
    commits = git("rev-list", f"{base}..{head}").splitlines()
    failures = []
    for commit in commits:
        author = git("show", "-s", "--format=%an%n%ae", commit).splitlines()
        if author[0].endswith("[bot]") or author[1].casefold() == "153565009+tlothian-cc@users.noreply.github.com":
            continue
        message = git("show", "-s", "--format=%B", commit)
        trailers = re.findall(r"(?im)^Signed-off-by:\s*(.+?)\s*<([^<>]+)>\s*$", message)
        if not any(name.casefold() == author[0].casefold() and email.casefold() == author[1].casefold() for name, email in trailers):
            failures.append(commit[:12])
    if failures:
        raise SystemExit("Missing author-matching Signed-off-by trailer: " + ", ".join(failures))
    print(f"DCO sign-off verified for {len(commits)} pull-request commits")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: check_dco.py BASE_SHA HEAD_SHA")
    main(sys.argv[1], sys.argv[2])
