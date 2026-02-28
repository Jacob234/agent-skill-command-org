"""Render the ecosystem graph as a self-contained HTML file with Cytoscape.js."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ..models import EcosystemGraph, NodeType


# Location of templates relative to this file
TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates"


def export_html(graph: EcosystemGraph, output_path: Path) -> Path:
    """Render ecosystem-map.html with inlined Cytoscape.js and graph data."""
    # Prepare graph data (strip internal properties)
    graph_dict = graph.to_dict()
    for node in graph_dict["nodes"]:
        node["properties"] = {
            k: v for k, v in node["properties"].items()
            if not k.startswith("_")
        }

    # Collect unique node types that exist in the graph
    node_types = sorted({n["type"] for n in graph_dict["nodes"]})

    # Load Cytoscape.js core (includes built-in cose layout)
    cytoscape_js = _load_js(TEMPLATES_DIR / "cytoscape.min.js")

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
        graph_json=json.dumps(graph_dict, ensure_ascii=False),
        cytoscape_js=cytoscape_js,
    )

    output_file = output_path / "ecosystem-map.html"
    output_file.write_text(html, encoding="utf-8")
    return output_file


def _load_js(path: Path) -> str:
    """Load a JS file, returning empty string if not found."""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"// {path.name} not found"
