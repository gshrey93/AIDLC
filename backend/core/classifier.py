"""File walking, classification, token estimation and inventory building."""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import NamedTuple, Optional

from .config import (
    AGENT_DIR_PARTS, AGENT_FILENAMES, AGENT_LIKE_CATEGORIES, AGENT_SUFFIXES,
    CATEGORY_AGENT, CATEGORY_CONTEXT, CATEGORY_DIAGRAM, CATEGORY_ORCHESTRATION,
    CATEGORY_OTHER, CATEGORY_SKILL, CATEGORY_SOURCE, CONTEXT_DIR_PARTS,
    CONTEXT_FILENAMES, CONTEXT_SUFFIXES, DATA_EXTENSIONS, DIAGRAM_EXTENSIONS,
    DOC_EXTENSIONS, GENERATED_PATH_MARKERS, IGNORED_DIR_PARTS, MAX_FILES,
    MAX_PARSE_FILE_BYTES, ORCHESTRATION_DIR_PARTS, ORCHESTRATION_FILENAMES,
    ORCHESTRATION_SUFFIXES, SKILL_DIR_PARTS, SKILL_FILENAMES, SKILL_SUFFIXES,
    SOURCE_EXTENSIONS, SUPPORTED_EXTENSIONS,
)

WS_RE = re.compile(r"\s+")

MAX_RETAINED_CHARS_PER_FILE = 200_000
MAX_RETAINED_TEXT_BYTES = 160 * 1024 * 1024


def estimate_tokens(char_count: int) -> int:
    return int(math.ceil(char_count / 4)) if char_count else 0


def normalise(text: str) -> str:
    """Lower-case + collapse whitespace so case-only and whitespace-only diffs vanish."""
    return WS_RE.sub(" ", (text or "").lower()).strip()


@dataclass
class FileRecord:
    path: str
    extension: str
    category: str
    inventory_group: str
    size_bytes: int
    line_count: int = 0
    estimated_tokens: int = 0
    parse_status: str = "Scanned"
    agent_like: bool = False
    skip_reason: Optional[str] = None
    similarity_group: Optional[str] = None
    content: Optional[str] = None
    norm: Optional[str] = None

    def to_public(self) -> dict:
        return {
            "path": self.path,
            "extension": self.extension,
            "category": self.category,
            "inventory_group": self.inventory_group,
            "size_bytes": self.size_bytes,
            "line_count": self.line_count,
            "estimated_tokens": self.estimated_tokens,
            "parse_status": self.parse_status,
            "agent_like": self.agent_like,
            "skip_reason": self.skip_reason,
            "similarity_group": self.similarity_group,
        }


@dataclass
class Inventory:
    files: list = field(default_factory=list)
    total_files: int = 0
    parsed_files: int = 0
    skipped_files: int = 0
    analyzed_tokens: int = 0
    warnings: list = field(default_factory=list)
    skip_reasons: dict = field(default_factory=dict)
    truncated: bool = False

    @property
    def parsed(self) -> list:
        return [f for f in self.files if f.parse_status == "Scanned"]


class _AgentAssetRule(NamedTuple):
    """One agent-asset classification rule: filename suffixes, exact names and path fragments."""

    category: str
    suffixes: tuple
    filenames: frozenset
    dir_parts: tuple


# Evaluated in order, so the first matching rule wins. This preserves the original
# agent > skill > context > orchestration precedence while replacing a 14-branch
# if-chain with a single data-driven loop.
_AGENT_ASSET_RULES: tuple = (
    _AgentAssetRule(CATEGORY_AGENT, AGENT_SUFFIXES, frozenset(AGENT_FILENAMES), AGENT_DIR_PARTS),
    _AgentAssetRule(CATEGORY_SKILL, SKILL_SUFFIXES, frozenset(SKILL_FILENAMES), SKILL_DIR_PARTS),
    _AgentAssetRule(CATEGORY_CONTEXT, CONTEXT_SUFFIXES, frozenset(CONTEXT_FILENAMES), CONTEXT_DIR_PARTS),
    _AgentAssetRule(
        CATEGORY_ORCHESTRATION, ORCHESTRATION_SUFFIXES,
        frozenset(ORCHESTRATION_FILENAMES), ORCHESTRATION_DIR_PARTS,
    ),
)

_EXTENSION_CATEGORIES: tuple = (
    (DIAGRAM_EXTENSIONS, CATEGORY_DIAGRAM),
    (SOURCE_EXTENSIONS, CATEGORY_SOURCE),
)


def classify(rel_path: str) -> str:
    """Map a repository-relative path to a FileAsset category."""
    path = "/" + rel_path.replace("\\", "/").lower()
    name = path.rsplit("/", 1)[-1]
    ext = os.path.splitext(name)[1]

    for rule in _AGENT_ASSET_RULES:
        if (
            name in rule.filenames
            or name.endswith(rule.suffixes)
            or any(part in path for part in rule.dir_parts)
        ):
            return rule.category

    for extensions, category in _EXTENSION_CATEGORIES:
        if ext in extensions:
            return category
    return CATEGORY_OTHER


def inventory_group_for(category: str, extension: str) -> str:
    mapping = {
        CATEGORY_AGENT: "Agents",
        CATEGORY_SKILL: "Skills",
        CATEGORY_CONTEXT: "Context and memory",
        CATEGORY_ORCHESTRATION: "Prompt and orchestration",
        CATEGORY_SOURCE: "Source code",
        CATEGORY_DIAGRAM: "Diagrams",
    }
    if category in mapping:
        return mapping[category]
    if extension in DOC_EXTENSIONS:
        return "Docs"
    if extension in DATA_EXTENSIONS:
        return "Other text assets"
    return "Other text assets"


def is_generated(rel_path: str) -> bool:
    p = "/" + rel_path.replace("\\", "/").lower()
    return any(marker in p for marker in GENERATED_PATH_MARKERS)


def _looks_binary(blob: bytes) -> bool:
    if b"\x00" in blob[:8192]:
        return True
    return False


def inventory_from_entries(entries: list) -> Inventory:
    """Build an inventory from in-memory entries.

    Each entry is either {"path", "content"} for a parsed text file, or
    {"path", "size_bytes", "parse_status", "skip_reason"} for a skipped/binary asset.
    """
    inv = Inventory()
    for entry in entries:
        rel = entry["path"].replace("\\", "/")
        ext = os.path.splitext(rel)[1].lower()
        category = classify(rel)
        rec = FileRecord(
            path=rel, extension=ext, category=category,
            inventory_group=inventory_group_for(category, ext),
            size_bytes=int(entry.get("size_bytes") or 0),
            agent_like=category in AGENT_LIKE_CATEGORIES,
        )
        if "content" in entry and entry.get("parse_status", "Scanned") == "Scanned":
            text = entry["content"]
            rec.size_bytes = len(text.encode("utf-8"))
            rec.line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
            rec.estimated_tokens = estimate_tokens(len(text))
            clipped = text[:MAX_RETAINED_CHARS_PER_FILE]
            rec.norm = normalise(clipped)
            if category in AGENT_LIKE_CATEGORIES or ext in DOC_EXTENSIONS:
                rec.content = clipped
            rec.parse_status = "Scanned"
        else:
            rec.parse_status = entry.get("parse_status") or "SkippedUnsupported"
            rec.skip_reason = entry.get("skip_reason") or "Not analysed"
        inv.files.append(rec)

    inv.total_files = len(inv.files)
    inv.parsed_files = sum(1 for f in inv.files if f.parse_status == "Scanned")
    inv.skipped_files = inv.total_files - inv.parsed_files
    inv.analyzed_tokens = sum(f.estimated_tokens for f in inv.files if f.parse_status == "Scanned")
    reasons: dict = {}
    for f in inv.files:
        if f.parse_status != "Scanned":
            reasons[f.parse_status] = reasons.get(f.parse_status, 0) + 1
    inv.skip_reasons = reasons
    return inv


class _TextBudget:
    """Tracks how much repository text has been retained for in-memory analysis."""

    def __init__(self, limit: int = MAX_RETAINED_TEXT_BYTES):
        self.limit = limit
        self.used = 0
        self.exhausted_reported = False

    def has_room(self) -> bool:
        return self.used < self.limit

    def take(self, chars: int) -> None:
        self.used += chars


def _walk_repository(root_dir: str) -> list:
    """Return [(relative_path, absolute_path)] for every analysable file on disk."""
    found: list = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Only the literal ".git" object store is dropped. ".github" must stay: it holds
        # copilot-instructions.md, agents/*.agent.md and prompts/*.prompt.md.
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIR_PARTS]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root_dir).replace("\\", "/")
            found.append((rel, full))
    return found


def _scan_priority(item: tuple) -> tuple:
    """Agent assets first, then other supported text, then everything else."""
    rel, _ = item
    ext = os.path.splitext(rel)[1].lower()
    if classify(rel) in AGENT_LIKE_CATEGORIES:
        return (0, rel)
    if ext in SUPPORTED_EXTENSIONS:
        return (1, rel)
    return (2, rel)


def _file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _retain_text(rec: FileRecord, text: str, budget: _TextBudget, inv: Inventory) -> None:
    """Keep a clipped copy of the text for similarity and block detection, within budget."""
    if not budget.has_room():
        if not budget.exhausted_reported:
            budget.exhausted_reported = True
            inv.warnings.append(
                "Repository text exceeded the in-memory analysis budget. Metadata and token "
                "counts are complete, but duplicate detection covers the most relevant files only."
            )
        return
    clipped = text[:MAX_RETAINED_CHARS_PER_FILE]
    rec.norm = normalise(clipped)
    if rec.category in AGENT_LIKE_CATEGORIES or rec.extension in DOC_EXTENSIONS:
        rec.content = clipped
    budget.take(len(clipped))


def _parse_file(rec: FileRecord, full: str, budget: _TextBudget, inv: Inventory) -> None:
    """Populate parse status, line count, tokens and retained text for one file."""
    if rec.extension not in SUPPORTED_EXTENSIONS:
        rec.parse_status = "SkippedUnsupported"
        rec.skip_reason = f"Extension '{rec.extension or 'none'}' is not in the supported analysis list"
        return
    if rec.size_bytes > MAX_PARSE_FILE_BYTES:
        rec.parse_status = "SkippedOversized"
        rec.skip_reason = f"File is {rec.size_bytes / 1048576:.1f} MB which is above the 5 MB parse limit"
        return
    try:
        with open(full, "rb") as fh:
            blob = fh.read()
    except Exception as exc:  # noqa: BLE001 - surfaced to the user as ParseError
        rec.parse_status = "ParseError"
        rec.skip_reason = f"Could not read file: {exc}"
        return
    if _looks_binary(blob):
        rec.parse_status = "Binary"
        rec.skip_reason = "File contains binary data"
        return
    text = blob.decode("utf-8", errors="replace")
    rec.line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    rec.estimated_tokens = estimate_tokens(len(text))
    rec.parse_status = "Scanned"
    _retain_text(rec, text, budget, inv)


def _finalise_inventory(inv: Inventory) -> Inventory:
    inv.parsed_files = sum(1 for f in inv.files if f.parse_status == "Scanned")
    inv.skipped_files = sum(1 for f in inv.files if f.parse_status != "Scanned")
    inv.analyzed_tokens = sum(f.estimated_tokens for f in inv.files if f.parse_status == "Scanned")
    reasons: dict = {}
    for f in inv.files:
        if f.parse_status != "Scanned":
            reasons[f.parse_status] = reasons.get(f.parse_status, 0) + 1
    inv.skip_reasons = reasons
    return inv


def build_inventory(root_dir: str, progress_cb=None) -> Inventory:
    inv = Inventory()
    all_paths = _walk_repository(root_dir)
    inv.total_files = len(all_paths)
    all_paths.sort(key=_scan_priority)
    considered = all_paths[:MAX_FILES]
    if len(all_paths) > MAX_FILES:
        inv.truncated = True
        inv.warnings.append(
            f"Repository contains {len(all_paths)} files which is above the {MAX_FILES} file limit. "
            f"The {MAX_FILES} most relevant files (agent assets first) were inventoried; "
            f"{len(all_paths) - MAX_FILES} files were not included."
        )

    budget = _TextBudget()
    for idx, (rel, full) in enumerate(considered):
        ext = os.path.splitext(rel)[1].lower()
        category = classify(rel)
        rec = FileRecord(
            path=rel, extension=ext, category=category,
            inventory_group=inventory_group_for(category, ext),
            size_bytes=_file_size(full), agent_like=category in AGENT_LIKE_CATEGORIES,
        )
        _parse_file(rec, full, budget, inv)
        inv.files.append(rec)
        if progress_cb and idx % 200 == 0:
            progress_cb(idx, len(considered))

    return _finalise_inventory(inv)
