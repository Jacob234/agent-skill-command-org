"""Extractor orchestration — runs all extractors and merges results."""

from ..config import Config, BUILTIN_TOOLS
from ..models import EcosystemGraph, GraphNode, NodeType
from .agents import AgentExtractor
from .commands import CommandExtractor
from .plugins import PluginExtractor
from .mcp_servers import MCPServerExtractor
from .hooks import HookExtractor
from .gsd import GSDFrameworkExtractor
from .settings import SettingsExtractor


def extract_all(config: Config) -> EcosystemGraph:
    """Run all extractors and merge into a single EcosystemGraph."""
    graph = EcosystemGraph()

    # Seed built-in tool nodes
    for tool_name in BUILTIN_TOOLS:
        graph.add_node(GraphNode(
            id=f"tool:{tool_name}",
            node_type=NodeType.BUILTIN_TOOL,
            name=tool_name,
        ))

    extractors = [
        AgentExtractor(config),
        CommandExtractor(config),
        PluginExtractor(config),
        MCPServerExtractor(config),
        HookExtractor(config),
        GSDFrameworkExtractor(config),
        SettingsExtractor(config),
    ]

    for extractor in extractors:
        try:
            nodes, edges = extractor.extract()
            for node in nodes:
                # Don't let plugin-sourced nodes overwrite user-level nodes
                if graph.has_node(node.id) and node.properties.get("plugin_source"):
                    existing = graph.get_node(node.id)
                    if existing and not existing.properties.get("plugin_source"):
                        continue
                graph.add_node(node)
            for edge in edges:
                graph.add_edge(edge)
        except Exception as e:
            print(f"  Warning: {extractor.__class__.__name__} failed: {e}")

    # Auto-create missing tool nodes referenced by edges
    _create_missing_tool_nodes(graph)

    # Remove dangling edges (targets that still don't exist, e.g. event strings)
    _prune_dangling_edges(graph)

    return graph


def _create_missing_tool_nodes(graph: EcosystemGraph) -> None:
    """Create BuiltInTool nodes for tools referenced by edges but not yet in graph."""
    missing_tools: set[str] = set()
    for edge in graph.edges:
        for node_id in (edge.source_id, edge.target_id):
            if node_id.startswith("tool:") and not graph.has_node(node_id):
                missing_tools.add(node_id)

    for tool_id in sorted(missing_tools):
        tool_name = tool_id.removeprefix("tool:")
        graph.add_node(GraphNode(
            id=tool_id,
            node_type=NodeType.BUILTIN_TOOL,
            name=tool_name,
            properties={"auto_created": True},
        ))


def _prune_dangling_edges(graph: EcosystemGraph) -> None:
    """Remove edges where source or target node doesn't exist."""
    valid = [
        e for e in graph.edges
        if graph.has_node(e.source_id) and graph.has_node(e.target_id)
    ]
    graph._edges = valid
    graph._edge_keys = {
        (e.source_id, e.target_id, e.edge_type.value) for e in valid
    }
