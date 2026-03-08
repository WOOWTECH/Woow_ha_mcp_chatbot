"""Skills management for AI agent capabilities.

Adapted from nanobot's agent/skills.py for Home Assistant.
Each skill = directory with SKILL.md (YAML frontmatter + Markdown body).
  - always: true  → full body injected into system prompt
  - otherwise     → listed as XML summary; AI reads on demand via read_skill tool
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Default example skill
_EXAMPLE_SKILL = """---
name: example
description: An example skill showing the SKILL.md format. Delete or modify this.
always: false
---

# Example Skill

This is an example skill. Replace this content with your own instructions.

## Usage

The AI agent can read this skill when relevant and follow the instructions here.

## Frontmatter Fields

- **name**: Skill directory name (must match)
- **description**: One-line description shown in the skill summary
- **always**: If `true`, the full skill body is always injected into the system prompt
- **homepage**: Optional URL for more information
"""


class SkillsLoader:
    """Discover, load, and manage skills from the skills directory.

    All file I/O is performed via hass.async_add_executor_job to avoid
    blocking the HA event loop.
    """

    def __init__(self, hass: HomeAssistant, skills_dir: Path) -> None:
        self.hass = hass
        self._skills_dir = skills_dir
        # Cache: name → parsed metadata dict
        self._cache: dict[str, dict[str, Any]] = {}

    async def async_setup(self) -> None:
        """Initialize skills directory and discover skills."""
        await self.hass.async_add_executor_job(self._setup_dir)
        await self.refresh_cache()
        _LOGGER.info(
            "SkillsLoader initialized: %d skills at %s",
            len(self._cache),
            self._skills_dir,
        )

    def _setup_dir(self) -> None:
        """Create skills directory if it doesn't exist (sync)."""
        self._skills_dir.mkdir(parents=True, exist_ok=True)
        # Create example skill if directory is empty
        example_dir = self._skills_dir / "example"
        if not any(self._skills_dir.iterdir()):
            example_dir.mkdir(exist_ok=True)
            (example_dir / "SKILL.md").write_text(_EXAMPLE_SKILL, encoding="utf-8")

    # ── Discovery & Cache ──

    async def refresh_cache(self) -> None:
        """Re-scan the skills directory and rebuild the cache."""
        self._cache = await self.hass.async_add_executor_job(self._scan_skills)

    def _scan_skills(self) -> dict[str, dict[str, Any]]:
        """Scan skills directory and parse metadata (sync)."""
        result: dict[str, dict[str, Any]] = {}
        if not self._skills_dir.exists():
            return result

        for skill_dir in sorted(self._skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            content = skill_file.read_text(encoding="utf-8")
            meta = self._parse_frontmatter(content)
            meta.setdefault("name", skill_dir.name)
            meta["path"] = str(skill_file)
            meta["dir"] = str(skill_dir)
            result[skill_dir.name] = meta

        return result

    @staticmethod
    def _parse_frontmatter(content: str) -> dict[str, Any]:
        """Parse YAML frontmatter from SKILL.md content."""
        if not content.startswith("---"):
            return {}

        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return {}

        metadata: dict[str, Any] = {}
        for line in match.group(1).split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip("\"'")

            # Type coercion for known fields
            if key == "always":
                metadata[key] = value.lower() in ("true", "yes", "1")
            else:
                metadata[key] = value

        return metadata

    @staticmethod
    def _strip_frontmatter(content: str) -> str:
        """Remove YAML frontmatter from content."""
        if not content.startswith("---"):
            return content
        match = re.match(r"^---\n.*?\n---\n?", content, re.DOTALL)
        if match:
            return content[match.end():]
        return content

    # ── Public API ──

    async def list_skills(self) -> list[dict[str, Any]]:
        """List all skills with metadata."""
        return [
            {
                "name": name,
                "description": meta.get("description", ""),
                "always": meta.get("always", False),
                "homepage": meta.get("homepage", ""),
                "path": meta.get("path", ""),
            }
            for name, meta in self._cache.items()
        ]

    async def get_skill_metadata(self, name: str) -> dict[str, Any] | None:
        """Get metadata for a specific skill."""
        return self._cache.get(name)

    async def read_skill(self, name: str) -> str | None:
        """Read the full SKILL.md content for a skill."""
        meta = self._cache.get(name)
        if not meta:
            return None
        path = Path(meta["path"])
        return await self.hass.async_add_executor_job(self._read_file, path)

    async def read_skill_body(self, name: str) -> str | None:
        """Read skill body (without frontmatter)."""
        content = await self.read_skill(name)
        if content is None:
            return None
        return self._strip_frontmatter(content)

    async def create_skill(
        self,
        name: str,
        description: str,
        content: str,
        always: bool = False,
        homepage: str = "",
    ) -> dict[str, Any]:
        """Create a new skill."""
        # Validate name
        safe_name = re.sub(r"[^a-z0-9_-]", "_", name.lower())
        if not safe_name:
            return {"error": "Invalid skill name"}

        skill_dir = self._skills_dir / safe_name
        if skill_dir.exists():
            return {"error": f"Skill '{safe_name}' already exists"}

        # Build SKILL.md
        frontmatter_lines = [
            "---",
            f"name: {safe_name}",
            f"description: {description}",
            f"always: {'true' if always else 'false'}",
        ]
        if homepage:
            frontmatter_lines.append(f"homepage: {homepage}")
        frontmatter_lines.append("---")
        frontmatter_lines.append("")

        full_content = "\n".join(frontmatter_lines) + content

        await self.hass.async_add_executor_job(
            self._create_skill_files, skill_dir, full_content
        )
        await self.refresh_cache()

        return {"success": True, "name": safe_name}

    async def update_skill(
        self,
        name: str,
        content: str | None = None,
        description: str | None = None,
        always: bool | None = None,
    ) -> dict[str, Any]:
        """Update an existing skill."""
        meta = self._cache.get(name)
        if not meta:
            return {"error": f"Skill '{name}' not found"}

        path = Path(meta["path"])
        current_content = await self.hass.async_add_executor_job(self._read_file, path)

        if content is not None:
            # Replace entire content (frontmatter + body)
            new_content = content
        else:
            # Update only frontmatter fields, keep body
            current_meta = self._parse_frontmatter(current_content)
            body = self._strip_frontmatter(current_content)

            if description is not None:
                current_meta["description"] = description
            if always is not None:
                current_meta["always"] = always

            frontmatter_lines = [
                "---",
                f"name: {name}",
                f"description: {current_meta.get('description', '')}",
                f"always: {'true' if current_meta.get('always') else 'false'}",
            ]
            if current_meta.get("homepage"):
                frontmatter_lines.append(f"homepage: {current_meta['homepage']}")
            frontmatter_lines.append("---")
            frontmatter_lines.append("")

            new_content = "\n".join(frontmatter_lines) + body

        await self.hass.async_add_executor_job(self._write_file, path, new_content)
        await self.refresh_cache()

        return {"success": True, "name": name}

    async def delete_skill(self, name: str) -> dict[str, Any]:
        """Delete a skill directory."""
        meta = self._cache.get(name)
        if not meta:
            return {"error": f"Skill '{name}' not found"}

        skill_dir = Path(meta["dir"])
        await self.hass.async_add_executor_job(self._delete_dir, skill_dir)
        await self.refresh_cache()

        return {"success": True, "name": name}

    async def toggle_skill(self, name: str, always: bool) -> dict[str, Any]:
        """Toggle a skill's always-on status."""
        return await self.update_skill(name, always=always)

    # ── Context building for system prompt ──

    async def get_always_skills_context(self) -> str:
        """Get the combined content of all always-on skills for system prompt injection."""
        parts = []
        for name, meta in self._cache.items():
            if meta.get("always"):
                body = await self.read_skill_body(name)
                if body and body.strip():
                    parts.append(f"### Skill: {name}\n\n{body.strip()}")

        return "\n\n---\n\n".join(parts) if parts else ""

    async def build_skills_summary(self) -> str:
        """Build XML summary of all available skills for system prompt."""
        if not self._cache:
            return ""

        def escape_xml(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        lines = ["<skills>"]
        for name, meta in self._cache.items():
            if meta.get("always"):
                continue  # Always-on skills already injected in full
            desc = escape_xml(meta.get("description", ""))
            lines.append(f'  <skill>')
            lines.append(f"    <name>{escape_xml(name)}</name>")
            lines.append(f"    <description>{desc}</description>")
            lines.append(f"  </skill>")
        lines.append("</skills>")

        return "\n".join(lines) if len(lines) > 2 else ""

    async def get_skills_context(self) -> str:
        """Build the full skills context for system prompt injection.

        Returns:
            Combined string with always-on skill bodies + XML summary of others.
        """
        parts = []

        # Always-on skills: full body
        always_content = await self.get_always_skills_context()
        if always_content:
            parts.append(always_content)

        # Other skills: XML summary
        summary = await self.build_skills_summary()
        if summary:
            framing = (
                "The following skills extend your capabilities. "
                "To use a skill, call the `read_skill` tool with the skill name.\n\n"
            )
            parts.append(framing + summary)

        return "\n\n---\n\n".join(parts) if parts else ""

    # ── Statistics ──

    async def get_stats(self) -> dict[str, Any]:
        """Get skills statistics."""
        total = len(self._cache)
        always_on = sum(1 for m in self._cache.values() if m.get("always"))
        return {
            "total_skills": total,
            "always_on_skills": always_on,
            "on_demand_skills": total - always_on,
            "skills_dir": str(self._skills_dir),
        }

    # ── Sync file helpers ──

    @staticmethod
    def _read_file(path: Path) -> str:
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    @staticmethod
    def _write_file(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _create_skill_files(skill_dir: Path, content: str) -> None:
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    @staticmethod
    def _delete_dir(path: Path) -> None:
        if path.exists():
            shutil.rmtree(path)
