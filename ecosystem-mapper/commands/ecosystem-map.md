---
name: ecosystem-map
description: Generate an interactive graph of the Claude Code ecosystem (agents, skills, plugins, hooks, MCP servers)
argument-hint: "[--format json|html|all]"
allowed-tools:
  - Bash
  - Read
  - Glob
---

<objective>
Generate an interactive ecosystem map showing how all Claude Code components connect.
</objective>

<instructions>
1. Run the ecosystem mapper CLI:
   ```bash
   cd ~/JBK-Research/agent-skill-command-org/ecosystem-mapper
   python -m ecosystem_mapper.cli --claude-home ~/.claude --output-dir ./out --format all -v
   ```

2. Report the summary statistics (node counts by type, edge counts by type).

3. Open the HTML visualization:
   ```bash
   open ./out/ecosystem-map.html
   ```

4. Highlight key findings:
   - Which agents have the most connections?
   - Which plugins provide the most skills?
   - Are there isolated nodes with no connections?
   - What are the main execution chains (skill → agent → agent)?
</instructions>
