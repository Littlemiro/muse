#!/usr/bin/env python3
"""
MUSE local console for Hermes skill assets.

The console deliberately stays outside Hermes' reasoning and learning loop.
It discovers skills, audits them, records human approvals, composes Hermes
bundles, and exports an approved set into a versioned directory that Hermes
can consume through ``skills.external_dirs``.

No command in this file fetches URLs or executes skill scripts.  ``apply``
copies only audited, approved skill directories and keeps immutable release
copies so that ``rollback`` can restore an earlier approved set.

Examples:
    python3 muse-console.py audit --root ~/.hermes/skills
    python3 muse-console.py route "repair jellyfin" --json
    python3 muse-console.py inspect jellyfin-repair
    python3 muse-console.py approve my-skill --ack-risk
    python3 muse-console.py bundle
    python3 muse-console.py apply --target ~/.hermes/.muse/active
    python3 muse-console.py config --target ~/.hermes/.muse/active
    python3 muse-console.py rollback --target ~/.hermes/.muse/active
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

try:
    import yaml
except ImportError as exc:  # pragma: no cover - exercised by installation errors
    raise SystemExit("MUSE console requires PyYAML. Install requirements.txt first.") from exc


VERSION = "0.1.0"
FRONTMATTER_RE = re.compile(r"^---\s*\r?\n(.*?)\r?\n---(?:\r?\n|$)", re.DOTALL)
URL_RE = re.compile(r'''https?://[^\s<>"'`)\]]+''', re.IGNORECASE)
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SCRIPT_SUFFIXES = {
    ".bat", ".bash", ".cmd", ".js", ".mjs", ".pl", ".ps1", ".py",
    ".rb", ".sh", ".sql", ".ts", ".vbs", ".zsh",
}
TEXT_SUFFIXES = {
    ".conf", ".csv", ".ini", ".json", ".md", ".rst", ".sh", ".sql",
    ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml", ".py", ".js",
    ".mjs", ".ps1", ".bat", ".cmd", ".zsh", ".bash",
}
MAX_INSPECT_BYTES = 2 * 1024 * 1024
MAX_SKILL_MD_BYTES = 4 * 1024 * 1024
MAX_INSPECT_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_INSPECT_SCRIPT_BYTES = 256 * 1024
REFACTOR_MAX_LINES = 500
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
REFERENCE_TOKEN_RE = re.compile(r"(?<![\w/])references/[A-Za-z0-9._/-]+")
RISK_TAG_BY_FINDING = {
    "remote_pipe_exec": {"network", "script"},
    "powershell_pipe_exec": {"network", "script"},
    "encoded_powershell": {"script"},
    "destructive_delete": {"destructive", "filesystem"},
    "destructive_format": {"destructive", "filesystem"},
    "force_push": {"destructive", "network"},
    "world_writable": {"filesystem"},
    "scripts_present": {"script"},
    "external_links": {"network"},
    "private_key": {"api_key"},
    "github_token": {"api_key"},
    "openai_key": {"api_key"},
    "aws_access_key": {"api_key"},
    "path_escape": {"filesystem"},
    "symlink_present": {"filesystem"},
    "special_file": {"filesystem"},
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def safe_home() -> Path:
    """Resolve Hermes home using Hermes' native platform defaults."""
    raw = os.environ.get("HERMES_HOME", "").strip()
    if raw:
        return Path(raw).expanduser()

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data).expanduser() / "hermes"

    return Path.home() / ".hermes"


def default_state_dir() -> Path:
    return safe_home() / ".muse"


def normalize_path(path: Path) -> Path:
    return path.expanduser().resolve()


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def redact(text: str, limit: int = 160) -> str:
    """Keep audit evidence useful without persisting credential-like values."""
    value = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1<redacted>", text)
    value = re.sub(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+", r"\1=<redacted>", value)
    value = re.sub(r"(?:sk|ghp|github_pat|AKIA)[A-Za-z0-9_\-]{12,}", "<redacted-token>", value)
    value = value.replace("\x00", "")
    return value[:limit]


def safe_url(value: str) -> str:
    """Keep host/path for review but never persist URL credentials."""
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        if parts.port:
            host = f"{host}:{parts.port}"
        return urlunsplit((parts.scheme, host, parts.path or "/", "", ""))
    except ValueError:
        return "<invalid-url>"


def export_category(value: str) -> str:
    """Turn a display category into a single safe release-directory name."""
    slug = re.sub(r"[^a-z0-9._-]+", "-", str(value).strip().lower())
    slug = slug.strip(".-")
    return slug or "uncategorized"


@dataclass
class Finding:
    code: str
    severity: str
    message: str
    file: str = ""
    evidence: str = ""

    def to_dict(self) -> dict[str, str]:
        value = {
            "code": self.code,
            "severity": self.severity,
            "message": redact(self.message),
        }
        if self.file:
            value["file"] = self.file
        if self.evidence:
            value["evidence"] = redact(self.evidence)
        return value


@dataclass
class SkillRecord:
    skill_id: str
    name: str
    description: str
    root: str
    skill_dir: str
    rel_dir: str
    category: str
    tags: list[str]
    version: str
    content_hash: str
    file_count: int
    urls: list[str] = field(default_factory=list)
    script_files: list[str] = field(default_factory=list)
    symlink_files: list[str] = field(default_factory=list)
    declared_risk: str = ""
    observed_risk: str = "low"
    findings: list[Finding] = field(default_factory=list)

    @property
    def audit_status(self) -> str:
        if any(item.severity == "critical" for item in self.findings):
            return "critical"
        if self.findings:
            return "needs_review"
        return "ready"

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": redact(self.description, 1024),
            "root": self.root,
            "skill_dir": self.skill_dir,
            "rel_dir": self.rel_dir,
            "category": self.category,
            "tags": self.tags,
            "version": self.version,
            "content_hash": self.content_hash,
            "file_count": self.file_count,
            "urls": self.urls,
            "script_files": self.script_files,
            "symlink_files": self.symlink_files,
            "declared_risk": self.declared_risk,
            "observed_risk": self.observed_risk,
            "audit_status": self.audit_status,
            "findings": [item.to_dict() for item in self.findings],
        }


def add_finding(items: list[Finding], code: str, severity: str, message: str,
                file: str = "", evidence: str = "") -> None:
    items.append(Finding(code, severity, message, file, redact(evidence)))


def parse_skill_file(path: Path) -> tuple[dict[str, Any], str, list[Finding]]:
    findings: list[Finding] = []
    try:
        file_stat = path.lstat()
        if not stat.S_ISREG(file_stat.st_mode):
            add_finding(findings, "special_file", "critical", "SKILL.md must be a regular file", str(path))
            return {}, "", findings
        if file_stat.st_size > MAX_SKILL_MD_BYTES:
            add_finding(findings, "skill_md_too_large", "critical", "SKILL.md exceeds the safe parsing limit", str(path))
            return {}, "", findings
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        add_finding(findings, "read_error", "critical", f"Cannot read SKILL.md: {exc}", str(path))
        return {}, "", findings

    match = FRONTMATTER_RE.match(raw)
    if not match:
        add_finding(findings, "frontmatter_missing", "critical", "SKILL.md has no valid YAML frontmatter", str(path))
        return {}, raw, findings

    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        add_finding(findings, "frontmatter_invalid", "critical", f"YAML frontmatter is invalid: {exc}", str(path))
        metadata = {}
    if not isinstance(metadata, dict):
        add_finding(findings, "frontmatter_type", "critical", "Frontmatter must be a mapping", str(path))
        metadata = {}
    return metadata, raw[match.end():].strip(), findings


def metadata_mapping(metadata: dict[str, Any], key: str) -> dict[str, Any]:
    value = metadata.get(key, {})
    return value if isinstance(value, dict) else {}


def string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def iter_files(skill_dir: Path) -> tuple[list[Path], list[Path], list[Path]]:
    files: list[Path] = []
    symlinks: list[Path] = []
    special: list[Path] = []
    for current, directories, names in os.walk(skill_dir, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_dirs: list[str] = []
        for directory in directories:
            candidate = current_path / directory
            if candidate.is_symlink():
                symlinks.append(candidate)
            else:
                kept_dirs.append(directory)
        directories[:] = kept_dirs
        for name in names:
            candidate = current_path / name
            if candidate.is_symlink():
                symlinks.append(candidate)
                continue
            try:
                mode = candidate.lstat().st_mode
            except OSError:
                special.append(candidate)
            else:
                if stat.S_ISREG(mode):
                    files.append(candidate)
                else:
                    special.append(candidate)
    return files, symlinks, special


def inspect_text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_INSPECT_BYTES:
            return ""
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != "SKILL.md":
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


DANGEROUS_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("remote_pipe_exec", "critical", r"(?i)\b(curl|wget)\b[^\n|]*\|\s*(ba)?sh\b"),
    ("powershell_pipe_exec", "critical", r"(?i)(invoke-webrequest|iwr|irm)[^\n|]*\|\s*(iex|invoke-expression)\b"),
    ("encoded_powershell", "critical", r"(?i)\bpowershell(?:\.exe)?\b[^\n]*(?:-enc|-encodedcommand)\b"),
    ("destructive_delete", "warning", r"(?i)\brm\s+-rf\s+(?:/|~|\$home|\$env:|[a-z]:\\)"),
    ("destructive_format", "warning", r"(?i)\b(format|diskpart)\b[^\n]*(?:[a-z]:|select\s+disk)"),
    ("force_push", "warning", r"(?i)\bgit\s+push\b[^\n]*--force\b"),
    ("world_writable", "warning", r"(?i)\bchmod\s+(?:-R\s+)?777\b"),
)
SECRET_PATTERNS: tuple[tuple[str, str], ...] = (
    ("private_key", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ("github_token", r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    ("openai_key", r"\bsk-[A-Za-z0-9]{20,}\b"),
    ("aws_access_key", r"\bAKIA[0-9A-Z]{16}\b"),
)


def hash_skill(files: Iterable[Path], skill_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(skill_dir).as_posix()):
        relative = path.relative_to(skill_dir).as_posix().encode("utf-8")
        digest.update(relative + b"\0")
        try:
            if not stat.S_ISREG(path.lstat().st_mode):
                digest.update(b"<non-regular>")
                continue
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            digest.update(b"<unreadable>")
    return digest.hexdigest()


def infer_category(root: Path, skill_dir: Path, metadata: dict[str, Any]) -> str:
    muse = metadata_mapping(metadata_mapping(metadata, "metadata"), "muse")
    hermes = metadata_mapping(metadata_mapping(metadata, "metadata"), "hermes")
    explicit = muse.get("primary_category") or muse.get("category") or hermes.get("category")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    try:
        parts = skill_dir.relative_to(root).parts
    except ValueError:
        parts = ()
    return parts[0] if len(parts) > 1 else "uncategorized"


def audit_skill(root: Path, marker: Path) -> SkillRecord:
    root = normalize_path(root)
    marker = marker.absolute()
    skill_dir = marker.parent
    findings: list[Finding] = []
    metadata, body, parse_findings = parse_skill_file(marker)
    findings.extend(parse_findings)

    try:
        relative_dir = skill_dir.relative_to(root)
        resolved_dir = skill_dir.resolve()
        if not is_within(resolved_dir, root):
            add_finding(findings, "path_escape", "critical", "Skill directory resolves outside its configured root", str(marker))
    except ValueError:
        relative_dir = Path(skill_dir.name)
        add_finding(findings, "path_escape", "critical", "Skill path is outside its configured root", str(marker))

    name_value = metadata.get("name", "")
    description_value = metadata.get("description", "")
    name = name_value.strip() if isinstance(name_value, str) else ""
    description = description_value.strip() if isinstance(description_value, str) else ""
    if not name:
        add_finding(findings, "name_missing", "critical", "Skill name is missing or not a string", str(marker))
    elif not NAME_RE.fullmatch(name):
        add_finding(findings, "name_invalid", "critical", "Skill name is not a safe portable slug", str(marker), name)
    if not description:
        add_finding(findings, "description_missing", "critical", "Skill description is missing or not a string", str(marker))
    elif len(description) > 1024:
        add_finding(findings, "description_long", "warning", "Skill description exceeds 1024 characters", str(marker))
    if not body:
        add_finding(findings, "body_missing", "critical", "SKILL.md has no instruction body", str(marker))
    if name and name != skill_dir.name:
        add_finding(findings, "name_dir_mismatch", "warning", "Skill name differs from its directory name", str(marker), name)

    metadata_block = metadata_mapping(metadata, "metadata")
    muse_block = metadata_mapping(metadata_block, "muse")
    hermes_block = metadata_mapping(metadata_block, "hermes")
    tags = string_list(muse_block.get("tags") or hermes_block.get("tags") or metadata.get("trigger_keywords"))
    declared_risk = str(muse_block.get("risk_level") or metadata.get("risk_level") or "").lower().strip()
    if declared_risk not in {"low", "medium", "high"}:
        declared_risk = ""
    category = infer_category(root, skill_dir, metadata)
    if category != export_category(category):
        add_finding(findings, "category_normalized", "warning", "Category will be normalized in approved exports", str(marker), category)
    version = str(metadata.get("version", "0.0.0"))

    files, symlinks, special_files = iter_files(skill_dir)
    for link in symlinks:
        try:
            resolved = link.resolve()
            severity = "critical" if not is_within(resolved, root) else "warning"
        except OSError:
            severity = "critical"
        add_finding(findings, "symlink_present", severity, "Symlinks are not copied into approved exports", str(link))
    for special in special_files:
        add_finding(findings, "special_file", "critical", "Non-regular files are not accepted in skill exports", str(special))
    if marker not in files:
        try:
            if stat.S_ISREG(marker.lstat().st_mode):
                files.append(marker)
        except OSError:
            pass
    files = list(dict.fromkeys(files))

    urls: set[str] = set()
    scripts: list[str] = []
    for path in files:
        relative = path.relative_to(skill_dir).as_posix()
        if path.suffix.lower() in SCRIPT_SUFFIXES:
            scripts.append(relative)
        text = inspect_text(path)
        if not text:
            try:
                if path.stat().st_size > MAX_INSPECT_BYTES:
                    add_finding(findings, "large_file", "warning", "File was not content-scanned because it exceeds 2 MiB", relative)
            except OSError:
                pass
            continue
        for match in URL_RE.findall(text):
            urls.add(safe_url(match.rstrip(".,;")))
        for code, severity, pattern in DANGEROUS_PATTERNS:
            found = re.search(pattern, text)
            if found:
                add_finding(findings, code, severity, "Potentially dangerous command or side effect", relative, found.group(0))
        for code, pattern in SECRET_PATTERNS:
            found = re.search(pattern, text)
            if found:
                add_finding(findings, code, "critical", "Credential-like material detected; remove it from the skill", relative, found.group(0))

    content_hash = hash_skill(files, skill_dir)
    lower_text = (body + "\n" + "\n".join(urls)).lower()
    observed_destructive = any(item.code in {"destructive_delete", "destructive_format", "force_push", "world_writable"} for item in findings)
    observed_auth = bool(re.search(r"\b(api[_ -]?key|token|password|cookie|oauth|ssh)\b", lower_text))
    observed_network = bool(urls or re.search(r"\b(curl|wget|requests|urllib|httpx|fetch)\b", lower_text))
    if any(item.severity == "critical" for item in findings) or (observed_destructive and scripts):
        observed_risk = "high"
    elif scripts or observed_auth or observed_network or any(item.severity == "warning" for item in findings):
        observed_risk = "medium"
    else:
        observed_risk = "low"
    if declared_risk and {"low": 0, "medium": 1, "high": 2}[observed_risk] > {"low": 0, "medium": 1, "high": 2}[declared_risk]:
        add_finding(findings, "risk_mismatch", "warning", "Observed risk is higher than declared risk", str(marker))
    if scripts:
        add_finding(findings, "scripts_present", "warning", "Skill contains executable-supporting files; review before approval", str(marker))
    if urls:
        add_finding(findings, "external_links", "warning", "Skill contains external URLs; MUSE records them but never fetches them", str(marker))

    relative_text = relative_dir.as_posix() if str(relative_dir) != "." else "."
    identity = f"{root}|{relative_text}|{name or skill_dir.name}"
    skill_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return SkillRecord(
        skill_id=skill_id,
        name=name or skill_dir.name,
        description=description,
        root=str(root),
        skill_dir=str(skill_dir),
        rel_dir=relative_text,
        category=category,
        tags=sorted(set(tags)),
        version=version,
        content_hash=content_hash,
        file_count=len(files),
        urls=sorted(urls),
        script_files=sorted(scripts),
        symlink_files=sorted(str(item) for item in symlinks),
        declared_risk=declared_risk,
        observed_risk=observed_risk,
        findings=findings,
    )


def discover(roots: Iterable[Path]) -> tuple[list[SkillRecord], list[str]]:
    records: list[SkillRecord] = []
    errors: list[str] = []
    seen_markers: set[Path] = set()
    for raw_root in roots:
        root = normalize_path(raw_root)
        if not root.exists():
            errors.append(f"root_missing: {root}")
            continue
        if not root.is_dir():
            errors.append(f"root_not_directory: {root}")
            continue
        for marker in sorted(root.rglob("SKILL.md")):
            marker = marker.absolute()
            if marker in seen_markers:
                continue
            seen_markers.add(marker)
            records.append(audit_skill(root, marker))
    records = sorted(records, key=lambda item: (item.category, item.name, item.skill_id))
    by_name: dict[str, list[SkillRecord]] = {}
    for record in records:
        by_name.setdefault(record.name, []).append(record)
    for name, matches in by_name.items():
        if len(matches) > 1:
            for record in matches:
                add_finding(record.findings, "duplicate_name", "critical", f"Skill name is duplicated across scanned roots: {name}", record.skill_dir)
    return records, errors


def default_roots() -> list[Path]:
    root = safe_home() / "skills"
    return [root] if root.exists() else []


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return default.copy() if default else {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read state file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"State file must contain an object: {path}")
    return value


def save_text(path: Path, value: str) -> None:
    """Atomically write generated text without following an existing symlink."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_json(path: Path, value: dict[str, Any]) -> None:
    save_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def state_path(state_dir: Path) -> Path:
    return state_dir / "state.json"


def state_with_snapshot(state: dict[str, Any], roots: list[Path], records: list[SkillRecord], errors: list[str]) -> dict[str, Any]:
    state.setdefault("version", 1)
    state["roots"] = [str(normalize_path(root)) for root in roots]
    state["last_scan"] = {
        "scanned_at": now_iso(),
        "roots": state["roots"],
        "errors": errors,
        "skills": [record.to_dict() for record in records],
    }
    state.setdefault("approvals", {})
    state.setdefault("releases", [])
    return state


def records_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = state.get("last_scan", {})
    skills = snapshot.get("skills", [])
    return skills if isinstance(skills, list) else []


def current_scan(state_dir: Path, roots: list[Path] | None, save: bool = False) -> tuple[dict[str, Any], list[SkillRecord], list[str]]:
    state = load_json(state_path(state_dir), {"version": 1, "approvals": {}, "releases": []})
    selected = roots if roots is not None else [Path(item) for item in state.get("roots", [])]
    if not selected:
        selected = default_roots()
    records, errors = discover(selected)
    if save:
        state = state_with_snapshot(state, selected, records, errors)
        save_json(state_path(state_dir), state)
    return state, records, errors


def approval_for(state: dict[str, Any], record: SkillRecord) -> dict[str, Any]:
    value = state.get("approvals", {}).get(record.skill_id, {})
    return value if isinstance(value, dict) else {}


def effective_status(state: dict[str, Any], record: SkillRecord) -> str:
    approval = approval_for(state, record)
    if approval.get("approved") is True:
        if approval.get("content_hash") == record.content_hash:
            return "approved"
        return "stale"
    return record.audit_status


def print_records(state: dict[str, Any], records: list[SkillRecord], as_json: bool = False) -> None:
    output = []
    for record in records:
        value = record.to_dict()
        value["status"] = effective_status(state, record)
        output.append(value)
    if as_json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    if not output:
        print("No skills found.")
        return
    print(f"{'STATUS':<13} {'RISK':<7} {'CATEGORY':<24} {'NAME':<32} DESCRIPTION")
    print("-" * 115)
    for item in output:
        description = item["description"].replace("\n", " ")[:55]
        print(f"{item['status']:<13} {item['observed_risk']:<7} {item['category'][:23]:<24} {item['name'][:31]:<32} {description}")


def print_audit_summary(state: dict[str, Any], records: list[SkillRecord], errors: list[str]) -> None:
    counts: dict[str, int] = {}
    risks: dict[str, int] = {}
    for record in records:
        status = effective_status(state, record)
        counts[status] = counts.get(status, 0) + 1
        risks[record.observed_risk] = risks.get(record.observed_risk, 0) + 1
    print(f"MUSE audit: {len(records)} skills")
    print("Status:", ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    print("Risk:", ", ".join(f"{key}={value}" for key, value in sorted(risks.items())))
    if errors:
        print("Root warnings:")
        for error in errors:
            print(f"  - {error}")
    for record in records:
        status = effective_status(state, record)
        if status in {"critical", "needs_review", "stale"}:
            print(f"\n[{status}] {record.name} ({record.skill_id})")
            for finding in record.findings:
                print(f"  - {finding.severity}: {finding.message} ({finding.code})")


def find_record(records: list[SkillRecord], reference: str) -> SkillRecord:
    exact = [item for item in records if item.skill_id == reference or item.name == reference or item.skill_dir == reference]
    if not exact:
        try:
            target = normalize_path(Path(reference))
        except OSError:
            target = None
        if target is not None:
            exact = [item for item in records if normalize_path(Path(item.skill_dir)) == target]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise SystemExit(f"Ambiguous skill reference {reference!r}; use one of: {', '.join(item.skill_id for item in exact)}")
    raise SystemExit(f"Skill not found: {reference}")


def command_scan(args: argparse.Namespace) -> int:
    roots = args.root or default_roots()
    records, errors = discover(roots)
    state = load_json(state_path(args.state_dir), {"approvals": {}})
    if args.json:
        print(json.dumps({"version": VERSION, "roots": [str(normalize_path(root)) for root in roots], "errors": errors, "skills": [item.to_dict() for item in records]}, ensure_ascii=False, indent=2))
    else:
        print_records(state, records)
        if errors:
            for error in errors:
                print(f"WARNING: {error}", file=sys.stderr)
    return 1 if any(item.audit_status == "critical" for item in records) else 0


def command_audit(args: argparse.Namespace) -> int:
    roots = args.root or None
    state, records, errors = current_scan(args.state_dir, roots, save=True)
    if args.json:
        print(json.dumps(state["last_scan"], ensure_ascii=False, indent=2))
    else:
        print_audit_summary(state, records, errors)
    return 1 if any(item.audit_status == "critical" for item in records) else 0


def command_list(args: argparse.Namespace) -> int:
    if args.root:
        state, records, _ = current_scan(args.state_dir, args.root, save=False)
    else:
        state = load_json(state_path(args.state_dir), {"approvals": {}})
        records = [record_from_dict(item) for item in records_from_state(state)]
    print_records(state, records, args.json)
    return 0


def command_search(args: argparse.Namespace) -> int:
    state = load_json(state_path(args.state_dir), {"approvals": {}})
    records = [record_from_dict(item) for item in records_from_state(state)]
    query = args.query.lower()
    selected = [item for item in records if query in " ".join([item.name, item.description, item.category, " ".join(item.tags)]).lower()]
    print_records(state, selected, args.json)
    return 0


def route_tokens(value: str) -> list[str]:
    return [item.casefold() for item in re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]*|[\u4e00-\u9fff]+", value) if len(item) > 1]


def risk_tags_for_record(record: SkillRecord) -> list[str]:
    tags: set[str] = set()
    for finding in record.findings:
        tags.update(RISK_TAG_BY_FINDING.get(finding.code, set()))
    if record.urls:
        tags.add("network")
    if record.script_files:
        tags.add("script")

    body = inspect_text(Path(record.skill_dir) / "SKILL.md").casefold()
    if re.search(r"\b(systemctl|service|launchctl|sc\.exe|docker\s+(?:compose|run))\b", body):
        tags.add("service")
    if re.search(r"\b(?:rm\s+-r|dd\s+if=|mkfs|diskpart|format(?:\.com)?|drop\s+(?:table|database)|delete\s+from)\b", body):
        tags.update({"destructive", "filesystem"})
    if re.search(r"\b(?:api[_ -]?key|token|password|secret|cookie|oauth)\b", body):
        tags.add("api_key")
    if re.search(r"(?:/etc/|/var/|[A-Za-z]:\\|\b(?:chmod|chown|mount)\b)", body):
        tags.add("filesystem")
    return sorted(tags)


def route_record(record: SkillRecord, score: int = 0) -> dict[str, Any]:
    value = {
        "skill_id": record.skill_id,
        "name": record.name,
        "description": redact(record.description, 1024),
        "category": record.category,
        "risk_tags": risk_tags_for_record(record),
        "audit_status": record.audit_status,
        "file_count": record.file_count,
        "script_files": record.script_files,
        "path": str(normalize_path(Path(record.skill_dir))),
        "root": str(normalize_path(Path(record.root))),
        "version": record.version,
        "content_hash": record.content_hash,
    }
    if score:
        value["match_score"] = score
    return value


def route_score(record: SkillRecord, task: str) -> int:
    query = task.casefold().strip()
    tokens = route_tokens(task)
    fields = {
        "name": record.name.casefold(),
        "description": record.description.casefold(),
        "category": record.category.casefold(),
        "tags": " ".join(record.tags).casefold(),
        "path": record.skill_dir.casefold(),
    }
    score = 0
    if query and query in fields["name"]:
        score += 100
    elif query and query in " ".join(fields.values()):
        score += 20
    for token in tokens:
        if token in fields["name"]:
            score += 12
        elif token in fields["tags"] or token in fields["category"]:
            score += 7
        elif token in fields["description"] or token in fields["path"]:
            score += 4
    return score


def route_matches(records: list[SkillRecord], task: str, limit: int = 3) -> list[tuple[int, SkillRecord]]:
    scored = [(route_score(record, task), record) for record in records]
    scored = [(score, record) for score, record in scored if score > 0]
    status_order = {"ready": 0, "needs_review": 1, "critical": 2}
    return sorted(scored, key=lambda item: (-item[0], status_order.get(item[1].audit_status, 3), item[1].name))[:limit]


def command_route(args: argparse.Namespace) -> int:
    task = args.task.strip()
    if not task:
        raise SystemExit("Task description cannot be empty.")
    _, records, errors = current_scan(args.state_dir, args.root or None, save=False)
    matches = [route_record(record, score) for score, record in route_matches(records, task)]
    result = {"version": VERSION, "task": task, "matches": matches, "root_warnings": errors}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if not matches:
        print(f"No MUSE skills matched: {task}")
        return 0
    print(f"MUSE route: {task}")
    for index, item in enumerate(matches, 1):
        risk = ", ".join(item["risk_tags"]) or "none"
        print(f"{index}. {item['name']} [{item['audit_status']}] risk={risk}")
        print(f"   {item['description']}")
        print(f"   Path: {item['path']}")
    for warning in errors:
        print(f"WARNING: {warning}", file=sys.stderr)
    return 0


def read_inspect_file(path: Path, max_bytes: int) -> tuple[str | None, str | None]:
    try:
        file_stat = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(file_stat.st_mode):
            return None, "not a regular file"
        if file_stat.st_size > max_bytes:
            return None, f"file exceeds the {max_bytes} byte inspect limit"
        return path.read_text(encoding="utf-8", errors="replace"), None
    except OSError as exc:
        return None, str(exc)


def inspect_payload(record: SkillRecord, include_scripts: bool, acknowledge_risk: bool) -> dict[str, Any]:
    payload = route_record(record)
    payload.update({"requires_acknowledgement": False, "skill_md": None, "scripts": [], "warnings": []})
    if record.audit_status == "critical" and not acknowledge_risk:
        payload["requires_acknowledgement"] = True
        payload["warnings"].append("Critical findings require explicit --ack-risk for one-time content inspection.")
        return payload

    skill_dir = normalize_path(Path(record.skill_dir))
    marker, error = read_inspect_file(skill_dir / "SKILL.md", MAX_SKILL_MD_BYTES)
    if error:
        payload["warnings"].append(f"SKILL.md: {error}")
    elif marker is not None:
        payload["skill_md"] = redact(marker, MAX_INSPECT_OUTPUT_BYTES)
        if len(marker) > MAX_INSPECT_OUTPUT_BYTES:
            payload["warnings"].append("SKILL.md output was truncated at the inspect limit.")

    if record.audit_status == "needs_review":
        payload["warnings"].append("This skill has review findings; Hermes still controls command execution approval.")
    if not include_scripts:
        if record.script_files:
            payload["warnings"].append("Script contents omitted; re-run with --include-scripts to inspect them.")
        return payload

    for relative in record.script_files:
        script_path = normalize_path(skill_dir / relative)
        if not is_within(script_path, skill_dir):
            payload["warnings"].append(f"Skipped script outside skill directory: {relative}")
            continue
        content, error = read_inspect_file(script_path, MAX_INSPECT_SCRIPT_BYTES)
        item = {"path": str(script_path), "content": None}
        if error:
            item["error"] = error
        elif content is not None:
            item["content"] = redact(content, MAX_INSPECT_SCRIPT_BYTES)
        payload["scripts"].append(item)
    return payload


def command_inspect(args: argparse.Namespace) -> int:
    _, records, _ = current_scan(args.state_dir, args.root or None, save=False)
    record = find_record(records, args.skill)
    payload = inspect_payload(record, args.include_scripts, args.ack_risk)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"Inspect: {payload['name']} [{payload['audit_status']}]")
    print(f"Risk tags: {', '.join(payload['risk_tags']) or 'none'}")
    print(f"Path: {payload['path']}")
    for warning in payload["warnings"]:
        print(f"WARNING: {warning}")
    if payload["requires_acknowledgement"]:
        print(f"Re-run with --ack-risk to inspect this critical skill once: {payload['name']}")
        return 0
    if payload["skill_md"] is not None:
        print("\n--- SKILL.md ---\n")
        print(payload["skill_md"], end="" if payload["skill_md"].endswith("\n") else "\n")
    for script in payload["scripts"]:
        print(f"\n--- {script['path']} ---\n")
        print(script.get("content") or script.get("error", "unavailable"))
    return 0


def record_from_dict(value: dict[str, Any]) -> SkillRecord:
    findings = [Finding(str(item.get("code", "unknown")), str(item.get("severity", "warning")), str(item.get("message", "")), str(item.get("file", "")), str(item.get("evidence", ""))) for item in value.get("findings", []) if isinstance(item, dict)]
    return SkillRecord(
        skill_id=str(value.get("skill_id", "")), name=str(value.get("name", "")), description=str(value.get("description", "")),
        root=str(value.get("root", "")), skill_dir=str(value.get("skill_dir", "")), rel_dir=str(value.get("rel_dir", ".")),
        category=str(value.get("category", "uncategorized")), tags=string_list(value.get("tags")), version=str(value.get("version", "0.0.0")),
        content_hash=str(value.get("content_hash", "")), file_count=int(value.get("file_count", 0)), urls=string_list(value.get("urls")),
        script_files=string_list(value.get("script_files")), symlink_files=string_list(value.get("symlink_files")), declared_risk=str(value.get("declared_risk", "")),
        observed_risk=str(value.get("observed_risk", "low")), findings=findings,
    )


def command_approve(args: argparse.Namespace, approved: bool) -> int:
    state, records, errors = current_scan(args.state_dir, args.root or None, save=True)
    record = find_record(records, args.reference)
    if not approved:
        state.setdefault("approvals", {})[record.skill_id] = {"approved": False, "updated_at": now_iso(), "reason": args.reason or "revoked"}
        save_json(state_path(args.state_dir), state)
        print(f"Revoked: {record.name} ({record.skill_id})")
        return 0
    if record.audit_status == "critical":
        raise SystemExit(f"Cannot approve critical skill {record.name}; fix findings first.")
    if record.audit_status == "needs_review" and not args.ack_risk:
        raise SystemExit(f"Skill {record.name} needs review. Re-run with --ack-risk after inspecting audit findings.")
    state.setdefault("approvals", {})[record.skill_id] = {
        "approved": True,
        "content_hash": record.content_hash,
        "approved_at": now_iso(),
        "approved_by": os.environ.get("USERNAME") or os.environ.get("USER") or "local-user",
        "acknowledged_risk": bool(args.ack_risk),
        "note": args.reason or "",
    }
    save_json(state_path(args.state_dir), state)
    print(f"Approved: {record.name} ({record.skill_id}) at hash {record.content_hash[:12]}")
    return 0


def approved_records(state: dict[str, Any], records: list[SkillRecord]) -> list[SkillRecord]:
    selected: list[SkillRecord] = []
    for record in records:
        approval = approval_for(state, record)
        if approval.get("approved") is True and approval.get("content_hash") == record.content_hash and record.audit_status != "critical":
            selected.append(record)
    return selected


def safe_output_dir(output: Path, roots: Iterable[Path]) -> Path:
    resolved = normalize_path(output)
    for root in roots:
        root_resolved = normalize_path(root)
        if is_within(resolved, root_resolved):
            raise SystemExit(f"Refusing to write generated output inside a skill source root: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def command_bundle(args: argparse.Namespace) -> int:
    state, records, _ = current_scan(args.state_dir, args.root or None, save=True)
    selected = approved_records(state, records)
    if not selected:
        raise SystemExit("No approved, unchanged skills available. Run audit and approve first.")
    output_dir = safe_output_dir(args.output_dir or args.state_dir / "bundles", [Path(item["root"]) for item in state.get("last_scan", {}).get("skills", []) if isinstance(item, dict) and item.get("root")])
    groups: dict[str, list[SkillRecord]] = {}
    for record in selected:
        groups.setdefault(record.category or "uncategorized", []).append(record)
    generated: list[str] = []
    for category, group in sorted(groups.items()):
        slug = re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-") or "uncategorized"
        data = {
            "name": slug,
            "description": f"Approved MUSE skills for {category}",
            "skills": sorted({item.name for item in group}),
            "instruction": "Use the listed skills only when they match the task. Follow each skill's verification and approval constraints.",
        }
        path = output_dir / f"{slug}.yaml"
        save_text(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
        generated.append(str(path))
    print(f"Generated {len(generated)} Hermes bundles in {output_dir}")
    for path in generated:
        print(f"  {path}")
    return 0


def ensure_target_safe(target: Path, roots: Iterable[Path], consumer_home: Path | None = None) -> Path:
    target = normalize_path(target)
    for root in roots:
        root = normalize_path(root)
        if is_within(target, root) or is_within(root, target):
            raise SystemExit(f"Refusing to activate inside or over a skill source root: {target}")
    if consumer_home:
        primary = normalize_path(consumer_home) / "skills"
        if is_within(target, primary) or is_within(primary, target):
            raise SystemExit(f"Refusing to activate inside or over Hermes primary skills directory: {primary}")
    target.mkdir(parents=True, exist_ok=True)
    return target


def ensure_no_shadowed_local(roots: Iterable[Path], consumer_home: Path | None = None) -> None:
    """Prevent a release that Hermes would silently shadow with local skills."""
    base = normalize_path(consumer_home) if consumer_home else safe_home()
    primary = base / "skills"
    for raw_root in roots:
        root = normalize_path(raw_root)
        if is_within(root, primary) or is_within(primary, root):
            raise SystemExit(
                "Refusing to activate this external release: a scanned root overlaps Hermes' "
                f"primary skills directory ({primary}), which takes precedence over external_dirs. "
                "Use a dedicated Hermes profile with an empty local skills directory and pass "
                "that profile home with --consumer-home."
            )


def copy_approved_skills(records: list[SkillRecord], release_skills: Path) -> list[dict[str, Any]]:
    names: dict[str, SkillRecord] = {}
    manifest: list[dict[str, Any]] = []
    for record in records:
        if record.name in names:
            raise SystemExit(f"Duplicate approved skill name would shadow another skill: {record.name}")
        names[record.name] = record
        # Re-read and re-hash immediately before copying.  Approval is not a
        # substitute for a last-moment TOCTOU check on a writable source root.
        fresh = audit_skill(normalize_path(Path(record.root)), Path(record.skill_dir) / "SKILL.md")
        if fresh.content_hash != record.content_hash:
            raise SystemExit(f"Skill changed during apply; re-audit and approve again: {record.name}")
        if fresh.audit_status == "critical":
            raise SystemExit(f"Skill became critical during apply: {record.name}")
        destination = release_skills / export_category(record.category) / record.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if any(Path(item).is_symlink() for item in record.symlink_files):
            raise SystemExit(f"Refusing to export symlink-containing skill: {record.name}")
        shutil.copytree(record.skill_dir, destination, symlinks=True)
        copied_links = [item for item in destination.rglob("*") if item.is_symlink()]
        if copied_links:
            shutil.rmtree(destination)
            raise SystemExit(f"Refusing to export a skill containing symlinks: {record.name}")
        copied = audit_skill(release_skills, destination / "SKILL.md")
        if copied.content_hash != record.content_hash:
            shutil.rmtree(destination)
            raise SystemExit(f"Copied skill hash mismatch; release aborted: {record.name}")
        manifest.append({"skill_id": record.skill_id, "name": record.name, "content_hash": record.content_hash, "source": record.skill_dir, "destination": str(destination)})
    return manifest


def verify_release_manifest(release_skills: Path, expected: Any) -> None:
    """Verify a stored release before it can become active again."""
    if not isinstance(expected, list):
        raise SystemExit("Release has no trusted skill manifest in MUSE state")
    records, errors = discover([release_skills])
    if errors or any(record.audit_status == "critical" for record in records):
        raise SystemExit("Release audit failed; refusing to activate it")
    expected_pairs = {
        (str(item.get("name", "")), str(item.get("content_hash", "")))
        for item in expected
        if isinstance(item, dict)
    }
    actual_pairs = {(record.name, record.content_hash) for record in records}
    if expected_pairs != actual_pairs or len(expected_pairs) != len(records):
        raise SystemExit("Release content no longer matches its approved manifest")


def activate_release(release_skills: Path, target: Path, state: dict[str, Any], release_id: str) -> None:
    target = normalize_path(target)
    current = target / "current"
    rollback_root = target / "rollback"
    staging = target / f".staging-{uuid.uuid4().hex}"
    rollback_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(release_skills, staging, symlinks=True)
    copied_links = [item for item in staging.rglob("*") if item.is_symlink()]
    if copied_links:
        shutil.rmtree(staging)
        raise SystemExit("Refusing to activate a release containing symlinks")
    old_backup: Path | None = None
    old_active = state.get("active_release")
    try:
        if current.exists() or current.is_symlink():
            old_backup = rollback_root / (str(old_active or "previous") + "-" + uuid.uuid4().hex[:8])
            shutil.move(str(current), str(old_backup))
        shutil.move(str(staging), str(current))
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        if old_backup and old_backup.exists() and not current.exists():
            shutil.move(str(old_backup), str(current))
        raise
    state["active_release"] = release_id
    state["active_target"] = str(current)
    state.setdefault("release_history", []).append({"release_id": release_id, "activated_at": now_iso(), "target": str(current)})


def command_apply(args: argparse.Namespace) -> int:
    state, records, _ = current_scan(args.state_dir, args.root or None, save=True)
    selected = approved_records(state, records)
    if not selected:
        raise SystemExit("No approved, unchanged skills available to apply.")
    roots = [Path(item) for item in state.get("roots", [])]
    ensure_no_shadowed_local(roots, getattr(args, "consumer_home", None))
    target = ensure_target_safe(args.target, roots, getattr(args, "consumer_home", None))
    release_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    release_dir = args.state_dir / "releases" / release_id
    release_skills = release_dir / "skills"
    release_skills.mkdir(parents=True, exist_ok=False)
    manifest = copy_approved_skills(selected, release_skills)
    save_json(release_dir / "manifest.json", {"version": VERSION, "release_id": release_id, "created_at": now_iso(), "skills": manifest})
    verify_release_manifest(release_skills, manifest)
    try:
        activate_release(release_skills, target, state, release_id)
    except Exception as exc:
        raise SystemExit(f"Activation failed; release remains preserved at {release_dir}: {exc}") from exc
    state.setdefault("releases", []).append({"release_id": release_id, "created_at": now_iso(), "path": str(release_dir), "skills": manifest})
    save_json(state_path(args.state_dir), state)
    print(f"Applied release {release_id} with {len(selected)} approved skills.")
    print(f"Configure Hermes external_dirs to: {target / 'current'}")
    return 0


def command_rollback(args: argparse.Namespace) -> int:
    state = load_json(state_path(args.state_dir), {})
    releases = state.get("releases", [])
    if not isinstance(releases, list):
        raise SystemExit("State has no release history.")
    active = state.get("active_release")
    candidates = [item for item in releases if isinstance(item, dict) and item.get("release_id") != active]
    if args.release:
        candidates = [item for item in candidates if item.get("release_id") == args.release]
    if not candidates:
        raise SystemExit("No earlier release is available for rollback.")
    release = candidates[-1]
    release_id = str(release.get("release_id"))
    releases_root = normalize_path(args.state_dir / "releases")
    release_dir = normalize_path(Path(str(release.get("path"))))
    if not is_within(release_dir, releases_root) or release_dir == releases_root:
        raise SystemExit(f"Release path escapes the MUSE release directory: {release_dir}")
    release_skills = release_dir / "skills"
    if not release_skills.is_dir():
        raise SystemExit(f"Release contents missing: {release_skills}")
    verify_release_manifest(release_skills, release.get("skills"))
    roots = [Path(item) for item in state.get("roots", [])]
    ensure_no_shadowed_local(roots, getattr(args, "consumer_home", None))
    target = ensure_target_safe(args.target, roots, getattr(args, "consumer_home", None))
    activate_release(release_skills, target, state, release_id)
    state.setdefault("release_history", []).append({"release_id": release_id, "activated_at": now_iso(), "target": str(target / "current"), "rollback": True})
    save_json(state_path(args.state_dir), state)
    print(f"Rolled back to release {release_id}.")
    return 0


def command_config(args: argparse.Namespace) -> int:
    current = normalize_path(args.target) / "current"
    value = {"skills": {"external_dirs": [str(current)]}}
    print(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), end="")
    return 0


def refactor_audit(skill_dir: Path) -> dict[str, Any]:
    """Return read-only structure and split suggestions for one skill."""
    root = normalize_path(skill_dir)
    marker = root / "SKILL.md"
    metadata, body, parse_findings = parse_skill_file(marker)
    findings = list(parse_findings)
    raw = ""
    marker_bytes = 0
    try:
        marker_stat = marker.lstat()
        marker_bytes = marker_stat.st_size
        if stat.S_ISREG(marker_stat.st_mode) and marker_bytes <= MAX_SKILL_MD_BYTES:
            raw = marker.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass

    if not root.is_dir():
        findings.append(Finding("skill_dir_missing", "critical", "Skill directory does not exist", str(root)))

    references_root = root / "references"
    reference_files: list[Path] = []
    reference_symlinks: list[Path] = []
    reference_special: list[Path] = []
    if references_root.is_dir():
        reference_files, reference_symlinks, reference_special = iter_files(references_root)

    linked: set[str] = set()
    for target in MARKDOWN_LINK_RE.findall(raw):
        target = target.split("#", 1)[0].strip().rstrip(".,;:)")
        if target.startswith("references/"):
            linked.add(target)
    linked.update(REFERENCE_TOKEN_RE.findall(raw))

    refs_root_resolved = references_root.resolve()
    missing: list[str] = []
    unsafe: list[str] = []
    for target in sorted(linked):
        resolved = (root / target).resolve()
        if not is_within(resolved, refs_root_resolved):
            unsafe.append(target)
        elif not resolved.is_file():
            missing.append(target)

    existing = {
        path.relative_to(root).as_posix(): path
        for path in reference_files
    }
    orphan = sorted(set(existing) - linked)
    nested = sorted(
        relative for relative in existing
        if len(Path(relative).relative_to("references").parts) > 1
    )

    body_blocks = {
        re.sub(r"\s+", " ", block).strip()
        for block in re.split(r"\n\s*\n", body)
        if len(block.strip()) >= 80
    }
    duplicate_refs: list[str] = []
    for path in reference_files:
        reference_text = inspect_text(path)
        if not reference_text:
            continue
        reference_blocks = {
            re.sub(r"\s+", " ", block).strip()
            for block in re.split(r"\n\s*\n", reference_text)
            if len(block.strip()) >= 80
        }
        if body_blocks & reference_blocks:
            duplicate_refs.append(path.relative_to(root).as_posix())

    command_lines = re.findall(
        r"(?im)^\s*(?:\$\s*)?(?:curl|wget|pip(?:3)?|npm|docker|systemctl|git|python(?:3)?|chmod|ssh)\b",
        raw,
    )
    code_fences = raw.count("```") // 2
    safety_signals = [
        code for code, _, pattern in DANGEROUS_PATTERNS
        if re.search(pattern, raw)
    ]
    if safety_signals:
        findings.append(Finding(
            "safety_rules_present", "info",
            "Keep safety constraints and approval rules in SKILL.md when extracting detail",
            str(marker), ", ".join(safety_signals),
        ))
    if marker_bytes and raw.count("\n") + 1 > REFACTOR_MAX_LINES:
        findings.append(Finding(
            "skill_md_long", "warning",
            f"SKILL.md exceeds the recommended {REFACTOR_MAX_LINES}-line working limit",
            str(marker), str(raw.count("\n") + 1),
        ))
    if missing:
        findings.append(Finding("reference_missing", "warning", "SKILL.md points to missing reference files", str(marker), ", ".join(missing)))
    if unsafe:
        findings.append(Finding("reference_escape", "warning", "SKILL.md contains a reference path outside references/", str(marker), ", ".join(unsafe)))
    if orphan:
        findings.append(Finding("reference_orphan", "info", "Reference files are not linked from SKILL.md", str(references_root), ", ".join(orphan)))
    if nested:
        findings.append(Finding("reference_nested", "info", "Keep reference links one level below SKILL.md when possible", str(references_root), ", ".join(nested)))
    if code_fences >= 4 or len(command_lines) >= 8:
        findings.append(Finding(
            "inline_detail", "info",
            "SKILL.md contains substantial command or code detail; inspect whether it belongs in references/",
            str(marker), f"code_fences={code_fences}, command_lines={len(command_lines)}",
        ))
    if duplicate_refs:
        findings.append(Finding(
            "duplicate_reference_content", "info",
            "SKILL.md shares long blocks with reference files; remove duplication after review",
            str(marker), ", ".join(sorted(duplicate_refs)),
        ))

    status = "blocked" if any(item.severity == "critical" for item in findings) else (
        "review" if any(item.severity == "warning" for item in findings) else "ready"
    )
    return {
        "version": VERSION,
        "skill_dir": str(root),
        "name": str(metadata.get("name", root.name)) if isinstance(metadata, dict) else root.name,
        "status": status,
        "skill_md": {
            "bytes": marker_bytes,
            "lines": raw.count("\n") + 1 if raw else 0,
            "recommended_max_lines": REFACTOR_MAX_LINES,
            "code_fences": code_fences,
            "command_lines": len(command_lines),
        },
        "references": {
            "files": sorted(existing),
            "linked": sorted(linked),
            "missing": missing,
            "orphan": orphan,
            "nested": nested,
            "symlinks": sorted(path.relative_to(root).as_posix() for path in reference_symlinks),
            "special_files": sorted(path.relative_to(root).as_posix() for path in reference_special),
        },
        "findings": [item.to_dict() for item in findings],
    }


def command_refactor_audit(args: argparse.Namespace) -> int:
    report = refactor_audit(args.skill_dir)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        skill = report["skill_md"]
        refs = report["references"]
        print(f"Refactor audit: {report['name']} [{report['status']}]")
        print(f"SKILL.md: {skill['lines']} lines, {skill['bytes']} bytes")
        print(f"References: {len(refs['files'])} files, {len(refs['linked'])} linked, {len(refs['missing'])} missing, {len(refs['orphan'])} orphan")
        for finding in report["findings"]:
            print(f"- {finding['severity']}: {finding['message']} ({finding['code']})")
    if report["status"] == "blocked" or (args.strict and report["status"] != "ready"):
        return 1
    return 0


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-dir", type=Path, default=default_state_dir(), help="Local MUSE state directory")
    parser.add_argument("--root", type=Path, action="append", help="Skill root; repeat for multiple roots")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MUSE local console for Hermes skill assets")
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command", required=True)

    refactor = commands.add_parser("refactor-audit", help="Read-only audit of one skill's structure and reference split")
    refactor.add_argument("skill_dir", type=Path)
    refactor.add_argument("--json", action="store_true")
    refactor.add_argument("--strict", action="store_true", help="Treat advisory findings as a failing result")
    refactor.set_defaults(func=command_refactor_audit)

    route = commands.add_parser("route", help="Find relevant skills without changing MUSE state")
    add_common(route)
    route.add_argument("task", help="Natural-language task description")
    route.add_argument("--json", action="store_true")
    route.set_defaults(func=command_route)

    inspect = commands.add_parser("inspect", help="Read one skill on demand without approving or applying it")
    add_common(inspect)
    inspect.add_argument("skill", help="Skill name, id, or path returned by route")
    inspect.add_argument("--json", action="store_true")
    inspect.add_argument("--include-scripts", action="store_true", help="Include bounded, redacted script contents")
    inspect.add_argument("--ack-risk", action="store_true", help="Acknowledge critical findings for this one-time inspection")
    inspect.set_defaults(func=command_inspect)

    scan = commands.add_parser("scan", help="Read-only discover and audit skill roots")
    add_common(scan)
    scan.add_argument("--json", action="store_true")
    scan.set_defaults(func=command_scan)

    audit = commands.add_parser("audit", help="Scan and persist a local audit snapshot")
    add_common(audit)
    audit.add_argument("--json", action="store_true")
    audit.set_defaults(func=command_audit)

    listing = commands.add_parser("list", help="List skills from the last snapshot")
    add_common(listing)
    listing.add_argument("--json", action="store_true")
    listing.set_defaults(func=command_list)

    search = commands.add_parser("search", help="Search the last local snapshot")
    add_common(search)
    search.add_argument("query")
    search.add_argument("--json", action="store_true")
    search.set_defaults(func=command_search)

    approve = commands.add_parser("approve", help="Approve one unchanged skill for export")
    add_common(approve)
    approve.add_argument("reference")
    approve.add_argument("--ack-risk", action="store_true")
    approve.add_argument("--reason", default="")
    approve.set_defaults(func=lambda args: command_approve(args, True))

    revoke = commands.add_parser("revoke", help="Revoke an approval without touching source skills")
    add_common(revoke)
    revoke.add_argument("reference")
    revoke.add_argument("--reason", default="")
    revoke.set_defaults(func=lambda args: command_approve(args, False))

    bundle = commands.add_parser("bundle", help="Generate Hermes skill bundles from approved skills")
    add_common(bundle)
    bundle.add_argument("--output-dir", type=Path)
    bundle.set_defaults(func=command_bundle)

    apply = commands.add_parser("apply", help="Create and activate a versioned approved export")
    add_common(apply)
    apply.add_argument("--target", type=Path, required=True, help="Dedicated MUSE activation root")
    apply.add_argument("--consumer-home", type=Path, help="Hermes profile home that will consume the export")
    apply.set_defaults(func=command_apply)

    rollback = commands.add_parser("rollback", help="Activate an earlier approved export")
    add_common(rollback)
    rollback.add_argument("--target", type=Path, required=True)
    rollback.add_argument("--consumer-home", type=Path, help="Hermes profile home that will consume the export")
    rollback.add_argument("--release")
    rollback.set_defaults(func=command_rollback)

    config = commands.add_parser("config", help="Print Hermes external_dirs YAML for an activation root")
    config.add_argument("--target", type=Path, required=True)
    config.set_defaults(func=command_config)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.state_dir = normalize_path(args.state_dir) if hasattr(args, "state_dir") else default_state_dir()
    if getattr(args, "command", "") in {"audit", "approve", "revoke", "bundle", "apply", "rollback"}:
        args.state_dir.mkdir(parents=True, exist_ok=True)
    try:
        return int(args.func(args))
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
