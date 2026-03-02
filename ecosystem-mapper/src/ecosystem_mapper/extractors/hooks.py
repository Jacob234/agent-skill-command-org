"""Extract Hook nodes from hooks.json files and hookify rule files."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import GraphNode, GraphEdge, NodeType, EdgeType
from .base import BaseExtractor


class HookExtractor(BaseExtractor):
    """Parse hook configurations from plugins and hookify rules."""

    def extract(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        # Plugin hooks from active install paths
        self._extract_plugin_hooks(nodes, edges)

        # Hookify local rules
        self._extract_hookify_rules(nodes, edges)

        return nodes, edges

    def _extract_plugin_hooks(
        self,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
    ) -> None:
        """Parse hooks.json from plugin install paths."""
        active_paths = self._get_active_install_paths()

        for plugin_key, install_path in active_paths.items():
            hooks_file = install_path / "hooks" / "hooks.json"
            if not hooks_file.exists():
                continue

            try:
                data = json.loads(hooks_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            plugin_name = plugin_key.split("@")[0]
            plugin_id = f"plugin:{plugin_key}"
            hooks_config = data.get("hooks", {})

            for event_type, hook_list in hooks_config.items():
                if not isinstance(hook_list, list):
                    continue

                for i, hook_entry in enumerate(hook_list):
                    matcher = hook_entry.get("matcher", "")
                    hook_name = f"{plugin_name}-{event_type}-{i}"
                    hook_id = f"hook:{plugin_name}:{hook_name}"

                    # Extract command path from hooks array
                    hooks_array = hook_entry.get("hooks", [])
                    command_paths = []
                    for h in hooks_array if isinstance(hooks_array, list) else []:
                        cmd = h.get("command", "") if isinstance(h, dict) else ""
                        if cmd:
                            command_paths.append(cmd)

                    nodes.append(GraphNode(
                        id=hook_id,
                        node_type=NodeType.HOOK,
                        name=hook_name,
                        description=data.get("description", ""),
                        source_file=str(hooks_file),
                        properties={
                            "event": event_type,
                            "matcher": matcher,
                            "plugin_source": plugin_key,
                            "timeout": hook_entry.get("timeout", ""),
                            "command_paths": command_paths,
                        },
                    ))

                    # PROVIDES edge from plugin
                    edges.append(GraphEdge(
                        source_id=plugin_id,
                        target_id=hook_id,
                        edge_type=EdgeType.PROVIDES,
                    ))

                    # GUARDS edge to event type
                    edges.append(GraphEdge(
                        source_id=hook_id,
                        target_id=event_type,
                        edge_type=EdgeType.GUARDS,
                        properties={"matcher": matcher},
                    ))

    def _extract_hookify_rules(
        self,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
    ) -> None:
        """Parse hookify.*.local.md rule files."""
        # Look in common project directories and home
        search_dirs = [
            self.config.claude_home,
            Path.cwd(),
        ]

        for search_dir in search_dirs:
            for rule_file in self.safe_glob(search_dir, "hookify.*.local.md"):
                try:
                    text = rule_file.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue

                fm, body = self.parse_frontmatter(text)
                if not fm:
                    continue

                rule_name = fm.get("name", rule_file.stem)
                hook_id = f"hook:hookify:{rule_name}"

                nodes.append(GraphNode(
                    id=hook_id,
                    node_type=NodeType.HOOK,
                    name=rule_name,
                    source_file=str(rule_file),
                    properties={
                        "event": fm.get("event", ""),
                        "action": fm.get("action", ""),
                        "pattern": fm.get("pattern", ""),
                        "source": "hookify",
                    },
                ))

                event = fm.get("event", "")
                if event:
                    edges.append(GraphEdge(
                        source_id=hook_id,
                        target_id=event,
                        edge_type=EdgeType.GUARDS,
                    ))

    def _get_active_install_paths(self) -> dict[str, Path]:
        """Read installed_plugins.json for active paths."""
        path = self.config.installed_plugins_file
        if not path.exists():
            return {}

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

        result = {}
        for plugin_key, versions in data.get("plugins", {}).items():
            if isinstance(versions, list) and versions:
                install_path = Path(versions[0].get("installPath", ""))
                if install_path.exists():
                    result[plugin_key] = install_path
        return result
