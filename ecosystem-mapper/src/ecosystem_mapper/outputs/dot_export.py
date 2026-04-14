"""Export ecosystem graph as a Graphviz DOT file.

Color-codes Skill nodes by the `portability_tier` property set by SkillExtractor
(joined from the hand-curated REGISTRY.yaml). Groups Skill nodes by `domain` using
DOT subgraph clusters so the founder handover diagram reads as "this is what lives
where, and which parts are portable to Cowork."

Non-Skill node types (Agent, MCPServer, BuiltInTool, etc.) are rendered as a single
uncolored cluster per type so the graph stays legible. The focus is Skills; other
nodes are context.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from ..models import EcosystemGraph, EdgeType, GraphNode, NodeType

# Portability tier → fill color (Graphviz named colors)
TIER_COLORS: dict[str, str] = {
    "cowork_ready": "#b7e4b7",  # soft green
    "cowork_with_mcp": "#f5e69a",  # soft yellow
    "needs_port": "#f5c28a",  # soft orange
    "code_only": "#f5a5a5",  # soft red
    "unclassified": "#d9d9d9",  # neutral gray
}

TIER_ORDER = ["cowork_ready", "cowork_with_mcp", "needs_port", "code_only", "unclassified"]

# Non-skill node types → shape
NONSKILL_SHAPES: dict[NodeType, str] = {
    NodeType.AGENT: "hexagon",
    NodeType.MCP_SERVER: "cylinder",
    NodeType.BUILTIN_TOOL: "note",
    NodeType.PLUGIN: "folder",
    NodeType.PLUGIN_SKILL: "component",
    NodeType.HOOK: "cds",
    NodeType.CAPABILITY_ENTRY: "tab",
}

# Edge type → arrow style
EDGE_STYLES: dict[EdgeType, dict[str, str]] = {
    EdgeType.INVOKES: {"color": "#555555", "style": "solid"},
    EdgeType.SPAWNS: {"color": "#8b5a2b", "style": "solid"},
    EdgeType.HAS_TOOLS: {"color": "#aaaaaa", "style": "dashed"},
    EdgeType.PROVIDES: {"color": "#4a90e2", "style": "solid"},
    EdgeType.DELEGATES_TO: {"color": "#7b4dff", "style": "solid"},
    EdgeType.REFERENCES: {"color": "#bbbbbb", "style": "dotted"},
}


def export_dot(graph: EcosystemGraph, output_path: Path) -> Path:
    """Serialize the ecosystem graph to a Graphviz DOT file.

    Skill nodes are grouped by domain cluster and colored by portability tier.
    Non-skill nodes are rendered without clustering.
    """
    lines: list[str] = []
    lines.append("digraph ecosystem {")
    lines.append('  graph [rankdir="LR", fontname="Helvetica", ranksep=1.2, nodesep=0.4, splines=true];')
    lines.append('  node  [fontname="Helvetica", fontsize=10, style="filled,rounded", shape=box];')
    lines.append('  edge  [fontname="Helvetica", fontsize=8];')
    lines.append("")

    # Only include user/workspace/project-scoped skills from SKILL.md files.
    # Command-derived skills (id: "skill:<name>") and plugin skills are out of scope —
    # we exclude them to keep the handover diagram focused on Jacob's IP.
    all_skills = graph.get_nodes_by_type(NodeType.SKILL)
    skills = [n for n in all_skills if n.id.startswith(("skill:user:", "skill:project:", "skill:workspace:"))]
    plugin_skills: list[GraphNode] = []  # suppressed for clarity

    # --- Skill clusters by domain ----------------------------------------------------
    skills_by_domain: dict[str, list[GraphNode]] = defaultdict(list)
    for node in skills:
        domain = str(node.properties.get("domain", "unclassified") or "unclassified")
        skills_by_domain[domain].append(node)

    for domain in sorted(skills_by_domain.keys()):
        cluster_id = _safe_cluster_id("domain", domain)
        lines.append(f"  subgraph {cluster_id} {{")
        lines.append(f'    label="{_escape(domain)}";')
        lines.append('    style="rounded,filled";')
        lines.append('    color="#999999";')
        lines.append('    fillcolor="#f8f8f8";')
        lines.append("    margin=16;")
        for node in sorted(skills_by_domain[domain], key=lambda n: (n.namespace, n.name)):
            lines.append(_render_skill_node(node))
        lines.append("  }")
        lines.append("")

    # --- Legend for portability tiers -----------------------------------------------
    # Render legend as an HTML-like label on a single node to avoid layout conflicts
    # with cluster ranking. A single-node legend is the most robust form.
    legend_rows = "".join(f'<tr><td bgcolor="{TIER_COLORS[tier]}">{_escape(tier)}</td></tr>' for tier in TIER_ORDER)
    legend_label = (
        '<<table border="0" cellborder="1" cellspacing="0" cellpadding="6">'
        '<tr><td bgcolor="#ffffff"><b>Portability tiers</b></td></tr>' + legend_rows + "</table>>"
    )
    lines.append(f"  legend [shape=plaintext, label={legend_label}];")
    lines.append("")

    # --- Edges ----------------------------------------------------------------------
    # Only INVOKES edges between skills we rendered — this keeps the handover diagram
    # focused on "which skill hands off to which" rather than full tool/agent dependency.
    skill_ids = {n.id for n in skills}

    for edge in graph.edges:
        if edge.edge_type != EdgeType.INVOKES:
            continue
        if edge.source_id not in skill_ids or edge.target_id not in skill_ids:
            continue
        style = EDGE_STYLES.get(edge.edge_type, {"color": "#cccccc", "style": "dotted"})
        lines.append(
            f'  "{_escape(edge.source_id)}" -> "{_escape(edge.target_id)}" '
            f'[color="{style["color"]}", style="{style["style"]}"];'
        )

    lines.append("}")
    lines.append("")

    output_file = output_path / "ecosystem-map.dot"
    output_file.write_text("\n".join(lines), encoding="utf-8")
    return output_file


# -----------------------------------------------------------------------------
# Rendering helpers
# -----------------------------------------------------------------------------


def _render_skill_node(node: GraphNode) -> str:
    tier = str(node.properties.get("portability_tier", "unclassified") or "unclassified")
    fill = TIER_COLORS.get(tier, TIER_COLORS["unclassified"])
    scope = node.properties.get("scope", "") or ""
    label_parts = [node.name]
    if scope:
        label_parts.append(f"[{scope}]")
    if not node.properties.get("registry_matched"):
        label_parts.append("(unclassified)")
    label = "\\n".join(_escape(p) for p in label_parts)
    tooltip = _escape(str(node.properties.get("purpose") or node.description or node.name))
    return f'    "{_escape(node.id)}" [label="{label}", fillcolor="{fill}", tooltip="{tooltip}"];'


def _render_nonskill_node(node: GraphNode, fillcolor: str = "#ffffff") -> str:
    shape = NONSKILL_SHAPES.get(node.node_type, "box")
    label = _escape(node.name)
    return f'    "{_escape(node.id)}" [label="{label}", shape={shape}, fillcolor="{fillcolor}"];'


def _safe_cluster_id(prefix: str, value: str) -> str:
    sanitized = "".join(c if c.isalnum() else "_" for c in value)
    return f"cluster_{prefix}_{sanitized}"


def _escape(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace('"', '\\"')
