"""CLI entry point for ecosystem-map command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Config
from .extractors import extract_all
from .analyzers import analyze_cross_references
from .models import NodeType, EdgeType
from .outputs import export_json, export_html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ecosystem-map",
        description="Map the Claude Code ecosystem into an interactive graph",
    )
    parser.add_argument(
        "--claude-home",
        type=Path,
        default=None,
        help="Path to .claude directory (default: ~/.claude)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./out"),
        help="Output directory for generated files (default: ./out)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "html", "all"],
        default="all",
        help="Output format (default: all)",
    )
    parser.add_argument(
        "--project-dirs",
        type=Path,
        nargs="*",
        default=[],
        help="Project directories to scan for handoffs/wrapups (e.g. ~/JBK-Research/project1)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    args = parser.parse_args(argv)

    config = Config(claude_home=args.claude_home, project_dirs=args.project_dirs)
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1-2: Extract
    print("Extracting ecosystem data...")
    graph = extract_all(config)

    if args.verbose:
        for nt in NodeType:
            count = len(graph.get_nodes_by_type(nt))
            if count:
                print(f"  {nt.value}: {count} nodes")

    # Phase 3: Analyze cross-references
    print("Analyzing cross-references...")
    analyze_cross_references(graph, config)

    # Phase 4: Export
    if args.format in ("json", "all"):
        json_path = export_json(graph, output_dir)
        print(f"  JSON: {json_path}")

    if args.format in ("html", "all"):
        html_path = export_html(graph, output_dir)
        print(f"  HTML: {html_path}")

    # Summary
    stats = graph.to_dict()["stats"]
    print(f"\nEcosystem Summary:")
    print(f"  Total nodes: {stats['total_nodes']}")
    print(f"  Total edges: {stats['total_edges']}")
    print()
    print("  Nodes by type:")
    for type_name, count in sorted(stats.get("nodes_by_type", {}).items()):
        print(f"    {type_name:.<20} {count}")
    print()
    print("  Edges by type:")
    for type_name, count in sorted(stats.get("edges_by_type", {}).items()):
        print(f"    {type_name:.<20} {count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
