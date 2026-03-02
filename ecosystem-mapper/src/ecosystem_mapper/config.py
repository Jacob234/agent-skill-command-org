"""Path constants and configuration for ecosystem mapping."""

from pathlib import Path


class Config:
    """Centralized path resolution for Claude Code ecosystem files."""

    def __init__(self, claude_home: Path | None = None, project_dirs: list[Path] | None = None):
        self.claude_home = claude_home or Path.home() / ".claude"
        self.project_dirs: list[Path] = project_dirs or []

    @property
    def agents_dir(self) -> Path:
        return self.claude_home / "agents"

    @property
    def commands_dir(self) -> Path:
        return self.claude_home / "commands"

    @property
    def plugins_dir(self) -> Path:
        return self.claude_home / "plugins"

    @property
    def plugins_cache_dir(self) -> Path:
        return self.plugins_dir / "cache"

    @property
    def installed_plugins_file(self) -> Path:
        return self.plugins_dir / "installed_plugins.json"

    @property
    def settings_file(self) -> Path:
        return self.claude_home / "settings.json"

    @property
    def gsd_dir(self) -> Path:
        return self.claude_home / "get-shit-done"

    @property
    def capabilities_file(self) -> Path:
        return self.claude_home / "CAPABILITIES.md"

    @property
    def plans_dir(self) -> Path:
        return self.claude_home / "plans"

    @property
    def handoffs_dir(self) -> Path:
        return self.claude_home / "handoffs"

    @property
    def wrapups_dir(self) -> Path:
        return self.claude_home / "wrapups"


# Built-in tools that are always available
BUILTIN_TOOLS = [
    "Read", "Write", "Edit", "MultiEdit", "Bash", "Grep", "Glob",
    "Task", "WebFetch", "WebSearch", "NotebookEdit", "TodoWrite",
    "AskUserQuestion", "EnterPlanMode", "ExitPlanMode",
]
