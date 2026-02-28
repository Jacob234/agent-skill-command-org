"""Export ecosystem graph as JSON file."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import EcosystemGraph


def export_json(graph: EcosystemGraph, output_path: Path) -> Path:
    """Serialize the ecosystem graph to a JSON file.

    Strips internal properties (prefixed with _) before export.
    """
    data = graph.to_dict()

    # Clean internal properties from nodes
    for node in data["nodes"]:
        node["properties"] = {
            k: v for k, v in node["properties"].items()
            if not k.startswith("_")
        }

    output_file = output_path / "ecosystem-graph.json"
    output_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_file
