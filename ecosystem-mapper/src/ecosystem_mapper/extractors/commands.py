"""Extract Skill nodes from ~/.claude/commands/**/*.md files."""

from __future__ import annotations

from pathlib import Path

from ..models import GraphNode, GraphEdge, NodeType, EdgeType
from ..parsers import BodyParser
from .base import BaseExtractor


class CommandExtractor(BaseExtractor):
    """Parse command/skill definition files into Skill nodes + INVOKES edges."""

    def extract(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        # Top-level commands + nested directory commands
        for path in self._find_command_files():
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            fm, body = self.parse_frontmatter(text)
            if not fm:
                continue

            name = fm.get("name", path.stem)
            namespace = self._derive_namespace(path)
            skill_id = f"skill:{namespace}:{name}" if namespace else f"skill:{name}"

            # Parse allowed-tools — YAML list
            allowed_tools = fm.get("allowed-tools", [])
            if isinstance(allowed_tools, str):
                allowed_tools = [t.strip() for t in allowed_tools.split(",") if t.strip()]
            elif not isinstance(allowed_tools, list):
                allowed_tools = []

            node = GraphNode(
                id=skill_id,
                node_type=NodeType.SKILL,
                name=name,
                description=fm.get("description", "")[:200],
                source_file=str(path),
                namespace=namespace,
                properties={
                    "argument_hint": fm.get("argument-hint", ""),
                    "allowed_tools": [str(t) for t in allowed_tools],
                },
            )
            nodes.append(node)

            # Create INVOKES edges for each allowed tool
            for tool in allowed_tools:
                tool_str = str(tool).strip()
                if tool_str:
                    edges.append(GraphEdge(
                        source_id=skill_id,
                        target_id=f"tool:{tool_str}",
                        edge_type=EdgeType.INVOKES,
                    ))

            # Store body for cross-reference analysis
            node.properties["_body"] = body
            node.properties.update(BodyParser.parse(body))

        return nodes, edges

    def _find_command_files(self) -> list[Path]:
        """Find all .md files in commands dir and its subdirectories."""
        cmd_dir = self.config.commands_dir
        if not cmd_dir.exists():
            return []
        return sorted(cmd_dir.rglob("*.md"))

    def _derive_namespace(self, path: Path) -> str:
        """Derive namespace from subdirectory relative to commands/."""
        try:
            relative = path.relative_to(self.config.commands_dir)
            parts = relative.parts[:-1]  # everything except filename
            return "/".join(parts) if parts else ""
        except ValueError:
            return ""
