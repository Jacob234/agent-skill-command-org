"""Detect cross-references between ecosystem components.

Scans node body text for:
- Task() spawn patterns → SPAWNS edges
- @file references → REFERENCES edges
- <offer_next> suggestions → SUGGESTS_NEXT edges
- Agent delegation mentions → DELEGATES_TO edges
- CAPABILITIES.md alias pairs → ALIASES edges
"""

from __future__ import annotations

import re
from pathlib import Path

from ..config import Config
from ..models import EcosystemGraph, GraphEdge, EdgeType, NodeType


def analyze_cross_references(graph: EcosystemGraph, config: Config) -> None:
    """Analyze all nodes for cross-references and add edges to the graph."""
    _detect_task_spawns(graph)
    _detect_file_references(graph)
    _detect_offer_next(graph)
    _detect_agent_delegation(graph)
    _detect_aliases(graph, config)


# Pattern for Task(subagent_type="agent-name") or subagent_type: "agent-name"
_SPAWN_PATTERN = re.compile(
    r'subagent_type\s*[=:]\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# Pattern for @~/.claude/get-shit-done/... or @.planning/...
_FILE_REF_PATTERN = re.compile(
    r'@(~?/\.claude/get-shit-done/(?:workflows|references|templates)/[^\s)]+\.md)'
    r'|@(\.planning/[^\s)]+)',
)

# Pattern for /gsd:command-name or /command-name in offer_next blocks
_COMMAND_REF_PATTERN = re.compile(r'/(\w[\w:-]*)')


def _detect_task_spawns(graph: EcosystemGraph) -> None:
    """Find Task() spawn patterns in skill and agent bodies."""
    # Build agent name → id lookup
    agent_ids = {
        node.name: node.id
        for node in graph.get_nodes_by_type(NodeType.AGENT)
    }

    for node in graph.nodes:
        body = node.properties.get("_body", "")
        if not body:
            continue

        for match in _SPAWN_PATTERN.finditer(body):
            agent_name = match.group(1)
            target_id = agent_ids.get(agent_name)
            if target_id and target_id != node.id:
                graph.add_edge(GraphEdge(
                    source_id=node.id,
                    target_id=target_id,
                    edge_type=EdgeType.SPAWNS,
                ))


def _detect_file_references(graph: EcosystemGraph) -> None:
    """Find @file references to GSD workflows/references."""
    # Build filename → node id lookup
    gsd_ids: dict[str, str] = {}
    for node in graph.nodes:
        if node.node_type in (NodeType.GSD_WORKFLOW, NodeType.GSD_REFERENCE):
            # Map both full path and just filename
            gsd_ids[node.name] = node.id
            if node.source_file:
                gsd_ids[Path(node.source_file).name] = node.id

    for node in graph.nodes:
        body = node.properties.get("_body", "")
        if not body:
            continue

        for match in _FILE_REF_PATTERN.finditer(body):
            ref_path = match.group(1) or match.group(2)
            if not ref_path:
                continue

            # Extract filename from path
            ref_name = Path(ref_path).stem
            target_id = gsd_ids.get(ref_name) or gsd_ids.get(Path(ref_path).name)
            if target_id and target_id != node.id:
                graph.add_edge(GraphEdge(
                    source_id=node.id,
                    target_id=target_id,
                    edge_type=EdgeType.REFERENCES,
                    properties={"ref_path": ref_path},
                ))


def _detect_offer_next(graph: EcosystemGraph) -> None:
    """Parse <offer_next> sections for skill suggestions."""
    # Build skill name → id lookup (including namespace:name patterns)
    skill_ids: dict[str, str] = {}
    for node in graph.nodes:
        if node.node_type in (NodeType.SKILL, NodeType.PLUGIN_SKILL):
            skill_ids[node.name] = node.id
            # Also map namespace:name
            if node.namespace:
                skill_ids[f"{node.namespace}:{node.name}"] = node.id

    offer_pattern = re.compile(
        r'<offer_next>(.*?)</offer_next>',
        re.DOTALL,
    )

    for node in graph.nodes:
        body = node.properties.get("_body", "")
        if not body:
            continue

        for block_match in offer_pattern.finditer(body):
            block = block_match.group(1)
            for cmd_match in _COMMAND_REF_PATTERN.finditer(block):
                cmd_name = cmd_match.group(1)
                # Try exact match, then with gsd: prefix variations
                target_id = (
                    skill_ids.get(cmd_name)
                    or skill_ids.get(f"gsd:{cmd_name}")
                    or skill_ids.get(cmd_name.replace("gsd:", ""))
                )
                if target_id and target_id != node.id:
                    graph.add_edge(GraphEdge(
                        source_id=node.id,
                        target_id=target_id,
                        edge_type=EdgeType.SUGGESTS_NEXT,
                    ))


def _detect_agent_delegation(graph: EcosystemGraph) -> None:
    """Detect agent-to-agent delegation references in body text."""
    agent_nodes = graph.get_nodes_by_type(NodeType.AGENT)
    agent_names = {node.name: node.id for node in agent_nodes}

    # Coordination keywords that indicate delegation context
    delegation_context = re.compile(
        r'(spawn|delegate|invoke|coordinate|orchestrat|specialist|launch)',
        re.IGNORECASE,
    )

    for node in agent_nodes:
        body = node.properties.get("_body", "")
        if not body or not delegation_context.search(body):
            continue

        for other_name, other_id in agent_names.items():
            if other_id == node.id:
                continue
            # Look for agent name as a word boundary match
            if re.search(rf'\b{re.escape(other_name)}\b', body):
                graph.add_edge(GraphEdge(
                    source_id=node.id,
                    target_id=other_id,
                    edge_type=EdgeType.DELEGATES_TO,
                ))


def _detect_aliases(graph: EcosystemGraph, config: Config) -> None:
    """Parse CAPABILITIES.md appendix for alias pairs."""
    cap_file = config.capabilities_file
    if not cap_file.exists():
        return

    try:
        text = cap_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return

    # Build skill lookup
    skill_ids: dict[str, str] = {}
    for node in graph.nodes:
        if node.node_type in (NodeType.SKILL, NodeType.PLUGIN_SKILL):
            skill_ids[node.name] = node.id

    # Look for alias table rows: | /alias | /canonical | ... |
    alias_pattern = re.compile(r'\|\s*/(\S+)\s*\|\s*/(\S+)\s*\|')
    for match in alias_pattern.finditer(text):
        alias_name = match.group(1)
        canonical_name = match.group(2)
        alias_id = skill_ids.get(alias_name)
        canonical_id = skill_ids.get(canonical_name)
        if alias_id and canonical_id and alias_id != canonical_id:
            graph.add_edge(GraphEdge(
                source_id=alias_id,
                target_id=canonical_id,
                edge_type=EdgeType.ALIASES,
            ))
