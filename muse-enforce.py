#!/usr/bin/env python3
"""
MUSE Enforcer — run against a skills/ directory to bring all SKILL.md files
up to MUSE frontmatter standards.

Usage:
    python3 muse-enforce.py <skills-dir> [--dry-run]

What it does:
  1. Reads every SKILL.md in the directory tree
  2. Parses frontmatter with YAML-safe preprocessing (handles colons in values)
  3. Checks MUSE mandatory fields (name, description)
  4. Auto-fills recommended fields when missing:
     - version → "0.1.0"
     - author → "Hermes Agent"
     - license → "MIT"
     - platforms → ["linux", "macos", "windows"]
     - metadata.hermes.tags → inferred from category + description
     - trigger_keywords → inferred from name + category + description
     - metadata.hermes.related_skills → from same-category + tag overlap
  5. Fixes description quality (imperative, ≤64 chars where possible)
  6. Generates an audit report and returns a summary

Requirements: Python 3.10+ (yaml, pathlib)
"""

import re
import sys
import yaml
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────

FM_RE = re.compile(r'^---\s*\r?\n(.*?)\r?\n---', re.DOTALL)

IMPERATIVE_VERBS = {
    "use", "create", "configure", "set", "build", "run", "deploy",
    "manage", "debug", "diagnose", "monitor", "search", "extract",
    "control", "generate", "convert", "fix", "test", "write",
    "play", "track", "develop", "install", "author", "poll",
    "edit", "operate", "freeze", "design", "send", "read",
    "backup", "query", "clone", "review", "plan", "spawn",
    "author/validate", "host", "synthesize", "take", "jailbreak",
    "modify", "prepare", "post-processing", "research",
    "navigate", "drive", "maintain", "administer", "reference",
    "investigate", "extract", "report", "discover",
    "plan", "parse", "subscribe", "analyze", "apply",
}

CATEGORY_TAGS = {
    "autonomous-ai-agents": ["ai-agents", "delegation"],
    "apple": ["apple", "macos"],
    "content-creator-video-pipeline": ["content-creation", "video-pipeline"],
    "creative": ["creative", "design"],
    "data-science": ["data-science", "analysis"],
    "devops": ["devops", "infrastructure"],
    "dogfood": ["qa", "testing"],
    "email": ["email"],
    "food-science": ["cooking", "food"],
    "gaming": ["gaming"],
    "gao-economic-logic": ["economics", "knowledge-base"],
    "github": ["github", "git"],
    "linux-command-ref": ["linux", "reference"],
    "mcp": ["mcp", "protocol"],
    "media": ["media", "audio-video"],
    "mlops": ["mlops", "machine-learning"],
    "moviepilot-ops": ["moviepilot", "pt"],
    "nas-investigation-workflow": ["nas", "troubleshooting"],
    "note-taking": ["note-taking", "obsidian"],
    "productivity": ["productivity", "automation"],
    "pt-smart-seeder": ["pt", "seeding"],
    "red-teaming": ["red-teaming", "security"],
    "research": ["research", "academic"],
    "smart-home": ["smart-home", "iot"],
    "social-media": ["social-media", "twitter"],
    "software-development": ["development", "tools"],
    "watchers": ["monitoring", "rss"],
    "windows-powershell-ref": ["windows", "powershell"],
    "yuanbao": ["yuanbao", "wechat"],
}

EXTRA_TAG_WORDS = {
    "cli": "cli", "api": "api", "docker": "docker", "nas": "nas",
    "git": "git", "ssh": "ssh", "mcp": "mcp", "backup": "backup",
    "search": "search", "monitor": "monitoring", "automation": "automation",
    "debug": "debugging", "jupyter": "jupyter", "pdf": "pdf",
    "youtube": "youtube", "wechat": "wechat", "obsidian": "obsidian",
}

# ── Frontmatter helpers ───────────────────────────────────────────

def preprocess_fm(text):
    """Wrap description values containing ':' in quotes before YAML parse."""
    lines = text.split('\n')
    new_lines = []
    for line in lines:
        m = re.match(r'^(\s*)description:\s*(.*)', line)
        if m:
            indent = m.group(1)
            value = m.group(2).strip()
            if any(ch in value for ch in [': ', '#', '[', ']', '{', '}', ',', '&', '*', '?', '|', '!', '%', '@', '`']):
                if not (value.startswith('"') and value.endswith('"')):
                    escaped = value.replace('"', '\\"')
                    new_lines.append(f'{indent}description: "{escaped}"')
                    continue
        new_lines.append(line)
    return '\n'.join(new_lines)


def needs_quoting(val):
    if not isinstance(val, str):
        return False
    return any(ch in val for ch in [': ', ':', '#', '[', ']', '{', '}', ',', '&', '*', '?', '|', '!', '%', '@', '`'])


def dict_to_yaml(d):
    """Serialize a dict to YAML frontmatter, properly quoting values with YAML special chars."""
    lines = ["---"]
    for k, v in d.items():
        if isinstance(v, list):
            if not v:
                lines.append(f"{k}:")
            else:
                lines.append(f"{k}:")
                for item in v:
                    sv = str(item) if not isinstance(item, str) else item
                    if isinstance(item, str) and needs_quoting(item):
                        sv = '"' + item.replace('"', '\\"') + '"'
                    lines.append(f"  - {sv}")
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif v is None:
            lines.append(f"{k}:")
        elif isinstance(v, (int, float)):
            lines.append(f"{k}: {v}")
        elif isinstance(v, str):
            if needs_quoting(v):
                escaped = v.replace('"', '\\"')
                lines.append(f'{k}: "{escaped}"')
            else:
                lines.append(f"{k}: {v}")
        elif isinstance(v, dict):
            flow = yaml.dump(v, default_flow_style=True, allow_unicode=True, width=float('inf')).strip()
            lines.append(f"{k}: {flow}")
        else:
            lines.append(f"{k}: {str(v)}")
    lines.append("---")
    return "\n".join(lines)


# ── Inference ──────────────────────────────────────────────────────

def infer_keywords(name, cat, desc, body):
    keywords = []
    parts = re.split(r'[-_\s]', name)
    keywords.extend(p for p in parts if len(p) > 1 and p.lower() not in ['for', 'the', 'and', 'with'])
    cat_parts = re.split(r'[-_\s]', cat)
    keywords.extend(p for p in cat_parts if len(p) > 1 and p not in keywords)
    if desc:
        dl = desc.lower()
        for kw in ['cli', 'api', 'docker', 'nas', 'git', 'github', 'ssh', 'vps',
                    'pdf', 'mcp', 'obsidian', 'wiki', 'exa', 'rss',
                    'jellyfin', 'moviepilot', 'pt', 'bilibili', 'wechat',
                    'youtube', 'spotify', 'linux', 'windows', 'python',
                    'llm', 'rag', 'tui', 'terminal', 'cron', 'webhook',
                    'apple', 'imessage', 'opencli', 'polymarket', 'arxiv']:
            if kw in dl and kw not in keywords:
                keywords.append(kw)
    return list(dict.fromkeys(keywords))


def infer_tags(cat, name, desc):
    tags = list(CATEGORY_TAGS.get(cat, [cat]))
    if desc:
        dl = desc.lower()
        for word, tag in EXTRA_TAG_WORDS.items():
            if word in dl and tag not in tags:
                tags.append(tag)
    return tags[:6]


def improve_desc(current_desc, name, cat, body):
    """Return (new_desc, changed) — makes description imperative and ≤64 chars."""
    if not current_desc or not isinstance(current_desc, str):
        current_desc = ""
    desc = current_desc.strip().strip('"\'').strip()
    if not desc:
        return current_desc, False

    original = desc

    # Already good?
    first_word = desc.split()[0].lower() if desc.split() else ""
    if (first_word in IMPERATIVE_VERBS or desc.startswith(first_word.upper())) and len(desc) <= 64:
        return desc, False

    # Try body extraction
    body_stripped = body.strip()
    lines = [l.strip() for l in body_stripped.split('\n') if l.strip()]

    # Find first # heading
    heading = ""
    for l in lines:
        sl = l.strip()
        if sl.startswith('# ') and not sl.startswith('## '):
            heading = sl.lstrip('# ').strip()
            break

    # Find first substantial sentence
    for l in lines:
        sl = l.strip()
        if not sl or sl.startswith('```') or sl.startswith('---') or sl.startswith('> '):
            continue
        clean = re.sub(r'[#*_`>]', '', sl).strip()
        if len(clean) < 15 or clean.startswith('- ') or clean.startswith('http'):
            continue
        if clean.startswith('$') or clean.startswith('```'):
            continue
        sentence = clean.split('.')[0].strip()
        if 20 <= len(sentence) <= 64:
            return sentence, True
        elif len(sentence) > 64:
            return sentence[:61] + "...", True

    # Fallback to heading
    if heading:
        if len(heading) <= 64:
            return heading, True
        return heading[:61] + "...", True

    # Last resort — truncate current
    cleaned = desc
    for prefix in ["a ", "an ", "the "]:
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    if len(cleaned) > 64:
        cleaned = cleaned[:61] + "..."
    return cleaned, cleaned != original


# ── Main ───────────────────────────────────────────────────────────

def enforce(skills_dir, dry_run=False):
    skills_dir = Path(skills_dir)
    if not skills_dir.is_dir():
        print(f"ERROR: {skills_dir} is not a directory")
        return

    # Collect all skill metadata for cross-referencing
    all_skills = []
    for skill_path in sorted(skills_dir.rglob("SKILL.md")):
        text = skill_path.read_text(encoding='utf-8')
        cat = skill_path.parent.parent.name
        name = skill_path.parent.name

        m = FM_RE.match(text)
        if not m:
            continue
        fm_raw = preprocess_fm(m.group(1))
        try:
            fm = yaml.safe_load(fm_raw)
        except:
            continue
        if not isinstance(fm, dict):
            continue

        body = text[m.end():].strip()
        desc = fm.get("description", "") or ""
        tags = infer_tags(cat, name, desc)
        all_skills.append({
            "path": skill_path, "cat": cat, "name": name,
            "desc": desc, "tags": tags, "fm": fm, "body": body
        })

    # Enforce
    report = []
    changes = {"trigger": 0, "desc": 0, "tags": 0, "author": 0,
               "license": 0, "platforms": 0, "related": 0}

    for s in all_skills:
        changed = False
        fm = s["fm"]
        body = s["body"]

        # 1. Description quality
        new_desc, dc = improve_desc(s["desc"], s["name"], s["cat"], body)
        if dc:
            fm["description"] = new_desc
            changes["desc"] += 1
            changed = True

        # 2. Trigger keywords
        if not fm.get("trigger_keywords"):
            kw = infer_keywords(s["name"], s["cat"], new_desc or s["desc"], body)
            if kw:
                fm["trigger_keywords"] = kw[:10]
                changes["trigger"] += 1
                changed = True

        # 3. Metadata tags
        meta = fm.get("metadata")
        if isinstance(meta, str):
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        hermes = meta.get("hermes", {})
        if not isinstance(hermes, dict):
            hermes = {}

        tags = infer_tags(s["cat"], s["name"], new_desc or s["desc"])
        if not hermes.get("tags"):
            hermes["tags"] = tags
            changes["tags"] += 1
            changed = True

        # 4. Related skills
        if not hermes.get("related_skills"):
            my_tags = set(tags)
            candidates = []
            for other in all_skills:
                if other["name"] == s["name"]:
                    continue
                if other["cat"] == s["cat"]:
                    candidates.append(other["name"])
                elif len(set(other["tags"]) & my_tags) >= 2:
                    if other["name"] not in candidates:
                        candidates.append(other["name"])
            if candidates:
                hermes["related_skills"] = candidates[:5]
                changes["related"] += 1
                changed = True

        if hermes:
            meta["hermes"] = hermes
        fm["metadata"] = meta

        # 5-7. Author, license, platforms
        if not fm.get("author"):
            fm["author"] = "Hermes Agent"
            changes["author"] += 1
            changed = True
        if not fm.get("license"):
            fm["license"] = "MIT"
            changes["license"] += 1
            changed = True
        if not fm.get("platforms"):
            fm["platforms"] = ["linux", "macos", "windows"]
            changes["platforms"] += 1
            changed = True

        if changed and not dry_run:
            body_written = s["path"].read_text(encoding='utf-8')
            m2 = FM_RE.match(body_written)
            body_clean = body_written[m2.end():].strip() if m2 else body_written
            s["path"].write_text(dict_to_yaml(fm) + "\n" + body_clean, encoding='utf-8')
            report.append(f"  ✎ [{s['cat']}] {s['name']}")
        elif changed:
            report.append(f"  ◇ [{s['cat']}] {s['name']} (--dry-run)")

    print(f"Skills dir: {skills_dir}")
    print(f"Total SKILL.md files: {len(all_skills)}")
    print(f"Dry run: {dry_run}")
    print(f"\nChanges:")
    for k, v in changes.items():
        print(f"  {k}: {v}")
    if report:
        print(f"\nSkills modified:")
        for r in report:
            print(r)
    else:
        print("\nNo changes needed — all skills MUSE-compliant.")

    # Audit summary
    fields = {k: 0 for k in ["version", "author", "license", "platforms",
                              "meta_tags", "meta_related", "trigger"]}
    for s in all_skills:
        fm = s["fm"]
        if fm.get("version"): fields["version"] += 1
        if fm.get("author"): fields["author"] += 1
        if fm.get("license"): fields["license"] += 1
        if fm.get("platforms"): fields["platforms"] += 1
        meta = fm.get("metadata", {})
        if isinstance(meta, dict):
            h = meta.get("hermes", {})
            if isinstance(h, dict):
                if h.get("tags"): fields["meta_tags"] += 1
                if h.get("related_skills"): fields["meta_related"] += 1
        if fm.get("trigger_keywords"): fields["trigger"] += 1

    total = len(all_skills)
    print(f"\nMUSE Audit ({total} skills):")
    for k, v in fields.items():
        pct = v * 100 // total
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"  {k:15s} {bar} {v:3d}/{total} ({pct}%)")

    desc_imperative = sum(1 for s in all_skills
                          if s["fm"].get("description","").strip().split()[0].lower() in IMPERATIVE_VERBS)
    desc_short = sum(1 for s in all_skills
                     if len(s["fm"].get("description","").strip()) <= 64)
    print(f"\n  Description imperative: {desc_imperative:3d}/{total} ({desc_imperative*100//total}%)")
    print(f"  Description ≤64 chars: {desc_short:3d}/{total} ({desc_short*100//total}%)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 muse-enforce.py <skills-dir> [--dry-run]")
        sys.exit(1)
    dry = "--dry-run" in sys.argv
    enforce(sys.argv[1], dry_run=dry)
