# CLAUDE.md — agent-skill-command-org

## Project Overview

Tools for mapping and organizing the Claude Code agent skill ecosystem. The primary subproject is `ecosystem-mapper/`, which parses `~/.claude/` configs and produces interactive graph visualizations of how Claude Code components connect.

## Repository Structure

```
agent-skill-command-org/
├── CLAUDE.md                    # This file — project conventions
├── ecosystem-mapper/            # Main subproject
│   ├── pyproject.toml           # Python >=3.10, deps: pyyaml, jinja2
│   ├── src/ecosystem_mapper/    # Source code
│   │   ├── cli.py               # CLI entry point
│   │   ├── config.py            # Path constants
│   │   ├── models.py            # GraphNode, GraphEdge, EcosystemGraph
│   │   ├── extractors/          # 7+ extractors (agents, commands, plugins, etc.)
│   │   ├── analyzers/           # Cross-reference detection
│   │   └── outputs/             # JSON export + HTML visualization
│   ├── templates/               # Cytoscape.js visualization templates
│   ├── tests/                   # pytest test suites
│   └── commands/                # Slash command definitions
└── .github/                     # Issue templates, CI workflows
```

## Development Workflow: Issue/Worktree Model

### The Flow

1. **Create a GitHub issue** describing the work (feature, bug, improvement)
2. **Start a worktree** branching from `main` — the branch name references the issue:
   ```
   feat/42-neo4j-integration
   fix/57-dangling-edge-crash
   refactor/63-extractor-base-class
   ```
3. **Do the work** in the worktree — commit early, commit often
4. **Open a PR** linking the issue (use `Closes #42` in the PR body)
5. **Merge to main** via squash-merge or regular merge (prefer squash for single-feature PRs)
6. **Clean up** the worktree after merge

### Branch Naming Convention

```
<type>/<issue-number>-<short-description>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

### Commit Message Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/):
```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

Scopes: `extractors`, `analyzers`, `outputs`, `cli`, `models`, `templates`, `ci`, `docs`

Examples:
```
feat(extractors): add handoff document extractor
fix(outputs): prevent dangling edges in Cytoscape.js render
test(analyzers): add cross-reference edge case coverage
```

## Running the Project

```bash
cd ecosystem-mapper
source .venv/bin/activate
python -m ecosystem_mapper.cli --claude-home ~/.claude --output-dir ./out --format all -v
```

## Running Tests

```bash
cd ecosystem-mapper
source .venv/bin/activate
python -m pytest tests/ -v
```

## Code Conventions

- **Python 3.10+** — use modern syntax (match/case, `X | Y` union types, etc.)
- **Extractors** inherit from `BaseExtractor` in `extractors/base.py`
- **Models** are dataclasses in `models.py` — `GraphNode`, `GraphEdge`, `EcosystemGraph`
- **Edge pruning**: `extract_all()` in `extractors/__init__.py` auto-creates missing tool nodes and prunes dangling edges
- **YAML frontmatter**: The base extractor has a fallback line-by-line parser for files with unquoted colons
- **Generated output** (`out/`) is gitignored — never commit it

## Key Architectural Decisions

1. **Extractors are modular**: Each component type (agents, plugins, hooks, etc.) has its own extractor file. New extractors should follow the same pattern.
2. **Graph model is the contract**: All extractors produce `GraphNode`/`GraphEdge` instances. The output layer consumes `EcosystemGraph`.
3. **HTML visualization is self-contained**: The output HTML inlines Cytoscape.js so it works offline with zero dependencies.
4. **No external runtime dependencies beyond pyyaml + jinja2**: Keep the dependency footprint minimal.
