"""Extract semantic structure from markdown body text.

Produces a dict of ``semantic.*`` prefixed keys that survive the export
blocklist (which only strips ``_body``).
"""

from __future__ import annotations

import re


# Match XML-tagged sections: <tag>content</tag> or <tag name="x">content</tag>
_XML_SECTION_PATTERN = re.compile(
    r"<(\w+)(?:\s+name=[\"']([^\"']+)[\"'])?\s*>"
    r"(.*?)"
    r"</\1>",
    re.DOTALL,
)

# Match @file references to .claude paths and .planning paths
_AT_FILE_PATTERN = re.compile(
    r"@(~?/\.claude/[^\s)\"']+)"
    r"|@(\.planning/[^\s)\"']+)"
)

# Match markdown headings
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)", re.MULTILINE)


class BodyParser:
    """Extract semantic structure from a markdown body string."""

    @staticmethod
    def parse(body: str) -> dict:
        """Parse body text and return ``semantic.*`` keyed properties.

        Returns a dict with keys like:
        - ``semantic.xml_sections``: dict of tag -> content mappings
        - ``semantic.at_file_refs``: deduplicated list of @-file references
        - ``semantic.heading_structure``: list of {level, title} dicts
        """
        if not body or not body.strip():
            return {}

        result: dict = {}

        xml_sections = _extract_xml_sections(body)
        if xml_sections:
            result["semantic.xml_sections"] = xml_sections

        at_refs = _extract_at_file_refs(body)
        if at_refs:
            result["semantic.at_file_refs"] = at_refs

        headings = _extract_heading_structure(body)
        if headings:
            result["semantic.heading_structure"] = headings

        return result


def _extract_xml_sections(body: str) -> dict[str, str]:
    """Extract XML-tagged sections with dot-notation for named attributes.

    ``<step name="load">content</step>`` -> ``{"step.load": "content"}``
    ``<overview>content</overview>`` -> ``{"overview": "content"}``
    """
    sections: dict[str, str] = {}

    for match in _XML_SECTION_PATTERN.finditer(body):
        tag = match.group(1)
        name_attr = match.group(2)
        content = match.group(3).strip()

        if name_attr:
            key = f"{tag}.{name_attr}"
        else:
            key = tag

        # If we already have this key, append (handles repeated tags)
        if key in sections:
            sections[key] += "\n\n" + content
        else:
            sections[key] = content

    return sections


def _extract_at_file_refs(body: str) -> list[str]:
    """Extract deduplicated @-file references."""
    refs: list[str] = []
    seen: set[str] = set()

    for match in _AT_FILE_PATTERN.finditer(body):
        ref = match.group(1) or match.group(2)
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)

    return refs


def _extract_heading_structure(body: str) -> list[dict[str, str | int]]:
    """Extract markdown heading hierarchy."""
    headings: list[dict[str, str | int]] = []

    for match in _HEADING_PATTERN.finditer(body):
        level = len(match.group(1))
        title = match.group(2).strip()
        headings.append({"level": level, "title": title})

    return headings
