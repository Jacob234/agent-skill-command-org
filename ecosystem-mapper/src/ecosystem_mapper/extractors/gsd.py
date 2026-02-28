"""Extract GSD workflow and reference nodes from get-shit-done/ directory."""

from __future__ import annotations

from ..models import GraphNode, GraphEdge, NodeType
from .base import BaseExtractor


class GSDFrameworkExtractor(BaseExtractor):
    """Parse GSD workflows and references into graph nodes."""

    def extract(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        gsd_dir = self.config.gsd_dir
        if not gsd_dir.exists():
            return nodes, edges

        # Workflows
        for path in self.safe_glob(gsd_dir / "workflows", "*.md"):
            name = path.stem
            nodes.append(GraphNode(
                id=f"gsd-wf:{name}",
                node_type=NodeType.GSD_WORKFLOW,
                name=name,
                source_file=str(path),
                namespace="gsd",
            ))

        # References
        for path in self.safe_glob(gsd_dir / "references", "*.md"):
            name = path.stem
            nodes.append(GraphNode(
                id=f"gsd-ref:{name}",
                node_type=NodeType.GSD_REFERENCE,
                name=name,
                source_file=str(path),
                namespace="gsd",
            ))

        # Templates
        for path in self.safe_glob(gsd_dir / "templates", "*.md"):
            name = path.stem
            nodes.append(GraphNode(
                id=f"gsd-ref:{name}",
                node_type=NodeType.GSD_REFERENCE,
                name=name,
                source_file=str(path),
                namespace="gsd",
                properties={"subtype": "template"},
            ))

        # Version metadata
        version_file = gsd_dir / "VERSION"
        if version_file.exists():
            try:
                version = version_file.read_text(encoding="utf-8").strip()
                # Attach to all GSD nodes as metadata
                for node in nodes:
                    node.properties["gsd_version"] = version
            except OSError:
                pass

        return nodes, edges
