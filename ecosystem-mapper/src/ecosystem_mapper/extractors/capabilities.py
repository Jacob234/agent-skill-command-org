"""Extract CapabilityEntry nodes from CAPABILITIES.md markdown tables."""

from __future__ import annotations

import re

from ..models import GraphNode, GraphEdge, NodeType
from .base import BaseExtractor


# Match table rows like: | /command | Description text | When to use |
_TABLE_ROW_PATTERN = re.compile(
    r"\|\s*/(\S+)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|"
)

# Match markdown headings for section tracking
_HEADING_PATTERN = re.compile(r"^(#{1,4})\s+(.+)", re.MULTILINE)


class CapabilitiesExtractor(BaseExtractor):
    """Parse CAPABILITIES.md tables into CapabilityEntry nodes."""

    def extract(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        cap_file = self.config.capabilities_file
        if not cap_file.exists():
            return nodes, edges

        try:
            text = cap_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return nodes, edges

        current_section = ""
        seen_ids: set[str] = set()

        for line in text.split("\n"):
            # Track current section heading
            heading_match = _HEADING_PATTERN.match(line)
            if heading_match:
                current_section = heading_match.group(2).strip()
                continue

            # Parse table rows
            row_match = _TABLE_ROW_PATTERN.match(line)
            if not row_match:
                continue

            command_ref = row_match.group(1).strip()
            cap_description = row_match.group(2).strip()
            when_to_use = row_match.group(3).strip()

            # Skip header rows (e.g., "Command" | "Description" | ...)
            if command_ref.lower() in ("command", "name", "skill", "---"):
                continue
            if cap_description.startswith("---"):
                continue

            cap_id = f"capability:{command_ref}"
            if cap_id in seen_ids:
                continue
            seen_ids.add(cap_id)

            nodes.append(GraphNode(
                id=cap_id,
                node_type=NodeType.CAPABILITY_ENTRY,
                name=command_ref,
                description=cap_description[:200],
                source_file=str(cap_file),
                namespace="capabilities",
                properties={
                    "command_ref": command_ref,
                    "cap_description": cap_description,
                    "when_to_use": when_to_use,
                    "section": current_section,
                },
            ))

        return nodes, edges
