"""Tests for cross-reference detection."""

import pytest

from ecosystem_mapper.models import EcosystemGraph, GraphNode, GraphEdge, NodeType, EdgeType
from ecosystem_mapper.analyzers.cross_references import (
    _detect_task_spawns,
    _detect_file_references,
    _detect_offer_next,
    _detect_agent_delegation,
)


class TestTaskSpawnDetection:
    """Test Task() spawn pattern regex."""

    def test_double_quoted(self):
        g = EcosystemGraph()
        g.add_node(GraphNode(
            id="skill:test", node_type=NodeType.SKILL, name="test",
            properties={"_body": 'Use Task with subagent_type="gsd-executor"'},
        ))
        g.add_node(GraphNode(
            id="agent:gsd-executor", node_type=NodeType.AGENT, name="gsd-executor",
        ))
        _detect_task_spawns(g)
        spawns = g.get_edges_by_type(EdgeType.SPAWNS)
        assert len(spawns) == 1
        assert spawns[0].target_id == "agent:gsd-executor"

    def test_single_quoted(self):
        g = EcosystemGraph()
        g.add_node(GraphNode(
            id="skill:test", node_type=NodeType.SKILL, name="test",
            properties={"_body": "subagent_type='meta-architect'"},
        ))
        g.add_node(GraphNode(
            id="agent:meta-architect", node_type=NodeType.AGENT, name="meta-architect",
        ))
        _detect_task_spawns(g)
        assert len(g.get_edges_by_type(EdgeType.SPAWNS)) == 1

    def test_colon_syntax(self):
        g = EcosystemGraph()
        g.add_node(GraphNode(
            id="skill:test", node_type=NodeType.SKILL, name="test",
            properties={"_body": 'subagent_type: "gsd-verifier"'},
        ))
        g.add_node(GraphNode(
            id="agent:gsd-verifier", node_type=NodeType.AGENT, name="gsd-verifier",
        ))
        _detect_task_spawns(g)
        assert len(g.get_edges_by_type(EdgeType.SPAWNS)) == 1

    def test_no_false_positives(self):
        g = EcosystemGraph()
        g.add_node(GraphNode(
            id="skill:test", node_type=NodeType.SKILL, name="test",
            properties={"_body": "No subagent references here at all"},
        ))
        g.add_node(GraphNode(
            id="agent:some-agent", node_type=NodeType.AGENT, name="some-agent",
        ))
        _detect_task_spawns(g)
        assert len(g.get_edges_by_type(EdgeType.SPAWNS)) == 0


class TestFileReferenceDetection:
    """Test @file reference regex."""

    def test_gsd_workflow_ref(self):
        g = EcosystemGraph()
        g.add_node(GraphNode(
            id="skill:test", node_type=NodeType.SKILL, name="test",
            properties={"_body": "@~/.claude/get-shit-done/workflows/execute-phase.md"},
        ))
        g.add_node(GraphNode(
            id="gsd-wf:execute-phase", node_type=NodeType.GSD_WORKFLOW,
            name="execute-phase", source_file="/path/execute-phase.md",
        ))
        _detect_file_references(g)
        refs = g.get_edges_by_type(EdgeType.REFERENCES)
        assert len(refs) == 1

    def test_gsd_reference_ref(self):
        g = EcosystemGraph()
        g.add_node(GraphNode(
            id="skill:test", node_type=NodeType.SKILL, name="test",
            properties={"_body": "@~/.claude/get-shit-done/references/principles.md"},
        ))
        g.add_node(GraphNode(
            id="gsd-ref:principles", node_type=NodeType.GSD_REFERENCE,
            name="principles", source_file="/path/principles.md",
        ))
        _detect_file_references(g)
        assert len(g.get_edges_by_type(EdgeType.REFERENCES)) == 1


class TestOfferNextDetection:
    """Test <offer_next> section parsing."""

    def test_offer_next_commands(self):
        g = EcosystemGraph()
        g.add_node(GraphNode(
            id="skill:gsd:plan-phase", node_type=NodeType.SKILL,
            name="gsd:plan-phase", namespace="gsd",
            properties={"_body": """
<offer_next>
- /gsd:execute-plan — Execute the plan
- /gsd:discuss-phase — Discuss further
</offer_next>
"""},
        ))
        g.add_node(GraphNode(
            id="skill:gsd:gsd:execute-plan", node_type=NodeType.SKILL,
            name="gsd:execute-plan", namespace="gsd",
        ))
        g.add_node(GraphNode(
            id="skill:gsd:gsd:discuss-phase", node_type=NodeType.SKILL,
            name="gsd:discuss-phase", namespace="gsd",
        ))
        _detect_offer_next(g)
        suggestions = g.get_edges_by_type(EdgeType.SUGGESTS_NEXT)
        assert len(suggestions) >= 1


class TestAgentDelegation:
    """Test agent-to-agent delegation detection."""

    def test_delegation_with_context(self):
        g = EcosystemGraph()
        g.add_node(GraphNode(
            id="agent:meta-architect", node_type=NodeType.AGENT, name="meta-architect",
            properties={"_body": "Orchestrate by spawning python-code-architect for code tasks"},
        ))
        g.add_node(GraphNode(
            id="agent:python-code-architect", node_type=NodeType.AGENT,
            name="python-code-architect",
        ))
        _detect_agent_delegation(g)
        deleg = g.get_edges_by_type(EdgeType.DELEGATES_TO)
        assert len(deleg) == 1

    def test_no_delegation_without_context(self):
        g = EcosystemGraph()
        g.add_node(GraphNode(
            id="agent:a1", node_type=NodeType.AGENT, name="a1",
            properties={"_body": "This is agent a2 mentioned casually"},
        ))
        g.add_node(GraphNode(
            id="agent:a2", node_type=NodeType.AGENT, name="a2",
        ))
        _detect_agent_delegation(g)
        assert len(g.get_edges_by_type(EdgeType.DELEGATES_TO)) == 0
