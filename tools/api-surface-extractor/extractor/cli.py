"""
CLI entry point for the API surface extractor.

Usage:
    extract-api-surface /path/to/codebase --output tech.md
    extract-api-surface /path/to/codebase --format yaml --output surface.yaml
    extract-api-surface /path/to/codebase --scan-all --output tech.md
"""

import argparse
import sys
from pathlib import Path

from .formatter import format_tech_md, format_yaml
from .scanner import Scanner


def main():
    parser = argparse.ArgumentParser(
        description="Extract API surface from a codebase using tree-sitter AST analysis"
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Root path of the codebase to scan",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("generated-tech.md"),
        help="Output file path (default: generated-tech.md in working directory)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["markdown", "yaml"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--scan-all",
        action="store_true",
        help="Scan all source files, not just surface-pattern matches",
    )
    parser.add_argument(
        "--project-name",
        type=str,
        default=None,
        help="Project name for the output header (default: directory name)",
    )

    args = parser.parse_args()

    if not args.path.is_dir():
        print(f"Error: {args.path} is not a directory", file=sys.stderr)
        sys.exit(1)

    project_name = args.project_name or args.path.name

    scanner = Scanner(args.path, scan_all=args.scan_all)
    result = scanner.scan()

    # Print summary to stderr
    print(f"Extracted:", file=sys.stderr)
    print(f"  Endpoints: {len(result.endpoints)}", file=sys.stderr)
    print(f"  Types: {len(result.types)}", file=sys.stderr)
    print(f"  Service methods: {len(result.service_methods)}", file=sys.stderr)
    if result.errors:
        print(f"  Warnings: {len(result.errors)}", file=sys.stderr)

    if args.format == "yaml":
        output = format_yaml(result)
    else:
        output = format_tech_md(result, project_name)

    args.output.write_text(output)
    print(f"Written to: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
