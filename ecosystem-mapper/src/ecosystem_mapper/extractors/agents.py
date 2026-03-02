"""Extract Agent nodes from ~/.claude/agents/*.md files."""

from __future__ import annotations

from ..models import GraphNode, GraphEdge, NodeType, EdgeType
from ..parsers import BodyParser
from .base import BaseExtractor


class AgentExtractor(BaseExtractor):
    """Parse agent definition files into Agent nodes + HAS_TOOLS edges."""

    def extract(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        for path in self.safe_glob(self.config.agents_dir, "*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            fm, body = self.parse_frontmatter(text)
            if not fm:
                continue

            name = fm.get("name", path.stem)
            agent_id = f"agent:{name}"

            # Parse tools — can be comma-separated string or YAML list
            raw_tools = fm.get("tools", "")
            if isinstance(raw_tools, str):
                tools = [t.strip() for t in raw_tools.split(",") if t.strip()]
            elif isinstance(raw_tools, list):
                tools = [str(t).strip() for t in raw_tools]
            else:
                tools = []

            # Categorize agent
            model = fm.get("model", "")
            if tools:
                category = "execution"
            elif model:
                category = "design"
            else:
                category = "utility"

            node = GraphNode(
                id=agent_id,
                node_type=NodeType.AGENT,
                name=name,
                description=fm.get("description", "")[:200],
                source_file=str(path),
                properties={
                    "model": model,
                    "color": fm.get("color", ""),
                    "category": category,
                    "tools": tools,
                },
            )
            nodes.append(node)

            # Create HAS_TOOLS edges
            for tool in tools:
                # Normalize: some tools listed with wildcards like "mcp__*"
                if "*" in tool:
                    continue
                edges.append(GraphEdge(
                    source_id=agent_id,
                    target_id=f"tool:{tool}",
                    edge_type=EdgeType.HAS_TOOLS,
                ))

            # Store body text for cross-reference analysis later
            node.properties["_body"] = body
            node.properties.update(BodyParser.parse(body))

        return nodes, edges
