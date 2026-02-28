"""Extract settings and annotate plugin nodes with enabled status."""

from __future__ import annotations

import json

from ..models import GraphNode, GraphEdge, NodeType
from .base import BaseExtractor


class SettingsExtractor(BaseExtractor):
    """Read settings.json and annotate plugin nodes with enabled/disabled status.

    This extractor doesn't create new nodes — it produces annotations that
    the orchestrator applies to existing Plugin nodes after all extractors run.
    We return empty nodes/edges but store the settings data for later use.
    """

    def extract(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        settings = self._load_settings()
        if not settings:
            return nodes, edges

        # Create a synthetic settings node to capture global config
        enabled_plugins = settings.get("enabledPlugins", {})
        model = settings.get("model", "")

        # We annotate plugin nodes by creating a marker node that holds the data
        # The graph can then be post-processed to apply these annotations
        if enabled_plugins:
            nodes.append(GraphNode(
                id="settings:global",
                node_type=NodeType.BUILTIN_TOOL,  # reuse as config node
                name="Global Settings",
                source_file=str(self.config.settings_file),
                properties={
                    "model": model,
                    "enabled_plugins": {
                        k: v for k, v in enabled_plugins.items()
                    },
                },
            ))

        return nodes, edges

    def _load_settings(self) -> dict:
        """Load settings.json."""
        path = self.config.settings_file
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
