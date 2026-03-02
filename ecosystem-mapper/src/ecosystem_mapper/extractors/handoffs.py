"""Extract Handoff nodes from project-level and global handoff directories."""

from __future__ import annotations

import re
from pathlib import Path

from ..models import GraphNode, GraphEdge, NodeType, EdgeType
from ..parsers import BodyParser
from .base import BaseExtractor


class HandoffExtractor(BaseExtractor):
    """Parse handoff markdown files into Handoff nodes + CONTINUES edges."""

    def extract(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        # Collect all handoff directories to scan
        handoff_dirs = self._collect_handoff_dirs()

        seen_ids: set[str] = set()
        for handoff_dir in handoff_dirs:
            for path in self.safe_glob(handoff_dir, "*.md"):
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue

                fm, body = self.parse_frontmatter(text)
                name = path.stem
                handoff_id = f"handoff:{name}"

                if handoff_id in seen_ids:
                    continue
                seen_ids.add(handoff_id)

                props: dict = {
                    "handoff_id": fm.get("handoff_id", name),
                    "date": fm.get("date", ""),
                    "status": fm.get("status", ""),
                    "parent_handoffs": fm.get("parent_handoffs", []),
                    "_body": body,
                }
                props.update(BodyParser.parse(body))

                nodes.append(GraphNode(
                    id=handoff_id,
                    node_type=NodeType.HANDOFF,
                    name=name,
                    description=fm.get("description", "")[:200],
                    source_file=str(path),
                    namespace="handoffs",
                    properties=props,
                ))

                # Create CONTINUES edges from parent handoff references
                parents = fm.get("parent_handoffs", [])
                if isinstance(parents, str):
                    parents = [parents]
                for parent_ref in parents:
                    parent_stem = Path(parent_ref).stem if "/" in parent_ref else parent_ref
                    edges.append(GraphEdge(
                        source_id=handoff_id,
                        target_id=f"handoff:{parent_stem}",
                        edge_type=EdgeType.CONTINUES,
                        properties={"parent_ref": parent_ref},
                    ))

        return nodes, edges

    def _collect_handoff_dirs(self) -> list[Path]:
        """Collect handoff directories from global fallback + project dirs."""
        dirs: list[Path] = []

        # Global fallback
        global_dir = self.config.handoffs_dir
        if global_dir.exists():
            dirs.append(global_dir)

        # Project-level directories
        for project_dir in self.config.project_dirs:
            project_handoffs = project_dir / ".claude" / "handoffs"
            if project_handoffs.exists():
                dirs.append(project_handoffs)

        return dirs
