#!/usr/bin/env python3
"""
MUSE MCP Bridge — expose Hermes MUSE skills as MCP Prompts.
Any MCP client (Codex, Reasonix, Claude Desktop, Cursor, etc.) can load skills.

Usage:
    python3 muse-mcp-server.py [--port 8768] [--skills-dir /path/to/skills]

Config env vars:
    MUSE_MCP_PORT (default: 8768)
    MUSE_MCP_HOST (default: 127.0.0.1; remote binding requires --allow-insecure-remote)
    SKILLS_DIR    (default: auto-detect ~/.hermes/.muse/active/current/)
"""

import argparse
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - installation error
    raise SystemExit("MUSE MCP bridge requires PyYAML. Install requirements.txt first.") from exc


FRONTMATTER_RE = re.compile(r"^---\s*\r?\n(.*?)\r?\n---(?:\r?\n|$)", re.DOTALL)
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
MAX_SKILL_MD_BYTES = 4 * 1024 * 1024

# ── Path resolution ──────────────────────────────────────────────────

def hermes_home() -> Path:
    raw = os.environ.get("HERMES_HOME", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".hermes"


def default_skills_dir() -> Path:
    """Use only the MUSE-approved activation directory by default."""
    return hermes_home() / ".muse" / "active" / "current"


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def is_approved_export(path: Path) -> bool:
    candidate = path.expanduser().resolve()
    approved = default_skills_dir().resolve()
    return is_within(candidate, approved)

# ── Skill scanner ────────────────────────────────────────────────────

def find_all_skills(skills_dir: Path) -> list[dict[str, Any]]:
    """Scan skills directory for all SKILL.md files, return parsed list."""
    skills = []
    seen_names: set[str] = set()
    if not skills_dir.exists():
        print(f"[muse-mcp] WARNING: Skills dir not found: {skills_dir}", file=sys.stderr)
        return skills

    root = skills_dir.resolve()
    for sk_path in skills_dir.rglob("SKILL.md"):
        try:
            resolved = sk_path.resolve(strict=True)
            if sk_path.is_symlink() or not resolved.is_file() or not resolved.is_relative_to(root):
                print(f"[muse-mcp] Skipping out-of-root or linked skill: {sk_path}", file=sys.stderr)
                continue
            meta = parse_skill_md(sk_path)
            if not meta:
                print(f"[muse-mcp] Skipping invalid skill document: {sk_path}", file=sys.stderr)
                continue
            name = meta["name"]
            if name in seen_names:
                print(f"[muse-mcp] Skipping duplicate skill name: {name}", file=sys.stderr)
                continue
            seen_names.add(name)
            skills.append(meta)
        except Exception as e:
            print(f"[muse-mcp] Skipping {sk_path}: {e}", file=sys.stderr)

    skills.sort(key=lambda s: (s.get("category", ""), s["name"]))
    return skills

def parse_skill_md(path: Path) -> dict[str, Any] | None:
    """Parse a SKILL.md file, extract frontmatter + body."""
    try:
        file_stat = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(file_stat.st_mode):
            return None
        if file_stat.st_size > MAX_SKILL_MD_BYTES:
            return None
        raw = path.read_text("utf-8", errors="replace")
    except OSError:
        return None

    fm_match = FRONTMATTER_RE.match(raw)
    if not fm_match:
        return None

    try:
        meta = yaml.safe_load(fm_match.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(meta, dict):
        return None

    body_start = fm_match.end()
    body = raw[body_start:].strip()
    name_value = meta.get("name")
    description_value = meta.get("description")
    name = name_value.strip() if isinstance(name_value, str) else ""
    description = description_value.strip() if isinstance(description_value, str) else ""
    if not name or not NAME_RE.fullmatch(name) or not description or not body:
        return None

    # Compute category path for display
    parts = path.parent.parts
    skills_index = next((i for i, part in enumerate(parts) if part.lower() == "skills"), None)
    rel_parts = parts[skills_index + 1:] if skills_index is not None else (path.parent.name,)

    metadata = meta.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    hermes = metadata.get("hermes", {})
    if not isinstance(hermes, dict):
        hermes = {}

    tags = hermes.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    else:
        tags = [str(item).strip() for item in tags if str(item).strip()]
    trigger_keywords = meta.get("trigger_keywords", [])
    if not isinstance(trigger_keywords, list):
        trigger_keywords = []
    else:
        trigger_keywords = [str(item).strip() for item in trigger_keywords if str(item).strip()]

    skill_info = {
        "name": name,
        "description": description,
        "version": str(meta.get("version", "0.0.0")),
        "author": str(meta.get("author", "unknown")),
        "category": str(hermes.get("category", "")),
        "tags": tags,
        "trigger_keywords": trigger_keywords,
        "body": body,
        "path": str(path),
        "rel_path": "/".join(rel_parts),
    }
    return skill_info

def build_prompt_text(skill: dict[str, Any]) -> str:
    """Build the full prompt text from a skill's metadata + body."""
    header = f"""# {skill['name']}

{skill['description']}

**Version:** {skill['version']}  |  **Author:** {skill['author']}  |  **Category:** {skill['category'] or 'uncategorized'}  |  **Path:** {skill['rel_path']}

"""
    if skill["tags"]:
        header += f"**Tags:** {', '.join(skill['tags'])}\n\n"
    if skill["trigger_keywords"]:
        header += f"**Trigger keywords:** {', '.join(skill['trigger_keywords'])}\n\n"

    return header + skill["body"]

# ── MCP Server ───────────────────────────────────────────────────────

def create_mcp_server(skills_dir: Path, host: str = "127.0.0.1", port: int = 8768) -> Any:
    """Create a FastMCP server exposing skills as prompts."""
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.prompts import Prompt
        from mcp.server.fastmcp.prompts.base import Message
        from mcp.types import TextContent
    except ImportError as exc:
        raise SystemExit("MCP bridge requires the optional dependencies in requirements.txt") from exc

    skills_list = find_all_skills(skills_dir)
    for skill in skills_list:
        skill["_search_text"] = " ".join(
            [skill["name"], skill["description"], skill["category"], *skill["tags"], *skill["trigger_keywords"]]
        ).casefold()
        skill["_category_key"] = skill["category"].casefold()
        skill["_tag_keys"] = {tag.casefold() for tag in skill["tags"]}
    print(f"[muse-mcp] Loaded {len(skills_list)} skills from {skills_dir}", file=sys.stderr)

    server = FastMCP(
        "muse-mcp-bridge",
        host=host,
        port=port,
        instructions=f"""MUSE Skill Bridge — {len(skills_list)} Hermes skills available as prompts.

This server exposes MUSE (Hermes Agent's skill system) skills as MCP prompts.
Each prompt contains a complete skill document that the agent can follow.

To use a skill: call `prompts/get` with the skill name.
To browse available skills: call `prompts/list`.
""",
    )

    # ── Register each skill as a prompt ──────────────────────────

    for sk in skills_list:
        name = sk["name"]
        desc = sk["description"][:120] if sk["description"] else f"A skill for {name}"
        prompt_text = build_prompt_text(sk)

        def make_prompt_fn(text: str):
            def fn() -> list[Message]:
                return [Message(
                    role="user",
                    content=TextContent(type="text", text=f"Follow this skill:\n\n{text}")
                )]
            return fn

        prompt = Prompt(
            name=name,
            description=desc,
            fn=make_prompt_fn(prompt_text),
        )
        server.add_prompt(prompt)

    # ── Tool: search skills ──────────────────────────────────────

    @server.tool()
    def search_skills(query: str = "", category: str = "", tag: str = "") -> str:
        """Search available skills by name, description, category, or tag.
        
        Args:
            query: Free-text search in name and description
            category: Filter by category name
            tag: Filter by tag
        """
        results = skills_list
        if query:
            results = [s for s in results if query.casefold() in s["_search_text"]]
        if category:
            results = [s for s in results if s["_category_key"] == category.casefold()]
        if tag:
            results = [s for s in results if tag.casefold() in s["_tag_keys"]]

        if not results:
            return "No skills found matching your criteria."

        lines = [f"# Found {len(results)} skills\n"]
        for s in results:
            lines.append(f"## {s['name']}")
            lines.append(f"- **Description:** {s['description']}")
            lines.append(f"- **Category:** {s['category'] or 'uncategorized'}")
            lines.append(f"- **Tags:** {', '.join(s['tags']) if s['tags'] else 'none'}")
            lines.append(f"- **Version:** {s['version']}")
            lines.append(f"- **Author:** {s['author']}")
            lines.append("")
        return "\n".join(lines)

    @server.tool()
    def skill_stats() -> str:
        """Get summary statistics of all loaded skills."""
        cats = {}
        for s in skills_list:
            c = s["category"] or "uncategorized"
            cats[c] = cats.get(c, 0) + 1

        lines = [f"# MUSE Skill Stats\n"]
        lines.append(f"**Total skills:** {len(skills_list)}")
        lines.append(f"\n## By Category\n")
        for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
            lines.append(f"- **{cat}:** {count}")
        return "\n".join(lines)

    return server

# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MUSE MCP Bridge - expose Hermes skills as MCP prompts")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MUSE_MCP_PORT", "8768")),
                        help="Port to listen on (default: 8768, or $MUSE_MCP_PORT)")
    parser.add_argument("--skills-dir", type=str, default=os.environ.get("SKILLS_DIR", ""),
                        help="Path to skills directory (default: auto-detect)")
    parser.add_argument("--allow-unapproved-source", action="store_true",
                        help="Allow serving a directory outside MUSE active/current; review it first")
    parser.add_argument("--host", type=str, default=os.environ.get("MUSE_MCP_HOST", "127.0.0.1"),
                        help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--allow-insecure-remote", action="store_true",
                        help="Allow non-loopback HTTP binding without built-in auth; use only behind a trusted reverse proxy")
    args = parser.parse_args()

    if args.host.lower() not in {"127.0.0.1", "localhost", "::1"} and not args.allow_insecure_remote:
        parser.error("Refusing non-loopback binding without --allow-insecure-remote")
    if args.allow_insecure_remote and args.host.lower() not in {"127.0.0.1", "localhost", "::1"}:
        print("[muse-mcp] WARNING: remote HTTP binding has no built-in authentication; put it behind a trusted authenticated proxy", file=sys.stderr)

    skills_dir = Path(args.skills_dir) if args.skills_dir else default_skills_dir()
    if not args.allow_unapproved_source and not is_approved_export(skills_dir):
        parser.error("Refusing to expose a non-approved source; use MUSE active/current or explicitly pass --allow-unapproved-source")
    print(f"[muse-mcp] Starting on {args.host}:{args.port}", file=sys.stderr)
    print(f"[muse-mcp] Skills dir: {skills_dir}", file=sys.stderr)

    server = create_mcp_server(skills_dir, host=args.host, port=args.port)
    server.run(transport="streamable-http")

if __name__ == "__main__":
    main()
