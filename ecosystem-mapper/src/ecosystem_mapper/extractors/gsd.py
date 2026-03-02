"""Extract GSD workflow and reference nodes from get-shit-done/ directory."""

from __future__ import annotations

from ..models import GraphNode, GraphEdge, NodeType
from ..parsers import BodyParser
from .base import BaseExtractor


class GSDFrameworkExtractor(BaseExtractor):
    """Parse GSD workflows and references into graph nodes with full content."""

    def extract(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        gsd_dir = self.config.gsd_dir
        if not gsd_dir.exists():
            return nodes, edges

        # Workflows
        for path in self.safe_glob(gsd_dir / "workflows", "*.md"):
            node = self._parse_gsd_file(path, NodeType.GSD_WORKFLOW, "gsd-wf")
            if node:
                nodes.append(node)

        # References
        for path in self.safe_glob(gsd_dir / "references", "*.md"):
            node = self._parse_gsd_file(path, NodeType.GSD_REFERENCE, "gsd-ref")
            if node:
                nodes.append(node)

        # Templates
        for path in self.safe_glob(gsd_dir / "templates", "*.md"):
            node = self._parse_gsd_file(path, NodeType.GSD_REFERENCE, "gsd-ref")
            if node:
                node.properties["subtype"] = "template"
                nodes.append(node)

        # Version metadata
        version_file = gsd_dir / "VERSION"
        if version_file.exists():
            try:
                version = version_file.read_text(encoding="utf-8").strip()
                for node in nodes:
                    node.properties["gsd_version"] = version
            except OSError:
                pass

        return nodes, edges

    def _parse_gsd_file(self, path, node_type: NodeType, id_prefix: str) -> GraphNode | None:
        """Read a GSD markdown file and extract content + semantic data."""
        name = path.stem

        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return GraphNode(
                id=f"{id_prefix}:{name}",
                node_type=node_type,
                name=name,
                source_file=str(path),
                namespace="gsd",
            )

        fm, body = self.parse_frontmatter(text)
        description = fm.get("description", "")
        if not description and body:
            # Extract description from first 200 chars of body
            description = body[:200].split("\n")[0].strip()

        # Check for deprecation markers in first 200 chars
        deprecated = False
        first_chunk = (body or text)[:200].lower()
        if "deprecated" in first_chunk or "⚠️" in first_chunk:
            deprecated = True

        props: dict = {
            "_body": body,
            **fm,
        }
        props.update(BodyParser.parse(body))

        if deprecated:
            props["deprecated"] = True

        return GraphNode(
            id=f"{id_prefix}:{name}",
            node_type=node_type,
            name=name,
            description=description[:200],
            source_file=str(path),
            namespace="gsd",
            properties=props,
        )
