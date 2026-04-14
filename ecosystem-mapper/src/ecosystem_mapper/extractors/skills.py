"""Extract Skill nodes from SKILL.md files at user, workspace, and project scopes.

Unlike CommandExtractor (which walks ~/.claude/commands/*.md slash-command files),
this extractor walks SKILL.md files inside skills/ directories at three scope levels:

  - user      : ~/.claude/skills/{slug}/SKILL.md
  - workspace : {workspace_root}/.claude/skills/{slug}/SKILL.md
  - project   : {project_root}/.claude/skills/{slug}/SKILL.md

Plugin-shipped skills are deliberately NOT walked here — PluginExtractor handles those
from the plugin cache, producing PLUGIN_SKILL nodes.

Portability metadata (Cowork-ready / code-only / etc.) is joined from a hand-curated
REGISTRY.yaml file when one is provided via Config.registry_path. Skills missing from
the registry get properties['portability_tier'] = 'unclassified' so they surface in
the graph output as work-to-do.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..models import GraphEdge, GraphNode, NodeType
from ..parsers import BodyParser
from .base import BaseExtractor


class SkillExtractor(BaseExtractor):
    """Walk SKILL.md files at user/workspace/project scopes and join registry metadata."""

    def extract(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        registry = self._load_registry()

        # Scope 1: User-level skills at ~/.claude/skills/
        user_skills_dir = self.config.claude_home / "skills"
        for skill_md in self._find_skill_md_files(user_skills_dir):
            node = self._build_node(skill_md, scope="user", project_slug=None, registry=registry)
            if node is not None:
                nodes.append(node)

        # Scope 2 & 3: Per-project-dir skills
        # project_dirs may contain both workspace-level roots and project-level roots.
        # We classify them as "workspace" or "project" by looking for a parent project
        # marker (pyproject.toml / package.json); this is heuristic but good enough.
        for project_dir in self.config.project_dirs:
            project_skills_dir = project_dir / ".claude" / "skills"
            if not project_skills_dir.exists():
                continue

            scope, slug = self._classify_scope(project_dir)
            for skill_md in self._find_skill_md_files(project_skills_dir):
                node = self._build_node(
                    skill_md,
                    scope=scope,
                    project_slug=slug,
                    registry=registry,
                )
                if node is not None:
                    nodes.append(node)

        # Cross-reference edges: for each skill that declares other_skills dependencies
        # in the registry, emit INVOKES edges. Target IDs are resolved by name within
        # the same scope first, then fall back to any scope.
        edges.extend(self._emit_registry_invokes(nodes, registry))

        return nodes, edges

    # ---- file discovery -----------------------------------------------------

    def _find_skill_md_files(self, skills_root: Path) -> list[Path]:
        """Return SKILL.md files one level deep inside a skills/ directory."""
        if not skills_root.exists():
            return []
        results: list[Path] = []
        for child in sorted(skills_root.iterdir()):
            if not child.is_dir():
                continue
            skill_md = child / "SKILL.md"
            if skill_md.exists():
                results.append(skill_md)
            # Handle nested pattern like .claude/skills/anchor-brand-guidelines/anchor-brand-guidelines/SKILL.md
            for nested in child.glob("*/SKILL.md"):
                results.append(nested)
        return results

    def _classify_scope(self, project_dir: Path) -> tuple[str, str]:
        """Classify a project_dir as workspace or project scope and derive a slug.

        Heuristic: if the dir has pyproject.toml/package.json AND has a parent path
        component named ".../subprojects/..." or ".../projects/.../subprojects/...",
        it's a project. Otherwise it's a workspace.
        """
        slug = project_dir.name
        parts = project_dir.parts
        if "subprojects" in parts:
            return "project", slug
        return "workspace", slug

    # ---- registry -----------------------------------------------------------

    def _load_registry(self) -> dict[tuple[str, str | None, str], dict[str, Any]]:
        """Load REGISTRY.yaml into a lookup keyed by (scope, project_slug, name).

        Returns an empty dict if no registry path is configured or the file is missing.
        """
        registry_path = getattr(self.config, "registry_path", None)
        if not registry_path or not Path(registry_path).exists():
            return {}

        try:
            raw = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError) as exc:
            print(f"  Warning: failed to load registry {registry_path}: {exc}")
            return {}

        if not isinstance(raw, dict):
            return {}

        index: dict[tuple[str, str | None, str], dict[str, Any]] = {}
        for entry in raw.get("skills", []) or []:
            if not isinstance(entry, dict):
                continue
            scope = entry.get("scope")
            name = entry.get("name")
            if not scope or not name:
                continue
            project_slug = entry.get("project_slug")
            key = (scope, project_slug, name)
            index[key] = entry
        return index

    # ---- node construction --------------------------------------------------

    def _build_node(
        self,
        skill_md: Path,
        scope: str,
        project_slug: str | None,
        registry: dict[tuple[str, str | None, str], dict[str, Any]],
    ) -> GraphNode | None:
        try:
            text = skill_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

        fm, body = self.parse_frontmatter(text)
        # Skills without frontmatter still count — they just won't have metadata
        # beyond filesystem-derived name.
        name = fm.get("name", skill_md.parent.name) if fm else skill_md.parent.name
        description = ""
        if fm:
            desc_raw = fm.get("description", "")
            if isinstance(desc_raw, str):
                description = desc_raw[:200]

        skill_id = self._build_id(scope, project_slug, name)
        namespace = self._build_namespace(scope, project_slug)

        properties: dict[str, Any] = {
            "scope": scope,
            "project_slug": project_slug or "",
            "source_scope": scope,
            "_body": body,
        }
        properties.update(BodyParser.parse(body))

        # Join registry metadata if present
        registry_entry = registry.get((scope, project_slug, name))
        if registry_entry is not None:
            properties["registry_matched"] = True
            properties["purpose"] = registry_entry.get("purpose", "")
            properties["domain"] = registry_entry.get("domain", "unclassified")

            portability = registry_entry.get("portability", {}) or {}
            properties["portability_tier"] = portability.get("tier", "unclassified")
            properties["portability_rationale"] = portability.get("rationale", "")
            properties["portability_migration_notes"] = portability.get("migration_notes", "")

            properties["triggers"] = registry_entry.get("triggers", []) or []
            properties["registry_dependencies"] = registry_entry.get("dependencies", {}) or {}
            properties["registry_outputs"] = registry_entry.get("outputs", []) or []
            properties["cowork_substitute"] = registry_entry.get("cowork_substitute")
        else:
            properties["registry_matched"] = False
            properties["portability_tier"] = "unclassified"
            properties["domain"] = "unclassified"

        return GraphNode(
            id=skill_id,
            node_type=NodeType.SKILL,
            name=name,
            description=description,
            source_file=str(skill_md),
            namespace=namespace,
            properties=properties,
        )

    def _build_id(self, scope: str, project_slug: str | None, name: str) -> str:
        if scope == "project" and project_slug:
            return f"skill:project:{project_slug}:{name}"
        if scope == "workspace" and project_slug:
            return f"skill:workspace:{project_slug}:{name}"
        return f"skill:user:{name}"

    def _build_namespace(self, scope: str, project_slug: str | None) -> str:
        if scope == "project" and project_slug:
            return f"project/{project_slug}"
        if scope == "workspace" and project_slug:
            return f"workspace/{project_slug}"
        return "user"

    # ---- edges --------------------------------------------------------------

    def _emit_registry_invokes(
        self,
        nodes: list[GraphNode],
        registry: dict[tuple[str, str | None, str], dict[str, Any]],
    ) -> list[GraphEdge]:
        """Emit INVOKES edges where a registry entry declares other_skills.

        Resolution order: same scope → any scope → fallback to `skill:user:{name}`
        (which may dangle and get pruned by extract_all's cleanup).
        """
        from ..models import EdgeType  # local import to avoid top-level churn

        edges: list[GraphEdge] = []
        nodes_by_id = {n.id: n for n in nodes}
        nodes_by_name: dict[str, list[GraphNode]] = {}
        for node in nodes:
            nodes_by_name.setdefault(node.name, []).append(node)

        for node in nodes:
            deps = node.properties.get("registry_dependencies", {}) or {}
            other_skills = deps.get("other_skills", []) or []
            for target_name in other_skills:
                target_id = self._resolve_target_id(
                    target_name,
                    source_node=node,
                    nodes_by_id=nodes_by_id,
                    nodes_by_name=nodes_by_name,
                )
                if target_id:
                    edges.append(
                        GraphEdge(
                            source_id=node.id,
                            target_id=target_id,
                            edge_type=EdgeType.INVOKES,
                        )
                    )
        return edges

    def _resolve_target_id(
        self,
        target_name: str,
        source_node: GraphNode,
        nodes_by_id: dict[str, GraphNode],
        nodes_by_name: dict[str, list[GraphNode]],
    ) -> str | None:
        source_scope = source_node.properties.get("source_scope", "")
        source_project = source_node.properties.get("project_slug", "") or None

        # 1. Same scope, same project
        if source_scope == "project" and source_project:
            candidate = f"skill:project:{source_project}:{target_name}"
            if candidate in nodes_by_id:
                return candidate
        if source_scope == "workspace" and source_project:
            candidate = f"skill:workspace:{source_project}:{target_name}"
            if candidate in nodes_by_id:
                return candidate

        # 2. User scope (always a fallback candidate)
        user_candidate = f"skill:user:{target_name}"
        if user_candidate in nodes_by_id:
            return user_candidate

        # 3. Any scope with matching name
        matches = nodes_by_name.get(target_name, [])
        if matches:
            return matches[0].id

        # 4. Let it dangle — pruner will remove if still unresolved
        return user_candidate
