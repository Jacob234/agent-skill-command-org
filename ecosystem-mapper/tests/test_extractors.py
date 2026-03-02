"""Tests for ecosystem extractors against real data formats."""

import pytest
import tempfile
from pathlib import Path

from ecosystem_mapper.extractors.base import BaseExtractor, _parse_frontmatter_fallback
from ecosystem_mapper.models import EcosystemGraph, GraphNode, GraphEdge, NodeType, EdgeType
from ecosystem_mapper.config import Config


class TestFrontmatterParsing:
    """Test YAML frontmatter parsing including fallback for broken YAML."""

    def test_standard_yaml(self):
        text = """---
name: test-agent
description: A test agent
model: opus
---

Body text here."""
        fm, body = BaseExtractor.parse_frontmatter(text)
        assert fm["name"] == "test-agent"
        assert fm["model"] == "opus"
        assert "Body text" in body

    def test_yaml_with_list(self):
        text = """---
name: test-skill
allowed-tools:
  - Read
  - Write
  - Bash
---

Content."""
        fm, body = BaseExtractor.parse_frontmatter(text)
        assert fm["name"] == "test-skill"
        assert fm["allowed-tools"] == ["Read", "Write", "Bash"]

    def test_broken_yaml_with_colons(self):
        """Agent descriptions with embedded colons that break yaml.safe_load."""
        text = """---
name: meta-architect
description: Use this agent for: strategic decisions. Examples: <example>Context: User asks something</example>
model: opus
color: silver
---

Body."""
        fm, body = BaseExtractor.parse_frontmatter(text)
        assert fm["name"] == "meta-architect"
        assert fm["model"] == "opus"
        assert "description" in fm
        assert "Body." in body

    def test_no_frontmatter(self):
        text = "# Just markdown\n\nNo frontmatter here."
        fm, body = BaseExtractor.parse_frontmatter(text)
        assert fm == {}
        assert "Just markdown" in body

    def test_empty_frontmatter(self):
        text = "---\n---\nBody only."
        fm, body = BaseExtractor.parse_frontmatter(text)
        assert fm == {}
        assert "Body only." in body


class TestFallbackParser:
    """Test the line-by-line fallback parser directly."""

    def test_simple_kv(self):
        raw = "name: test\nmodel: opus"
        result = _parse_frontmatter_fallback(raw)
        assert result["name"] == "test"
        assert result["model"] == "opus"

    def test_multiline_value(self):
        raw = "description: This is a long\n  description that spans lines"
        result = _parse_frontmatter_fallback(raw)
        assert "long" in result["description"]
        assert "spans" in result["description"]

    def test_list_items(self):
        raw = "allowed-tools:\n  - Read\n  - Write\n  - Bash"
        result = _parse_frontmatter_fallback(raw)
        assert result["allowed-tools"] == ["Read", "Write", "Bash"]

    def test_value_with_colons(self):
        raw = "name: test\ndescription: Context: user asks. Result: success"
        result = _parse_frontmatter_fallback(raw)
        assert result["name"] == "test"
        assert "Context" in result["description"]


class TestEcosystemGraph:
    """Test the graph container."""

    def test_add_node(self):
        g = EcosystemGraph()
        n = GraphNode(id="test:1", node_type=NodeType.AGENT, name="test")
        g.add_node(n)
        assert g.has_node("test:1")
        assert len(g.nodes) == 1

    def test_add_edge_deduplication(self):
        g = EcosystemGraph()
        e1 = GraphEdge("a", "b", EdgeType.SPAWNS)
        e2 = GraphEdge("a", "b", EdgeType.SPAWNS)
        g.add_edge(e1)
        g.add_edge(e2)
        assert len(g.edges) == 1

    def test_get_nodes_by_type(self):
        g = EcosystemGraph()
        g.add_node(GraphNode(id="agent:1", node_type=NodeType.AGENT, name="a1"))
        g.add_node(GraphNode(id="skill:1", node_type=NodeType.SKILL, name="s1"))
        g.add_node(GraphNode(id="agent:2", node_type=NodeType.AGENT, name="a2"))
        assert len(g.get_nodes_by_type(NodeType.AGENT)) == 2
        assert len(g.get_nodes_by_type(NodeType.SKILL)) == 1

    def test_to_dict_stats(self):
        g = EcosystemGraph()
        g.add_node(GraphNode(id="a:1", node_type=NodeType.AGENT, name="a"))
        g.add_edge(GraphEdge("a:1", "b:1", EdgeType.SPAWNS))
        d = g.to_dict()
        assert d["stats"]["total_nodes"] == 1
        assert d["stats"]["total_edges"] == 1


class TestAgentCategorization:
    """Test agent categorization logic."""

    def test_execution_category(self):
        """Agents with tools should be categorized as execution."""
        text = """---
name: executor
tools: Read, Write, Bash
---
Body."""
        fm, _ = BaseExtractor.parse_frontmatter(text)
        tools = [t.strip() for t in fm.get("tools", "").split(",") if t.strip()]
        model = fm.get("model", "")
        if tools:
            category = "execution"
        elif model:
            category = "design"
        else:
            category = "utility"
        assert category == "execution"

    def test_design_category(self):
        """Agents with model but no tools should be design."""
        text = """---
name: planner
model: opus
---
Body."""
        fm, _ = BaseExtractor.parse_frontmatter(text)
        tools_raw = fm.get("tools", "")
        tools = [t.strip() for t in tools_raw.split(",") if t.strip()] if isinstance(tools_raw, str) else []
        model = fm.get("model", "")
        if tools:
            category = "execution"
        elif model:
            category = "design"
        else:
            category = "utility"
        assert category == "design"


class TestCapabilitiesExtraction:
    """Test CapabilitiesExtractor table row parsing."""

    def test_table_row_parsing(self):
        """Verify table rows are parsed into CapabilityEntry nodes."""
        from ecosystem_mapper.extractors.capabilities import CapabilitiesExtractor

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_home = Path(tmpdir)
            cap_file = claude_home / "CAPABILITIES.md"
            cap_file.write_text("""# Skills

## Core Commands

| Command | Description | When to Use |
|---------|-------------|-------------|
| /commit | Create a git commit | After completing changes |
| /review-pr | Review a pull request | When PR needs review |

## GSD Commands

| Command | Description | When to Use |
|---------|-------------|-------------|
| /gsd:plan | Plan a project phase | At project start |
""")
            config = Config(claude_home=claude_home)
            extractor = CapabilitiesExtractor(config)
            nodes, edges = extractor.extract()

            assert len(nodes) == 3
            names = {n.name for n in nodes}
            assert "commit" in names
            assert "review-pr" in names
            assert "gsd:plan" in names

            # Verify properties
            commit_node = next(n for n in nodes if n.name == "commit")
            assert commit_node.properties["when_to_use"] == "After completing changes"
            assert commit_node.properties["section"] == "Core Commands"

    def test_skips_header_rows(self):
        """Header rows like | Command | Description | should be skipped."""
        from ecosystem_mapper.extractors.capabilities import CapabilitiesExtractor

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_home = Path(tmpdir)
            cap_file = claude_home / "CAPABILITIES.md"
            cap_file.write_text("""| Command | Description | When to Use |
|---------|-------------|-------------|
| /test | Test skill | When testing |
""")
            config = Config(claude_home=claude_home)
            extractor = CapabilitiesExtractor(config)
            nodes, _ = extractor.extract()
            # Should only have "test", not "Command"
            assert len(nodes) == 1
            assert nodes[0].name == "test"


class TestGSDContentParsing:
    """Test that GSD nodes now have _body and semantic.* properties."""

    def test_gsd_workflow_has_body_and_semantics(self):
        from ecosystem_mapper.extractors.gsd import GSDFrameworkExtractor

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_home = Path(tmpdir)
            gsd_dir = claude_home / "get-shit-done"
            wf_dir = gsd_dir / "workflows"
            wf_dir.mkdir(parents=True)

            (wf_dir / "execute-phase.md").write_text("""---
description: Execute a planned phase
---

## Execution Steps

<execution_flow>
Run the plan step by step.
</execution_flow>

Load @~/.claude/get-shit-done/references/principles.md for guidance.
""")
            config = Config(claude_home=claude_home)
            extractor = GSDFrameworkExtractor(config)
            nodes, _ = extractor.extract()

            assert len(nodes) == 1
            node = nodes[0]
            assert node.properties["_body"]
            assert "semantic.xml_sections" in node.properties
            assert "execution_flow" in node.properties["semantic.xml_sections"]
            assert "semantic.at_file_refs" in node.properties
            assert "semantic.heading_structure" in node.properties

    def test_gsd_deprecation_detection(self):
        from ecosystem_mapper.extractors.gsd import GSDFrameworkExtractor

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_home = Path(tmpdir)
            gsd_dir = claude_home / "get-shit-done" / "references"
            gsd_dir.mkdir(parents=True)

            (gsd_dir / "old-guide.md").write_text(
                "⚠️ DEPRECATED: Use new-guide.md instead.\n\nOld content."
            )
            config = Config(claude_home=claude_home)
            extractor = GSDFrameworkExtractor(config)
            nodes, _ = extractor.extract()

            assert len(nodes) == 1
            assert nodes[0].properties.get("deprecated") is True
