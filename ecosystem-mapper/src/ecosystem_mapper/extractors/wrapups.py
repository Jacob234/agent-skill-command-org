"""Extract Wrapup nodes from project-level and global wrapup directories."""

from __future__ import annotations

from pathlib import Path

from ..models import GraphNode, GraphEdge, NodeType, EdgeType
from ..parsers import BodyParser
from .base import BaseExtractor


class WrapupExtractor(BaseExtractor):
    """Parse wrapup markdown files into Wrapup nodes + DOCUMENTS edges."""

    def extract(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        wrapup_dirs = self._collect_wrapup_dirs()

        seen_ids: set[str] = set()
        for wrapup_dir in wrapup_dirs:
            for path in self.safe_glob(wrapup_dir, "*.md"):
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue

                fm, body = self.parse_frontmatter(text)
                name = path.stem
                wrapup_id = f"wrapup:{name}"

                if wrapup_id in seen_ids:
                    continue
                seen_ids.add(wrapup_id)

                props: dict = {
                    "date": fm.get("date", ""),
                    "status": fm.get("status", ""),
                    "related_handoffs": fm.get("related_handoffs", []),
                    "_body": body,
                }
                props.update(BodyParser.parse(body))

                nodes.append(GraphNode(
                    id=wrapup_id,
                    node_type=NodeType.WRAPUP,
                    name=name,
                    description=fm.get("description", "")[:200],
                    source_file=str(path),
                    namespace="wrapups",
                    properties=props,
                ))

                # DOCUMENTS edges to related handoffs
                related = fm.get("related_handoffs", [])
                if isinstance(related, str):
                    related = [related]
                for handoff_ref in related:
                    handoff_stem = Path(handoff_ref).stem if "/" in handoff_ref else handoff_ref
                    edges.append(GraphEdge(
                        source_id=wrapup_id,
                        target_id=f"handoff:{handoff_stem}",
                        edge_type=EdgeType.DOCUMENTS,
                        properties={"handoff_ref": handoff_ref},
                    ))

        return nodes, edges

    def _collect_wrapup_dirs(self) -> list[Path]:
        """Collect wrapup directories from global fallback + project dirs."""
        dirs: list[Path] = []

        global_dir = self.config.wrapups_dir
        if global_dir.exists():
            dirs.append(global_dir)

        for project_dir in self.config.project_dirs:
            project_wrapups = project_dir / ".claude" / "wrapups"
            if project_wrapups.exists():
                dirs.append(project_wrapups)

        return dirs
