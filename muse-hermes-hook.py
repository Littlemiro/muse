"""Read-only Hermes ``pre_llm_call`` adapter for MUSE.

Hermes invokes this file with a JSON hook payload on stdin.  The adapter does
one thing before the model sees a user turn: discover matching MUSE skills and
inspect the highest-scoring one.  It never executes a skill, calls a URL, or
changes approvals/releases.  Its stdout is exactly one JSON object so it can
be used as a Hermes shell hook.

Example Hermes configuration::

    hooks:
      pre_llm_call:
        - command: C:/Users/Administrator/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe C:/Users/Administrator/muse/muse-hermes-hook.py
          timeout: 20

The route catalog uses metadata fingerprints.  A new or changed skill causes
one full audit refresh; unchanged turns reuse the local cache.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


MAX_CONTEXT_CHARS = 24_000
MAX_INSPECT_CHARS = 18_000


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def load_console():
    path = Path(__file__).resolve().with_name("muse-console.py")
    spec = importlib.util.spec_from_file_location("muse_console_for_hermes_hook", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load MUSE console: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def message_from_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("user_message", "message", "prompt", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def compact(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n\n[inspect output truncated by Hermes adapter]"


def canonical_matches(console, records, task: str, limit: int = 3):
    """Keep the preferred source when the same skill is mirrored elsewhere."""
    selected = []
    seen = set()
    for score, record in console.route_matches(records, task, limit=max(limit * 4, 12)):
        # The user's chosen canonical source wins even when the mirrored copy
        # has drifted and therefore has a different content hash.
        key = record.name.casefold()
        if key in seen:
            continue
        seen.add(key)
        selected.append((score, record))
        if len(selected) >= limit:
            break
    return selected


def route_context(task: str, console) -> str:
    roots = console.default_roots()
    records, errors, refreshed = console.route_catalog(console.default_state_dir(), roots)
    matches = canonical_matches(console, records, task)
    lines = [
        "[MUSE AUTO-ROUTE]",
        "MUSE ran a read-only route before this model turn.",
        f"task: {task}",
        f"catalog: {'refreshed' if refreshed else 'cache-hit'}",
    ]
    if errors:
        lines.append("root_warnings: " + " | ".join(errors[:5]))
    if not matches:
        lines.append("matches: none; use the normal Hermes method if needed.")
        return "\n".join(lines)

    lines.append("route matches:")
    for index, (score, record) in enumerate(matches, 1):
        item = console.route_record(record, score)
        risk = ", ".join(item["risk_tags"]) or "none"
        lines.append(
            f"{index}. {item['name']} [{item['audit_status']}] "
            f"score={score} risk={risk} source={item['source']}"
        )
        lines.append(f"   path: {item['path']}")
        lines.append(f"   description: {item['description']}")

    score, record = matches[0]
    inspected = console.inspect_payload(record, include_scripts=False, acknowledge_risk=False)
    lines.extend([
        "",
        f"inspect: {inspected['name']} [{inspected['audit_status']}]",
        f"inspect path: {inspected['path']}",
        "inspect warnings: " + (" | ".join(inspected["warnings"]) or "none"),
        "",
        "--- inspected SKILL.md ---",
        compact(inspected.get("skill_md") or "SKILL.md could not be read.", MAX_INSPECT_CHARS),
        "--- end inspected SKILL.md ---",
        "",
        "MUSE has already performed route → inspect for this turn. "
        "Do not call Hermes skill_view for these matches; use the inspected content. "
        "MUSE is advisory and read-only: Hermes still controls execution approvals.",
    ])
    return compact("\n".join(lines), MAX_CONTEXT_CHARS)


def emit_context(context: str) -> int:
    print(json.dumps({"context": context}, ensure_ascii=False))
    return 0


def main() -> int:
    configure_stdio()
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        task = message_from_payload(payload)
        if not task or task.startswith("/"):
            return emit_context("[MUSE] No route needed for this command or empty turn.")
        console = load_console()
        return emit_context(route_context(task, console))
    except Exception as exc:  # The adapter must never block Hermes on a local catalog error.
        print(f"MUSE Hermes hook unavailable: {exc}", file=sys.stderr)
        return emit_context("[MUSE] Automatic route unavailable; continue with Hermes' normal skill discovery.")


if __name__ == "__main__":
    raise SystemExit(main())
