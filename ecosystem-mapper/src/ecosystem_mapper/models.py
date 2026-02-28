"""Graph data model: nodes, edges, and the ecosystem graph container."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeType(str, Enum):
    AGENT = "Agent"
    SKILL = "Skill"
    PLUGIN_SKILL = "PluginSkill"
    PLUGIN = "Plugin"
    MCP_SERVER = "MCPServer"
    HOOK = "Hook"
    GSD_WORKFLOW = "GSDWorkflow"
    GSD_REFERENCE = "GSDReference"
    BUILTIN_TOOL = "BuiltInTool"


class EdgeType(str, Enum):
    SPAWNS = "SPAWNS"
    INVOKES = "INVOKES"
    HAS_TOOLS = "HAS_TOOLS"
    PROVIDES = "PROVIDES"
    GUARDS = "GUARDS"
    REFERENCES = "REFERENCES"
    SUGGESTS_NEXT = "SUGGESTS_NEXT"
    DELEGATES_TO = "DELEGATES_TO"
    ALIASES = "ALIASES"


@dataclass
class GraphNode:
    id: str
    node_type: NodeType
    name: str
    description: str = ""
    source_file: str = ""
    namespace: str = ""
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.node_type.value,
            "name": self.name,
            "description": self.description,
            "source_file": self.source_file,
            "namespace": self.namespace,
            "properties": self.properties,
        }


@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    edge_type: EdgeType
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "type": self.edge_type.value,
            "properties": self.properties,
        }


class EcosystemGraph:
    """Container for the full ecosystem graph with node/edge management."""

    def __init__(self):
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._edge_keys: set[tuple[str, str, str]] = set()

    def add_node(self, node: GraphNode) -> None:
        self._nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        key = (edge.source_id, edge.target_id, edge.edge_type.value)
        if key not in self._edge_keys:
            self._edge_keys.add(key)
            self._edges.append(edge)

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def get_node(self, node_id: str) -> GraphNode | None:
        return self._nodes.get(node_id)

    def get_nodes_by_type(self, node_type: NodeType) -> list[GraphNode]:
        return [n for n in self._nodes.values() if n.node_type == node_type]

    def get_edges_by_type(self, edge_type: EdgeType) -> list[GraphEdge]:
        return [e for e in self._edges if e.edge_type == edge_type]

    @property
    def nodes(self) -> list[GraphNode]:
        return list(self._nodes.values())

    @property
    def edges(self) -> list[GraphEdge]:
        return list(self._edges)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges],
            "stats": {
                "total_nodes": len(self._nodes),
                "total_edges": len(self._edges),
                "nodes_by_type": {
                    t.value: len(self.get_nodes_by_type(t))
                    for t in NodeType
                    if self.get_nodes_by_type(t)
                },
                "edges_by_type": {
                    t.value: len(self.get_edges_by_type(t))
                    for t in EdgeType
                    if self.get_edges_by_type(t)
                },
            },
        }
