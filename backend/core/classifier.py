"""File walking, classification, token estimation and inventory building."""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Optional

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


def classify(rel_path: str) -> str:
    p = "/" + rel_path.replace("\\", "/").lower()
    name = p.rsplit("/", 1)[-1]
    ext = os.path.splitext(name)[1]

    if any(name.endswith(s) for s in AGENT_SUFFIXES) or name in AGENT_FILENAMES:
        return CATEGORY_AGENT
    if any(part in p for part in AGENT_DIR_PARTS):
        return CATEGORY_AGENT
    if any(name.endswith(s) for s in SKILL_SUFFIXES) or name in SKILL_FILENAMES:
        return CATEGORY_SKILL
    if any(part in p for part in SKILL_DIR_PARTS):
        return CATEGORY_SKILL
    if any(name.endswith(s) for s in CONTEXT_SUFFIXES) or name in CONTEXT_FILENAMES:
        return CATEGORY_CONTEXT
    if any(part in p for part in CONTEXT_DIR_PARTS):
        return CATEGORY_CONTEXT
    if any(name.endswith(s) for s in ORCHESTRATION_SUFFIXES) or name in ORCHESTRATION_FILENAMES:
        return CATEGORY_ORCHESTRATION
    if any(part in p for part in ORCHESTRATION_DIR_PARTS):
        return CATEGORY_ORCHESTRATION
    if ext in DIAGRAM_EXTENSIONS:
        return CATEGORY_DIAGRAM
    if ext in SOURCE_EXTENSIONS:
        return CATEGORY_SOURCE
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


def build_inventory(root_dir: str, progress_cb=None) -> Inventory:
    inv = Inventory()
    all_paths: list = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIR_PARTS and not d.startswith(".git")]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root_dir).replace("\\", "/")
            all_paths.append((rel, full))

    inv.total_files = len(all_paths)

    def priority(item):
        rel, _ = item
        cat = classify(rel)
        ext = os.path.splitext(rel)[1].lower()
        if cat in AGENT_LIKE_CATEGORIES:
            return (0, rel)
        if ext in SUPPORTED_EXTENSIONS:
            return (1, rel)
        return (2, rel)

    all_paths.sort(key=priority)
    considered = all_paths[:MAX_FILES]
    retained = [0]
    memory_warned = [False]
    if len(all_paths) > MAX_FILES:
        inv.truncated = True
        inv.warnings.append(
            f"Repository contains {len(all_paths)} files which is above the {MAX_FILES} file limit. "
            f"The {MAX_FILES} most relevant files (agent assets first) were inventoried; "
            f"{len(all_paths) - MAX_FILES} files were not included."
        )

    for idx, (rel, full) in enumerate(considered):
        ext = os.path.splitext(rel)[1].lower()
        category = classify(rel)
        group = inventory_group_for(category, ext)
        try:
            size = os.path.getsize(full)
        except OSError:
            size = 0
        rec = FileRecord(
            path=rel, extension=ext, category=category, inventory_group=group,
            size_bytes=size, agent_like=category in AGENT_LIKE_CATEGORIES,
        )

        if ext not in SUPPORTED_EXTENSIONS:
            rec.parse_status = "SkippedUnsupported"
            rec.skip_reason = f"Extension '{ext or 'none'}' is not in the supported analysis list"
        elif size > MAX_PARSE_FILE_BYTES:
            rec.parse_status = "SkippedOversized"
            rec.skip_reason = f"File is {size / 1048576:.1f} MB which is above the 5 MB parse limit"
        else:
            try:
                with open(full, "rb") as fh:
                    blob = fh.read()
                if _looks_binary(blob):
                    rec.parse_status = "Binary"
                    rec.skip_reason = "File contains binary data"
                else:
                    text = blob.decode("utf-8", errors="replace")
                    rec.line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
                    rec.estimated_tokens = estimate_tokens(len(text))
                    rec.parse_status = "Scanned"
                    if retained[0] < MAX_RETAINED_TEXT_BYTES:
                        clipped = text[:MAX_RETAINED_CHARS_PER_FILE]
                        rec.norm = normalise(clipped)
                        if category in AGENT_LIKE_CATEGORIES or ext in DOC_EXTENSIONS:
                            rec.content = clipped
                        retained[0] += len(clipped)
                    elif not memory_warned[0]:
                        memory_warned[0] = True
                        inv.warnings.append(
                            "Repository text exceeded the in-memory analysis budget. Metadata and token "
                            "counts are complete, but duplicate detection covers the most relevant files only."
                        )
            except Exception as exc:
                rec.parse_status = "ParseError"
                rec.skip_reason = f"Could not read file: {exc}"

        inv.files.append(rec)
        if progress_cb and idx % 200 == 0:
            progress_cb(idx, len(considered))

    inv.parsed_files = sum(1 for f in inv.files if f.parse_status == "Scanned")
    inv.skipped_files = sum(1 for f in inv.files if f.parse_status != "Scanned")
    inv.analyzed_tokens = sum(f.estimated_tokens for f in inv.files if f.parse_status == "Scanned")
    reasons: dict = {}
    for f in inv.files:
        if f.parse_status != "Scanned":
            reasons[f.parse_status] = reasons.get(f.parse_status, 0) + 1
    inv.skip_reasons = reasons
    return inv
