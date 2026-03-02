"""Detect cross-references between ecosystem components.

Scans node body text for:
- Task() spawn patterns → SPAWNS edges
- @file references → REFERENCES edges
- <offer_next> suggestions → SUGGESTS_NEXT edges
- Agent delegation mentions → DELEGATES_TO edges
- CAPABILITIES.md alias pairs → ALIASES edges
- Capability enrichment → DOCUMENTS edges
- Handoff/wrapup/plan references → DOCUMENTS edges
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
    _detect_capability_enrichment(graph)
    _detect_handoff_references(graph)


def _extract_context(body: str, match_start: int, match_end: int, chars: int = 50) -> str:
    """Extract surrounding context around a regex match."""
    start = max(0, match_start - chars)
    end = min(len(body), match_end + chars)
    snippet = body[start:end].replace("\n", " ").strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(body):
        snippet = snippet + "..."
    return snippet


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
                context = _extract_context(body, match.start(), match.end())
                graph.add_edge(GraphEdge(
                    source_id=node.id,
                    target_id=target_id,
                    edge_type=EdgeType.SPAWNS,
                    properties={"context": context},
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
                context = _extract_context(body, match.start(), match.end())
                graph.add_edge(GraphEdge(
                    source_id=node.id,
                    target_id=target_id,
                    edge_type=EdgeType.REFERENCES,
                    properties={"ref_path": ref_path, "context": context},
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
            context = _extract_context(body, block_match.start(), block_match.end())
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
                        properties={"context": context},
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
            name_match = re.search(rf'\b{re.escape(other_name)}\b', body)
            if name_match:
                context = _extract_context(body, name_match.start(), name_match.end())
                graph.add_edge(GraphEdge(
                    source_id=node.id,
                    target_id=other_id,
                    edge_type=EdgeType.DELEGATES_TO,
                    properties={"context": context},
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


def _detect_capability_enrichment(graph: EcosystemGraph) -> None:
    """Match CAPABILITY_ENTRY nodes to Skill/Agent/MCP nodes by name.

    Enriches matched nodes with when_to_use and cap_description.
    Creates DOCUMENTS edges from capability entries to matched nodes.
    """
    cap_nodes = graph.get_nodes_by_type(NodeType.CAPABILITY_ENTRY)
    if not cap_nodes:
        return

    # Build lookup of existing component names → node ids
    component_lookup: dict[str, str] = {}
    for node in graph.nodes:
        if node.node_type in (
            NodeType.SKILL, NodeType.PLUGIN_SKILL, NodeType.AGENT,
            NodeType.MCP_SERVER, NodeType.GSD_WORKFLOW,
        ):
            component_lookup[node.name] = node.id
            # Also index without namespace prefix
            if ":" in node.name:
                short_name = node.name.split(":")[-1]
                component_lookup.setdefault(short_name, node.id)

    for cap_node in cap_nodes:
        command_ref = cap_node.properties.get("command_ref", "")
        if not command_ref:
            continue

        # Try matching command_ref to existing components
        target_id = (
            component_lookup.get(command_ref)
            or component_lookup.get(command_ref.replace("gsd:", ""))
            or component_lookup.get(f"gsd:{command_ref}")
        )

        if target_id and target_id != cap_node.id:
            # Enrich the matched node
            target_node = graph.get_node(target_id)
            if target_node:
                when_to_use = cap_node.properties.get("when_to_use", "")
                cap_desc = cap_node.properties.get("cap_description", "")
                if when_to_use:
                    target_node.properties["when_to_use"] = when_to_use
                if cap_desc:
                    target_node.properties["cap_description"] = cap_desc

            graph.add_edge(GraphEdge(
                source_id=cap_node.id,
                target_id=target_id,
                edge_type=EdgeType.DOCUMENTS,
                properties={"match_type": "capability_enrichment"},
            ))


def _detect_handoff_references(graph: EcosystemGraph) -> None:
    """Scan HANDOFF/WRAPUP/PLAN body text for mentions of known components.

    Creates DOCUMENTS edges with match_type: "name_mention".
    """
    # Collect all searchable component names → ids
    component_names: dict[str, str] = {}
    for node in graph.nodes:
        if node.node_type in (
            NodeType.SKILL, NodeType.PLUGIN_SKILL, NodeType.AGENT,
            NodeType.GSD_WORKFLOW, NodeType.GSD_REFERENCE,
        ):
            # Only index names that are reasonably specific (3+ chars)
            if len(node.name) >= 3:
                component_names[node.name] = node.id

    # Scan handoff/wrapup/plan bodies
    doc_types = (NodeType.HANDOFF, NodeType.WRAPUP)
    for node in graph.nodes:
        if node.node_type not in doc_types:
            continue

        body = node.properties.get("_body", "")
        if not body:
            continue

        for comp_name, comp_id in component_names.items():
            if comp_id == node.id:
                continue
            # Word boundary match to avoid partial matches
            match = re.search(rf'\b{re.escape(comp_name)}\b', body)
            if match:
                context = _extract_context(body, match.start(), match.end())
                graph.add_edge(GraphEdge(
                    source_id=node.id,
                    target_id=comp_id,
                    edge_type=EdgeType.DOCUMENTS,
                    properties={
                        "match_type": "name_mention",
                        "context": context,
                    },
                ))
