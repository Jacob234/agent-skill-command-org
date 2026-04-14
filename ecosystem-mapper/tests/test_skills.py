"""Tests for the SkillExtractor and DOT output."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml
from ecosystem_mapper.config import Config
from ecosystem_mapper.extractors.skills import SkillExtractor
from ecosystem_mapper.models import EcosystemGraph, EdgeType, GraphNode, NodeType
from ecosystem_mapper.outputs.dot_export import (
    TIER_COLORS,
    _escape,
    export_dot,
)

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def fake_filesystem():
    """Create a temp dir that looks like:

        ~/.claude/skills/my-user-skill/SKILL.md
        ~/.claude/skills/user/nested-skill/SKILL.md   (two-level nesting)
        <project>/.claude/skills/alpha/SKILL.md
        <project>/.claude/skills/beta/SKILL.md        (no frontmatter)
        <workspace>/.claude/skills/gamma/SKILL.md

    Returns (tmpdir, claude_home, project_dir, workspace_dir).
    """
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # Fake ~/.claude/skills/
        claude_home = root / "fake_claude_home"
        user_skill = claude_home / "skills" / "my-user-skill" / "SKILL.md"
        user_skill.parent.mkdir(parents=True)
        user_skill.write_text("---\nname: my-user-skill\ndescription: A user-level skill\n---\n\nBody.\n")

        nested = claude_home / "skills" / "user" / "nested-skill" / "SKILL.md"
        nested.parent.mkdir(parents=True)
        nested.write_text("---\nname: nested-skill\ndescription: One level deeper\n---\n\nBody.\n")

        # Fake project at .../subprojects/<something>/
        project_dir = root / "some-root" / "subprojects" / "my-project"
        (project_dir / ".claude" / "skills" / "alpha").mkdir(parents=True)
        (project_dir / ".claude" / "skills" / "alpha" / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: Alpha skill\n---\n\nBody.\n"
        )
        (project_dir / ".claude" / "skills" / "beta").mkdir(parents=True)
        (project_dir / ".claude" / "skills" / "beta" / "SKILL.md").write_text("# No frontmatter here\n\nJust a body.\n")

        # Fake workspace (no 'subprojects' in path)
        workspace_dir = root / "my-workspace"
        (workspace_dir / ".claude" / "skills" / "gamma").mkdir(parents=True)
        (workspace_dir / ".claude" / "skills" / "gamma" / "SKILL.md").write_text(
            "---\nname: gamma\ndescription: Gamma skill\n---\n\nBody.\n"
        )

        yield root, claude_home, project_dir, workspace_dir


# -----------------------------------------------------------------------------
# SkillExtractor walking
# -----------------------------------------------------------------------------


class TestSkillExtractorDiscovery:
    def test_walks_all_three_scopes(self, fake_filesystem):
        _, claude_home, project_dir, workspace_dir = fake_filesystem
        config = Config(
            claude_home=claude_home,
            project_dirs=[project_dir, workspace_dir],
        )
        extractor = SkillExtractor(config)
        nodes, _edges = extractor.extract()

        ids = {n.id for n in nodes}
        assert "skill:user:my-user-skill" in ids
        assert "skill:user:nested-skill" in ids, "should find nested skill one level deeper"
        assert "skill:project:my-project:alpha" in ids
        assert "skill:project:my-project:beta" in ids, "should still index skills without frontmatter"
        assert "skill:workspace:my-workspace:gamma" in ids

    def test_classify_scope_by_subprojects_marker(self):
        config = Config(claude_home=Path("/tmp"))
        extractor = SkillExtractor(config)
        scope, slug = extractor._classify_scope(Path("/a/b/subprojects/deal-etl"))
        assert scope == "project"
        assert slug == "deal-etl"

        scope, slug = extractor._classify_scope(Path("/a/b/jbk-workspace"))
        assert scope == "workspace"
        assert slug == "jbk-workspace"

    def test_missing_skills_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            config = Config(
                claude_home=Path(td) / "does-not-exist",
                project_dirs=[Path(td) / "nope"],
            )
            extractor = SkillExtractor(config)
            nodes, edges = extractor.extract()
            assert nodes == []
            assert edges == []


# -----------------------------------------------------------------------------
# Registry join
# -----------------------------------------------------------------------------


class TestSkillRegistryJoin:
    def _write_registry(self, path: Path, entries: list[dict]) -> None:
        path.write_text(yaml.safe_dump({"schema_version": 1, "skills": entries}))

    def test_registry_metadata_joined_into_properties(self, fake_filesystem, tmp_path):
        _, claude_home, project_dir, _ = fake_filesystem
        registry_path = tmp_path / "REGISTRY.yaml"
        self._write_registry(
            registry_path,
            [
                {
                    "id": "skill:project:my-project:alpha",
                    "scope": "project",
                    "project_slug": "my-project",
                    "name": "alpha",
                    "purpose": "A plain-language description",
                    "domain": "ops",
                    "portability": {
                        "tier": "cowork_ready",
                        "rationale": "No filesystem writes",
                        "migration_notes": "",
                    },
                    "triggers": ["/alpha"],
                    "dependencies": {"tools": ["Read"], "other_skills": []},
                },
            ],
        )
        config = Config(
            claude_home=claude_home,
            project_dirs=[project_dir],
            registry_path=registry_path,
        )
        nodes, _edges = SkillExtractor(config).extract()

        alpha = next(n for n in nodes if n.id == "skill:project:my-project:alpha")
        assert alpha.properties["registry_matched"] is True
        assert alpha.properties["portability_tier"] == "cowork_ready"
        assert alpha.properties["domain"] == "ops"
        assert alpha.properties["purpose"] == "A plain-language description"

    def test_unclassified_fallback_when_no_registry_entry(self, fake_filesystem):
        _, claude_home, project_dir, _ = fake_filesystem
        config = Config(claude_home=claude_home, project_dirs=[project_dir])
        nodes, _ = SkillExtractor(config).extract()

        alpha = next(n for n in nodes if n.id == "skill:project:my-project:alpha")
        assert alpha.properties["registry_matched"] is False
        assert alpha.properties["portability_tier"] == "unclassified"
        assert alpha.properties["domain"] == "unclassified"

    def test_missing_registry_file_does_not_error(self, fake_filesystem, tmp_path):
        _, claude_home, project_dir, _ = fake_filesystem
        config = Config(
            claude_home=claude_home,
            project_dirs=[project_dir],
            registry_path=tmp_path / "does-not-exist.yaml",
        )
        nodes, _ = SkillExtractor(config).extract()
        assert all(n.properties["registry_matched"] is False for n in nodes)

    def test_registry_invokes_edges(self, fake_filesystem, tmp_path):
        _, claude_home, project_dir, _ = fake_filesystem
        registry_path = tmp_path / "REGISTRY.yaml"
        self._write_registry(
            registry_path,
            [
                {
                    "id": "skill:project:my-project:alpha",
                    "scope": "project",
                    "project_slug": "my-project",
                    "name": "alpha",
                    "purpose": "",
                    "domain": "ops",
                    "portability": {"tier": "cowork_ready"},
                    "dependencies": {"other_skills": ["beta"]},
                },
            ],
        )
        config = Config(
            claude_home=claude_home,
            project_dirs=[project_dir],
            registry_path=registry_path,
        )
        _nodes, edges = SkillExtractor(config).extract()

        invokes = [
            e
            for e in edges
            if e.edge_type == EdgeType.INVOKES
            and e.source_id == "skill:project:my-project:alpha"
            and e.target_id == "skill:project:my-project:beta"
        ]
        assert len(invokes) == 1


# -----------------------------------------------------------------------------
# DOT export
# -----------------------------------------------------------------------------


class TestDotExport:
    def _make_graph(self, tier: str) -> EcosystemGraph:
        graph = EcosystemGraph()
        graph.add_node(
            GraphNode(
                id="skill:project:demo:foo",
                node_type=NodeType.SKILL,
                name="foo",
                description="A demo skill",
                source_file="/tmp/fake/SKILL.md",
                namespace="project/demo",
                properties={
                    "scope": "project",
                    "project_slug": "demo",
                    "registry_matched": True,
                    "portability_tier": tier,
                    "domain": "deal_pipeline",
                    "purpose": "A test skill",
                },
            )
        )
        return graph

    def test_dot_file_is_written(self, tmp_path):
        graph = self._make_graph("cowork_ready")
        out = export_dot(graph, tmp_path)
        assert out.exists()
        assert out.name == "ecosystem-map.dot"
        content = out.read_text()
        assert content.startswith("digraph ecosystem {")
        assert content.rstrip().endswith("}")

    def test_tier_color_applied(self, tmp_path):
        graph = self._make_graph("code_only")
        out = export_dot(graph, tmp_path)
        content = out.read_text()
        assert TIER_COLORS["code_only"] in content

    def test_domain_cluster_rendered(self, tmp_path):
        graph = self._make_graph("cowork_with_mcp")
        out = export_dot(graph, tmp_path)
        content = out.read_text()
        assert "cluster_domain_deal_pipeline" in content

    def test_legend_rendered(self, tmp_path):
        graph = self._make_graph("needs_port")
        out = export_dot(graph, tmp_path)
        content = out.read_text()
        # Legend is a single plaintext node with an HTML-like label
        assert "legend [shape=plaintext" in content
        assert "Portability tiers" in content
        for tier in ("cowork_ready", "cowork_with_mcp", "needs_port", "code_only", "unclassified"):
            assert tier in content

    def test_escape_handles_quotes_and_backslashes(self):
        assert _escape('hello "world"') == 'hello \\"world\\"'
        assert _escape("a\\b") == "a\\\\b"
