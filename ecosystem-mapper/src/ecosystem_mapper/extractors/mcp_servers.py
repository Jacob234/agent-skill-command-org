"""Extract MCPServer nodes from .mcp.json files in plugin caches."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import GraphNode, GraphEdge, NodeType, EdgeType
from .base import BaseExtractor


class MCPServerExtractor(BaseExtractor):
    """Parse .mcp.json files from active plugin install paths."""

    def extract(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        # Get active install paths from registry
        active_paths = self._get_active_install_paths()

        for plugin_key, install_path in active_paths.items():
            mcp_file = install_path / ".mcp.json"
            if not mcp_file.exists():
                continue

            try:
                data = json.loads(mcp_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            plugin_id = f"plugin:{plugin_key}"
            servers = self._normalize_mcp_data(data)

            for server_name, server_config in servers.items():
                mcp_id = f"mcp:{server_name}"

                # Determine protocol
                if "url" in server_config:
                    protocol = "http"
                    url = server_config["url"]
                elif "command" in server_config:
                    protocol = "command"
                    url = f"{server_config['command']} {' '.join(server_config.get('args', []))}"
                else:
                    protocol = "unknown"
                    url = ""

                nodes.append(GraphNode(
                    id=mcp_id,
                    node_type=NodeType.MCP_SERVER,
                    name=server_name,
                    source_file=str(mcp_file),
                    properties={
                        "protocol": protocol,
                        "url": url,
                        "plugin_source": plugin_key,
                    },
                ))
                edges.append(GraphEdge(
                    source_id=plugin_id,
                    target_id=mcp_id,
                    edge_type=EdgeType.PROVIDES,
                ))

        return nodes, edges

    def _get_active_install_paths(self) -> dict[str, Path]:
        """Read installed_plugins.json to get active plugin paths."""
        path = self.config.installed_plugins_file
        if not path.exists():
            return {}

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

        result = {}
        plugins = data.get("plugins", {})
        for plugin_key, versions in plugins.items():
            if isinstance(versions, list) and versions:
                install_path = Path(versions[0].get("installPath", ""))
                if install_path.exists():
                    result[plugin_key] = install_path

        return result

    @staticmethod
    def _normalize_mcp_data(data: dict) -> dict:
        """Handle both MCP JSON schemas.

        Schema A: { "serverName": { "command": ..., "args": [...] } }
        Schema B: { "mcpServers": { "name": { "type": "http", "url": ... } } }
        """
        if "mcpServers" in data:
            return data["mcpServers"]
        # Schema A: top-level keys are server configs (skip meta keys)
        return {
            k: v for k, v in data.items()
            if isinstance(v, dict) and ("command" in v or "url" in v or "type" in v)
        }
