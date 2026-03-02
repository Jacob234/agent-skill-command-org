"""Render the ecosystem graph as a self-contained HTML file with Cytoscape.js."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from ..models import EcosystemGraph, NodeType
from .constants import EXPORT_BLOCKLIST


# Location of templates relative to this file
TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates"

# Properties too large or complex for the interactive HTML visualization.
# These are still available in the JSON export.
_VIZ_BLOCKLIST = EXPORT_BLOCKLIST | {"semantic.xml_sections"}


def export_html(graph: EcosystemGraph, output_path: Path) -> Path:
    """Render ecosystem-map.html with inlined Cytoscape.js and graph data."""
    # Prepare graph data — strip blocklisted + oversized properties for viz
    graph_dict = graph.to_dict()
    for node in graph_dict["nodes"]:
        node["properties"] = _slim_properties(node["properties"])

    # Collect unique node types that exist in the graph
    node_types = sorted({n["type"] for n in graph_dict["nodes"]})

    # Load Cytoscape.js core (includes built-in cose layout)
    cytoscape_js = _load_js(TEMPLATES_DIR / "cytoscape.min.js")

    # Serialize graph JSON and escape for safe <script> embedding
    graph_json = json.dumps(graph_dict, ensure_ascii=False)
    graph_json = _escape_for_script_tag(graph_json)

    # Render template
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,  # We handle escaping in JS via textContent
    )
    template = env.get_template("visualization.html")

    html = template.render(
        stats=graph_dict["stats"],
        node_types=node_types,
        node_types_json=json.dumps(node_types),
        graph_json=graph_json,
        cytoscape_js=cytoscape_js,
    )

    output_file = output_path / "ecosystem-map.html"
    output_file.write_text(html, encoding="utf-8")
    return output_file


def _slim_properties(props: dict[str, Any]) -> dict[str, Any]:
    """Filter and truncate properties for the visualization.

    - Removes blocklisted keys (_body, semantic.xml_sections)
    - Truncates long string values to 300 chars
    - Simplifies heading_structure to title list
    """
    result: dict[str, Any] = {}
    for k, v in props.items():
        if k in _VIZ_BLOCKLIST:
            continue

        # Simplify heading_structure: [{level, title}, ...] → ["## Title", ...]
        if k == "semantic.heading_structure" and isinstance(v, list):
            result[k] = [
                f"{'#' * entry.get('level', 2)} {entry.get('title', '')}"
                for entry in v[:20]  # cap at 20 headings
            ]
            continue

        # Truncate long strings
        if isinstance(v, str) and len(v) > 300:
            result[k] = v[:300] + "..."
            continue

        # Truncate long lists
        if isinstance(v, list) and len(v) > 20:
            result[k] = v[:20] + ["..."]
            continue

        result[k] = v

    return result


def _escape_for_script_tag(json_str: str) -> str:
    """Escape sequences that would break out of a <script> tag.

    The HTML parser processes </script> before the JS parser sees it,
    so we must escape </ sequences in embedded JSON.
    """
    return json_str.replace("</", r"<\/")


def _load_js(path: Path) -> str:
    """Load a JS file, returning empty string if not found."""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"// {path.name} not found"
