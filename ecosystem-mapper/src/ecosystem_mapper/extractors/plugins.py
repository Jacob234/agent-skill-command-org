"""Extract Plugin and PluginSkill nodes from installed_plugins.json + plugin caches."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import GraphNode, GraphEdge, NodeType, EdgeType
from .base import BaseExtractor


class PluginExtractor(BaseExtractor):
    """Parse plugin registry and walk plugin cache for skills/agents/commands."""

    def extract(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        registry = self._load_registry()
        if not registry:
            return nodes, edges

        plugins_data = registry.get("plugins", {})

        for plugin_key, versions in plugins_data.items():
            # plugin_key format: "name@marketplace"
            if not isinstance(versions, list) or not versions:
                continue

            # Use the first (active) version entry
            entry = versions[0]
            install_path = Path(entry.get("installPath", ""))

            plugin_id = f"plugin:{plugin_key}"
            node = GraphNode(
                id=plugin_id,
                node_type=NodeType.PLUGIN,
                name=plugin_key.split("@")[0],
                source_file=str(install_path),
                namespace=plugin_key.split("@")[-1] if "@" in plugin_key else "",
                properties={
                    "scope": entry.get("scope", ""),
                    "version": entry.get("version", ""),
                    "marketplace": plugin_key.split("@")[-1] if "@" in plugin_key else "",
                    "full_key": plugin_key,
                },
            )
            nodes.append(node)

            # Walk plugin cache for skills, commands, agents
            if install_path.exists():
                self._scan_plugin_skills(install_path, plugin_id, plugin_key, nodes, edges)
                self._scan_plugin_commands(install_path, plugin_id, plugin_key, nodes, edges)
                self._scan_plugin_agents(install_path, plugin_id, plugin_key, nodes, edges)

        return nodes, edges

    def _load_registry(self) -> dict:
        """Load installed_plugins.json."""
        path = self.config.installed_plugins_file
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _scan_plugin_skills(
        self,
        install_path: Path,
        plugin_id: str,
        plugin_key: str,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
    ) -> None:
        """Find SKILL.md files in plugin's skills/ directory."""
        skills_dir = install_path / "skills"
        if not skills_dir.exists():
            return

        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                text = skill_md.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            fm, body = self.parse_frontmatter(text)
            plugin_name = plugin_key.split("@")[0]
            skill_name = fm.get("name", skill_dir.name)
            skill_id = f"plugin-skill:{plugin_name}:{skill_name}"

            nodes.append(GraphNode(
                id=skill_id,
                node_type=NodeType.PLUGIN_SKILL,
                name=skill_name,
                description=fm.get("description", "")[:200],
                source_file=str(skill_md),
                namespace=plugin_name,
                properties={
                    "plugin_source": plugin_key,
                    "_body": body,
                },
            ))
            edges.append(GraphEdge(
                source_id=plugin_id,
                target_id=skill_id,
                edge_type=EdgeType.PROVIDES,
            ))

    def _scan_plugin_commands(
        self,
        install_path: Path,
        plugin_id: str,
        plugin_key: str,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
    ) -> None:
        """Find .md command files in plugin's commands/ directory."""
        cmd_dir = install_path / "commands"
        if not cmd_dir.exists():
            return

        plugin_name = plugin_key.split("@")[0]
        for md_path in sorted(cmd_dir.rglob("*.md")):
            try:
                text = md_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            fm, body = self.parse_frontmatter(text)
            if not fm:
                continue

            cmd_name = fm.get("name", md_path.stem)
            skill_id = f"plugin-skill:{plugin_name}:{cmd_name}"

            # Skip if already created from skills/ scan
            nodes.append(GraphNode(
                id=skill_id,
                node_type=NodeType.PLUGIN_SKILL,
                name=cmd_name,
                description=fm.get("description", "")[:200],
                source_file=str(md_path),
                namespace=plugin_name,
                properties={
                    "plugin_source": plugin_key,
                    "allowed_tools": fm.get("allowed-tools", []),
                    "_body": body,
                },
            ))
            edges.append(GraphEdge(
                source_id=plugin_id,
                target_id=skill_id,
                edge_type=EdgeType.PROVIDES,
            ))

    def _scan_plugin_agents(
        self,
        install_path: Path,
        plugin_id: str,
        plugin_key: str,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
    ) -> None:
        """Find agent .md files in plugin's agents/ directory."""
        agents_dir = install_path / "agents"
        if not agents_dir.exists():
            return

        for md_path in sorted(agents_dir.glob("*.md")):
            try:
                text = md_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            fm, body = self.parse_frontmatter(text)
            if not fm:
                continue

            agent_name = fm.get("name", md_path.stem)
            agent_id = f"agent:{agent_name}"

            nodes.append(GraphNode(
                id=agent_id,
                node_type=NodeType.AGENT,
                name=agent_name,
                description=fm.get("description", "")[:200],
                source_file=str(md_path),
                properties={
                    "plugin_source": plugin_key,
                    "model": fm.get("model", ""),
                    "_body": body,
                },
            ))
            edges.append(GraphEdge(
                source_id=plugin_id,
                target_id=agent_id,
                edge_type=EdgeType.PROVIDES,
            ))
