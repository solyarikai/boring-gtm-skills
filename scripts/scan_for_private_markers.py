#!/usr/bin/env python3
"""Fail if public files contain private infrastructure markers."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


DEFAULT_MARKERS = [
    "onsocial-outreach",
    "hetzner",
    "leadgen-postgres",
    "load_prod_core",
    "project_id = 42",
    "project_id=42",
]

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "tmp", "output", "reports"}


def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan for private markers.")
    parser.add_argument("--root", default=".", help="Repository root to scan")
    parser.add_argument("--marker", action="append", default=[], help="Additional marker")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    markers = DEFAULT_MARKERS + args.marker
    findings = []
    for path in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            for marker in markers:
                if marker in line:
                    findings.append((path.relative_to(root), idx, marker))

    for rel, line_no, marker in findings:
        print(f"{rel}:{line_no}: private marker found: {marker}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
