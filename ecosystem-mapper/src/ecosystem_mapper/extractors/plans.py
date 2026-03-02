"""Extract Plan nodes from ~/.claude/plans/ directory."""

from __future__ import annotations

import re

from ..models import GraphNode, GraphEdge, NodeType
from ..parsers import BodyParser
from .base import BaseExtractor


class PlanExtractor(BaseExtractor):
    """Parse plan markdown files into Plan nodes."""

    def extract(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        plans_dir = self.config.plans_dir
        if not plans_dir.exists():
            return nodes, edges

        for path in self.safe_glob(plans_dir, "*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            fm, body = self.parse_frontmatter(text)
            name = path.stem

            # Plans often lack frontmatter — extract title from first heading
            description = fm.get("description", "")
            if not description and body:
                heading_match = re.match(r"^#\s+(.+)", body.strip())
                if heading_match:
                    description = heading_match.group(1).strip()

            props: dict = {
                "_body": body,
                **{k: v for k, v in fm.items() if k != "description"},
            }
            props.update(BodyParser.parse(body))

            nodes.append(GraphNode(
                id=f"plan:{name}",
                node_type=NodeType.PLAN,
                name=name,
                description=description[:200],
                source_file=str(path),
                namespace="plans",
                properties=props,
            ))

        return nodes, edges
