"""LLM powered recommendation drafts.

Every draft is a refined version of a file that already exists in the repository.
The output filename is the original stem with `-optimised` appended.
"""
from __future__ import annotations

import os
import re
from typing import Optional

from .classifier import estimate_tokens
from .config import CATEGORY_AGENT, CATEGORY_CONTEXT, CATEGORY_ORCHESTRATION, CATEGORY_SKILL

MAX_DRAFTS = 25
MAX_SOURCE_CHARS = 30000
MIN_SOURCE_TOKENS = 150
MIN_DRAFT_CHARS = 220

CANONICAL_NAMES = ["instruction.md", "instructions.md", "orchestrator.md", "context.md", "memory.md"]

DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-opus-4-7"

SYSTEM_PROMPT = (
    "You are Bloat Guardian, an expert at making agentic coding repositories cheaper and clearer.\n"
    "You rewrite agent instruction, orchestration, context and memory files so they keep every real "
    "requirement but remove waste.\n\n"
    "Rules you must follow:\n"
    "1. Preserve every genuine rule, constraint, tool name, file path and acceptance criterion from the "
    "original. Never invent new product requirements.\n"
    "2. Remove duplicated paragraphs, restated boilerplate, filler prose and repeated preambles.\n"
    "3. Replace long prose with tight bullet lists and short headings.\n"
    "4. If the same instruction appears more than once, keep it once in the most logical section.\n"
    "5. Keep the writing plain and direct, readable at roughly a grade 8 level.\n"
    "6. Target a meaningful reduction in length, ideally 35-60 percent smaller, without losing meaning.\n"
    "7. Output ONLY the rewritten markdown file body. No preamble, no explanation, no code fences "
    "around the whole document.\n"
    "8. Start the file with a single H1 title, then a short 'Purpose' section of at most 3 lines."
)


def target_type_for(path: str, category: str) -> str:
    name = os.path.basename(path).lower()
    if "orchestrat" in name or "workflow" in name or "pipeline" in name:
        return "orchestrator"
    if "memory" in name:
        return "memory"
    if "context" in name or "knowledge" in name:
        return "context"
    if category == CATEGORY_CONTEXT:
        return "context"
    if category == CATEGORY_ORCHESTRATION:
        return "orchestrator"
    return "instruction"


def optimised_name(path: str) -> str:
    base = os.path.basename(path)
    stem, ext = os.path.splitext(base)
    if not ext:
        ext = ".md"
    return f"{stem}-optimised{ext if ext == '.md' else '.md'}"


def select_draft_targets(files: list, analysis: dict, limit: int = MAX_DRAFTS) -> list:
    """Pick eligible files (agent / orchestration / instruction / context / memory only)."""
    eligible = [
        f for f in files
        if f.parse_status == "Scanned" and f.content
        and f.estimated_tokens >= MIN_SOURCE_TOKENS
        and f.category in (CATEGORY_AGENT, CATEGORY_ORCHESTRATION, CATEGORY_CONTEXT, CATEGORY_SKILL)
    ]
    dup_paths = {p for c in analysis.get("clusters", []) for p in c.get("files", [])}
    block_paths = set()
    for iss in analysis.get("issues", []):
        if iss["category"] == "redundancy":
            block_paths.update(iss.get("impacted_files") or [])
    oversized = {
        p for iss in analysis.get("issues", []) if iss["category"] == "token_bloat"
        for p in (iss.get("impacted_files") or [])
    }

    def rank(f):
        name = os.path.basename(f.path).lower()
        canonical = 0 if name in CANONICAL_NAMES else 1
        problem = 0 if (f.path in oversized or f.path in dup_paths or f.path in block_paths) else 1
        return (canonical, problem, -f.estimated_tokens, f.path)

    eligible.sort(key=rank)
    picked = eligible[:limit]
    targets = []
    for f in picked:
        ttype = target_type_for(f.path, f.category)
        related = sorted({p for c in analysis.get("clusters", []) if f.path in c.get("files", [])
                          for p in c.get("files", []) if p != f.path})[:6]
        big = f.estimated_tokens > 8000
        targets.append({
            "source_path": f.path,
            "target_filename": optimised_name(f.path),
            "target_type": ttype,
            "source_tokens": f.estimated_tokens,
            "impact": "High" if (big or related) else ("Medium" if f.estimated_tokens > 2000 else "Low"),
            "effort": "Small" if f.estimated_tokens <= 4000 else ("Medium" if f.estimated_tokens <= 20000 else "Large"),
            "related_duplicates": related,
            "content": f.content,
        })
    return targets


def build_user_prompt(target: dict, repo_name: str) -> str:
    content = target["content"][:MAX_SOURCE_CHARS]
    truncated = len(target["content"]) > MAX_SOURCE_CHARS
    dupes = target.get("related_duplicates") or []
    parts = [
        f"Repository: {repo_name}",
        f"File to rewrite: {target['source_path']}",
        f"File type: {target['target_type']}",
        f"Current estimated size: {target['source_tokens']:,} tokens",
    ]
    if dupes:
        parts.append(
            "This file is a near duplicate of: " + ", ".join(dupes)
            + ". Write the rewrite so it can act as the single source of truth for all of them."
        )
    if target["source_tokens"] > 8000:
        parts.append(
            "This file is oversized. Produce a short always-on core, and clearly mark detail sections "
            "that could be moved into separate on-demand files."
        )
    if truncated:
        parts.append("Note: only the first 30,000 characters of the file are shown.")
    parts.append("---- ORIGINAL FILE CONTENT ----")
    parts.append(content)
    parts.append("---- END ORIGINAL FILE CONTENT ----")
    parts.append(
        "Now output the rewritten, de-duplicated markdown file only."
    )
    return "\n\n".join(parts)


def _clean_output(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^```(?:markdown|md)?\s*\n", "", t)
    t = re.sub(r"\n```\s*$", "", t)
    return t.strip()


async def generate_draft(
    target: dict,
    repo_name: str,
    api_key: str,
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    session_id: Optional[str] = None,
) -> dict:
    """Call the LLM and return a RecommendationDraft-shaped dict."""
    from emergentintegrations.llm.chat import LlmChat, StreamDone, TextDelta, UserMessage

    kwargs = {
        "api_key": api_key,
        "session_id": session_id or f"bg-draft-{abs(hash(target['source_path'])) % 10**10}",
        "system_message": SYSTEM_PROMPT,
    }
    if provider == "anthropic" and model.startswith("claude-opus-4-7"):
        kwargs["custom_headers"] = {"anthropic-beta": "task-budgets-2026-03-13"}
    chat = LlmChat(**kwargs).with_model(provider, model)
    if provider == "anthropic" and model.startswith("claude-opus-4-7"):
        chat = chat.with_params(
            extra_body={
                "output_config": {
                    "task_budget": {"type": "tokens", "total": 20000},
                    "effort": "medium",
                }
            },
            max_tokens=16000,
        )
    else:
        chat = chat.with_params(max_tokens=8000)

    async def run(extra: str = "") -> str:
        buf = []
        prompt = build_user_prompt(target, repo_name)
        if extra:
            prompt = f"{prompt}\n\n{extra}"
        async for ev in chat.stream_message(UserMessage(text=prompt)):
            if isinstance(ev, TextDelta):
                buf.append(ev.content)
            elif isinstance(ev, StreamDone):
                break
        return _clean_output("".join(buf))

    draft = await run()
    source_tokens = int(target.get("source_tokens") or 0)
    source_chars = len(target.get("content") or "")
    min_expected = max(MIN_DRAFT_CHARS, int(min(source_chars, MAX_SOURCE_CHARS) * 0.18))
    if len(draft) < min_expected:
        draft = await run(
            "Your previous answer was far too short to be a usable replacement file. Produce the FULL "
            "rewritten markdown document again. Keep every real rule, constraint, tool name, file path "
            f"and acceptance criterion from the original. The rewrite must be at least {min_expected} "
            "characters long and should land around 40 to 65 percent of the original length. "
            "Output only the markdown body."
        )
    quality_warning = None
    if len(draft) < 80:
        raise RuntimeError(
            "The model returned a draft that was too short to be usable. Try again, or pick a larger file."
        )
    if len(draft) < min_expected:
        quality_warning = (
            "This rewrite came back much shorter than expected. Read it side by side with the original "
            "before you replace anything, in case a rule was dropped."
        )

    new_tokens = estimate_tokens(len(draft))
    saved = max(0, target["source_tokens"] - new_tokens)
    return {
        "source_path": target["source_path"],
        "target_filename": target["target_filename"],
        "target_type": target["target_type"],
        "impact": target["impact"],
        "effort": target["effort"],
        "draft_content": draft,
        "original_tokens": target["source_tokens"],
        "draft_tokens": new_tokens,
        "tokens_saved_per_load": saved,
        "reduction_pct": round((saved / target["source_tokens"] * 100) if target["source_tokens"] else 0.0, 1),
        "model": f"{provider}/{model}",
        "quality_warning": quality_warning,
    }
