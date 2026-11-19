"""Command line interface for openapi-breakcheck."""

from __future__ import annotations

import argparse
import json
import sys

from breakcheck import diff_specs, load_spec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openapi-breakcheck",
        description="Detect breaking changes between two OpenAPI 3.x specs.",
    )
    parser.add_argument("old_spec", help="Path to the old (baseline) spec file")
    parser.add_argument("new_spec", help="Path to the new (candidate) spec file")
    parser.add_argument(
        "--fail-on",
        default=None,
        help="Comma-separated change kinds that fail the check "
        "(default: any breaking change fails)",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="Output format: human-readable text (default) or one JSON document",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    old = load_spec(args.old_spec)
    new = load_spec(args.new_spec)
    changes = diff_specs(old, new)
    fail_kinds = (
        {k.strip() for k in args.fail_on.split(",")} if args.fail_on else None
    )
    failing = [c for c in changes if fail_kinds and c.kind in fail_kinds]
    if args.output == "json":
        summary = {"total": len(changes)}
        if fail_kinds is not None:
            summary["failing"] = len(failing)
        print(json.dumps({"changes": [c.to_dict() for c in changes], "summary": summary}, indent=2))
        if not changes:
            return 0
        if fail_kinds is not None:
            return 1 if failing else 0
        return 1
    for change in changes:
        print(change)
    if not changes:
        print("No breaking changes detected.")
        return 0
    if fail_kinds is not None:
        print(f"{len(changes)} breaking change(s), {len(failing)} matching --fail-on.")
        return 1 if failing else 0
    print(f"{len(changes)} breaking change(s) detected.")
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
