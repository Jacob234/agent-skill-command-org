"""Tests for BodyParser semantic extraction."""

import pytest

from ecosystem_mapper.parsers.body_parser import BodyParser


class TestXMLExtraction:
    """Test XML-tagged section extraction."""

    def test_simple_tag(self):
        body = "<overview>This is an overview section.</overview>"
        result = BodyParser.parse(body)
        assert "semantic.xml_sections" in result
        assert result["semantic.xml_sections"]["overview"] == "This is an overview section."

    def test_named_tag(self):
        body = '<step name="load">Load the data from disk.</step>'
        result = BodyParser.parse(body)
        assert result["semantic.xml_sections"]["step.load"] == "Load the data from disk."

    def test_nested_tags(self):
        """Outer tag captures inner tags as raw content; sibling tags at same level are separate."""
        body = """<execution_flow>
<step name="init">Initialize the system.</step>
<step name="run">Execute the pipeline.</step>
</execution_flow>"""
        result = BodyParser.parse(body)
        sections = result["semantic.xml_sections"]
        # Outer tag captures everything inside including inner tags
        assert "execution_flow" in sections
        assert "Initialize the system" in sections["execution_flow"]
        assert "Execute the pipeline" in sections["execution_flow"]

    def test_sibling_named_tags(self):
        """Sibling tags at the same level (not nested) should each be captured."""
        body = '<step name="init">Initialize.</step>\n<step name="run">Execute.</step>'
        result = BodyParser.parse(body)
        sections = result["semantic.xml_sections"]
        assert "step.init" in sections
        assert "step.run" in sections

    def test_multiple_tags(self):
        body = "<overview>First section.</overview>\n\n<details>Second section.</details>"
        result = BodyParser.parse(body)
        sections = result["semantic.xml_sections"]
        assert len(sections) == 2
        assert sections["overview"] == "First section."
        assert sections["details"] == "Second section."

    def test_empty_body(self):
        result = BodyParser.parse("")
        assert result == {}

    def test_whitespace_only_body(self):
        result = BodyParser.parse("   \n\n  ")
        assert result == {}

    def test_no_xml_sections(self):
        body = "Just plain markdown with no XML tags."
        result = BodyParser.parse(body)
        assert "semantic.xml_sections" not in result


class TestAtFileRefs:
    """Test @file reference extraction."""

    def test_claude_path(self):
        body = "Load @~/.claude/get-shit-done/workflows/execute-phase.md for execution."
        result = BodyParser.parse(body)
        assert "semantic.at_file_refs" in result
        assert "~/.claude/get-shit-done/workflows/execute-phase.md" in result["semantic.at_file_refs"]

    def test_planning_path(self):
        body = "See @.planning/roadmap.md for details."
        result = BodyParser.parse(body)
        assert ".planning/roadmap.md" in result["semantic.at_file_refs"]

    def test_multiple_refs(self):
        body = """
Load @~/.claude/get-shit-done/workflows/plan.md and
also @~/.claude/get-shit-done/references/principles.md
"""
        result = BodyParser.parse(body)
        refs = result["semantic.at_file_refs"]
        assert len(refs) == 2

    def test_deduplication(self):
        body = """
Use @~/.claude/agents/foo.md here.
And again @~/.claude/agents/foo.md there.
"""
        result = BodyParser.parse(body)
        refs = result["semantic.at_file_refs"]
        assert len(refs) == 1

    def test_no_refs(self):
        body = "No file references here."
        result = BodyParser.parse(body)
        assert "semantic.at_file_refs" not in result


class TestHeadingStructure:
    """Test markdown heading extraction."""

    def test_h2_and_h3(self):
        body = """## Overview
Some text.

### Details
More text.

## Summary
Final text."""
        result = BodyParser.parse(body)
        headings = result["semantic.heading_structure"]
        assert len(headings) == 3
        assert headings[0] == {"level": 2, "title": "Overview"}
        assert headings[1] == {"level": 3, "title": "Details"}
        assert headings[2] == {"level": 2, "title": "Summary"}

    def test_title_extraction(self):
        body = "# Main Title\n\nContent here."
        result = BodyParser.parse(body)
        headings = result["semantic.heading_structure"]
        assert headings[0]["title"] == "Main Title"
        assert headings[0]["level"] == 1

    def test_no_headings(self):
        body = "No headings in this text."
        result = BodyParser.parse(body)
        assert "semantic.heading_structure" not in result
