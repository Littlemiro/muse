#!/usr/bin/env python3
"""
MUSE MCP Bridge — expose Hermes MUSE skills as MCP Prompts.
Any MCP client (Codex, Reasonix, Claude Desktop, Cursor, etc.) can load skills.

Usage:
    python3 muse-mcp-server.py [--port 8768] [--skills-dir /path/to/skills]

Config env vars:
    MUSE_MCP_PORT (default: 8768)
    MUSE_MCP_HOST (default: 0.0.0.0)
    SKILLS_DIR    (default: auto-detect ~/.hermes/skills/ or your OS equivalent)
"""

import os, sys, re, argparse
from pathlib import Path
from typing import Any
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import Prompt
from mcp.server.fastmcp.prompts.base import Message
from mcp.types import TextContent

# ── Path resolution ──────────────────────────────────────────────────

def default_skills_dir() -> Path:
    """Platform-aware default skills directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("HERMES_HOME", "")) or \
               Path.home() / "AppData" / "Local" / "hermes"
    else:
        base = Path(os.environ.get("HERMES_HOME", "")) or \
               Path.home() / ".hermes"
    return base / "skills"

# ── Skill scanner ────────────────────────────────────────────────────

def find_all_skills(skills_dir: Path) -> list[dict[str, Any]]:
    """Scan skills directory for all SKILL.md files, return parsed list."""
    skills = []
    if not skills_dir.exists():
        print(f"[muse-mcp] WARNING: Skills dir not found: {skills_dir}", file=sys.stderr)
        return skills

    for sk_path in skills_dir.rglob("SKILL.md"):
        try:
            meta = parse_skill_md(sk_path)
            if meta and meta.get("name"):
                skills.append(meta)
        except Exception as e:
            print(f"[muse-mcp] Skipping {sk_path}: {e}", file=sys.stderr)

    skills.sort(key=lambda s: (s.get("category", ""), s["name"]))
    return skills

def parse_skill_md(path: Path) -> dict[str, Any] | None:
    """Parse a SKILL.md file, extract frontmatter + body."""
    raw = path.read_text("utf-8", errors="replace")
    fm_match = re.match(r"^---\s*\n(.*?)\n---", raw, re.DOTALL)
    if not fm_match:
        return None

    fm_text = fm_match.group(1)
    try:
        import yaml
        meta = yaml.safe_load(fm_text) or {}
    except Exception:
        meta = {}
        for line in fm_text.strip().split("\n"):
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip().strip("\"'")

    body_start = fm_match.end()
    body = raw[body_start:].strip()

    # Compute category path for display
    try:
        parts = path.parent.parts
        # Find where "skills" is in the path to get relative path
        for i, p in enumerate(parts):
            if p.lower() == "skills":
                rel_parts = parts[i+1:]
                break
        else:
            rel_parts = [path.parent.name]
    except Exception:
        rel_parts = [path.parent.name]

    skill_info = {
        "name": str(meta.get("name", path.parent.name)),
        "description": str(meta.get("description", "")),
        "version": str(meta.get("version", "0.0.0")),
        "author": str(meta.get("author", "unknown")),
        "category": str(meta.get("metadata", {}).get("hermes", {}).get("category", "")),
        "tags": meta.get("metadata", {}).get("hermes", {}).get("tags", []),
        "trigger_keywords": meta.get("trigger_keywords", []),
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

def create_mcp_server(skills_dir: Path, host: str = "0.0.0.0", port: int = 8768) -> FastMCP:
    """Create a FastMCP server exposing skills as prompts."""
    skills_list = find_all_skills(skills_dir)
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
            q = query.lower()
            results = [s for s in results if q in s["name"].lower() or q in s["description"].lower() or q in str(s["tags"]).lower() or q in s["category"].lower()]
        if category:
            results = [s for s in results if s["category"].lower() == category.lower()]
        if tag:
            results = [s for s in results if tag.lower() in [t.lower() for t in s["tags"]]]

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
    parser = argparse.ArgumentParser(description="MUSE MCP Bridge — expose Hermes skills as MCP prompts")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MUSE_MCP_PORT", "8768")),
                        help="Port to listen on (default: 8768, or $MUSE_MCP_PORT)")
    parser.add_argument("--skills-dir", type=str, default=os.environ.get("SKILLS_DIR", ""),
                        help="Path to skills directory (default: auto-detect)")
    parser.add_argument("--host", type=str, default=os.environ.get("MUSE_MCP_HOST", "0.0.0.0"),
                        help="Host to bind (default: 0.0.0.0)")
    args = parser.parse_args()

    skills_dir = Path(args.skills_dir) if args.skills_dir else default_skills_dir()
    print(f"[muse-mcp] Starting on {args.host}:{args.port}", file=sys.stderr)
    print(f"[muse-mcp] Skills dir: {skills_dir}", file=sys.stderr)

    server = create_mcp_server(skills_dir, host=args.host, port=args.port)
    server.run(transport="streamable-http")

if __name__ == "__main__":
    main()
