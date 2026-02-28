"""Base extractor with shared YAML frontmatter parsing."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml

from ..config import Config
from ..models import GraphNode, GraphEdge


class BaseExtractor(ABC):
    """Abstract base for all ecosystem extractors."""

    def __init__(self, config: Config):
        self.config = config

    @abstractmethod
    def extract(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        """Extract nodes and edges from source files."""
        ...

    @staticmethod
    def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
        """Split YAML frontmatter from markdown body.

        Returns (frontmatter_dict, body_text). If no frontmatter found,
        returns ({}, full_text).

        Falls back to line-by-line parsing when YAML fails (common with
        description fields containing unquoted colons).
        """
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
        if not match:
            return {}, text

        raw = match.group(1)
        body = match.group(2)

        try:
            fm = yaml.safe_load(raw) or {}
            if isinstance(fm, dict):
                return fm, body
        except yaml.YAMLError:
            pass

        # Fallback: line-by-line key: value parsing
        fm = _parse_frontmatter_fallback(raw)
        return fm, body

    @staticmethod
    def safe_glob(directory: Path, pattern: str) -> list[Path]:
        """Glob that returns empty list if directory doesn't exist."""
        if not directory.exists():
            return []
        return sorted(directory.glob(pattern))


def _parse_frontmatter_fallback(raw: str) -> dict[str, Any]:
    """Parse frontmatter line by line when YAML fails.

    Handles multi-line values (description spanning lines) and
    YAML list items (lines starting with '  - ').
    """
    result: dict[str, Any] = {}
    current_key: str | None = None
    current_value_lines: list[str] = []

    for line in raw.split("\n"):
        # YAML list item under current key
        if re.match(r"^\s+-\s+", line) and current_key:
            item = re.sub(r"^\s+-\s+", "", line).strip()
            if current_key not in result:
                _flush_key(result, current_key, current_value_lines)
                current_value_lines = []
            if isinstance(result.get(current_key), list):
                result[current_key].append(item)
            else:
                prev = result.get(current_key, "")
                result[current_key] = [prev, item] if prev else [item]
            continue

        # New key: value pair (only split on first colon)
        kv_match = re.match(r"^(\w[\w-]*)\s*:\s*(.*)", line)
        if kv_match:
            if current_key and current_key not in result:
                _flush_key(result, current_key, current_value_lines)
            current_key = kv_match.group(1)
            current_value_lines = [kv_match.group(2).strip()]
        elif current_key and line.strip():
            current_value_lines.append(line.strip())

    if current_key and current_key not in result:
        _flush_key(result, current_key, current_value_lines)

    return result


def _flush_key(result: dict, key: str, value_lines: list[str]) -> None:
    """Store accumulated value lines into result dict."""
    value = " ".join(value_lines).strip()
    if not value:
        result[key] = ""
    elif value.startswith("[") and value.endswith("]"):
        items = [v.strip().strip("'\"") for v in value[1:-1].split(",")]
        result[key] = [i for i in items if i]
    else:
        result[key] = value
