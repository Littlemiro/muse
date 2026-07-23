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

import os, sys, re, argparse
from pathlib import Path
from typing import Any

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

    if not isinstance(meta, dict):
        meta = {}

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
        tags = [str(item) for item in tags]
    trigger_keywords = meta.get("trigger_keywords", [])
    if not isinstance(trigger_keywords, list):
        trigger_keywords = []
    else:
        trigger_keywords = [str(item) for item in trigger_keywords]

    skill_info = {
        "name": str(meta.get("name", path.parent.name)),
        "description": str(meta.get("description", "")),
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
