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


DRAFTABLE_CATEGORIES = (CATEGORY_AGENT, CATEGORY_ORCHESTRATION, CATEGORY_CONTEXT, CATEGORY_SKILL)


def _is_draft_eligible(f) -> bool:
    """Only agent, orchestration, context, memory and skill files are worth rewriting."""
    return (
        f.parse_status == "Scanned"
        and bool(f.content)
        and f.estimated_tokens >= MIN_SOURCE_TOKENS
        and f.category in DRAFTABLE_CATEGORIES
    )


def _problem_paths(analysis: dict) -> set:
    """Paths the adversary scan already flagged: duplicate clusters, repeated blocks, oversized."""
    paths = {p for c in analysis.get("clusters", []) for p in c.get("files", [])}
    for iss in analysis.get("issues", []):
        if iss["category"] in ("redundancy", "token_bloat"):
            paths.update(iss.get("impacted_files") or [])
    return paths


def _rank_key(problem_paths: set):
    """Canonical filenames first, then flagged files, then largest, then path for stability."""
    def key(f):
        canonical = 0 if os.path.basename(f.path).lower() in CANONICAL_NAMES else 1
        problem = 0 if f.path in problem_paths else 1
        return (canonical, problem, -f.estimated_tokens, f.path)
    return key


def _cluster_siblings(analysis: dict, path: str) -> list:
    return sorted({
        p for c in analysis.get("clusters", []) if path in c.get("files", [])
        for p in c.get("files", []) if p != path
    })[:6]


def _impact_for(tokens: int, related: list) -> str:
    if tokens > 8000 or related:
        return "High"
    return "Medium" if tokens > 2000 else "Low"


def _effort_for(tokens: int) -> str:
    if tokens <= 4000:
        return "Small"
    return "Medium" if tokens <= 20000 else "Large"


def select_draft_targets(files: list, analysis: dict, limit: int = MAX_DRAFTS) -> list:
    """Pick eligible files (agent / orchestration / instruction / context / memory only)."""
    eligible = [f for f in files if _is_draft_eligible(f)]
    eligible.sort(key=_rank_key(_problem_paths(analysis)))
    targets = []
    for f in eligible[:limit]:
        related = _cluster_siblings(analysis, f.path)
        targets.append({
            "source_path": f.path,
            "target_filename": optimised_name(f.path),
            "target_type": target_type_for(f.path, f.category),
            "source_tokens": f.estimated_tokens,
            "impact": _impact_for(f.estimated_tokens, related),
            "effort": _effort_for(f.estimated_tokens),
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


RETRY_INSTRUCTION = (
    "Your previous answer was far too short to be a usable replacement file. Produce the FULL "
    "rewritten markdown document again. Keep every real rule, constraint, tool name, file path "
    "and acceptance criterion from the original. The rewrite must be at least {min_expected} "
    "characters long and should land around 40 to 65 percent of the original length. "
    "Output only the markdown body."
)

SHORT_DRAFT_WARNING = (
    "This rewrite came back much shorter than expected. Read it side by side with the original "
    "before you replace anything, in case a rule was dropped."
)


def _uses_task_budget(provider: str, model: str) -> bool:
    """Claude Opus 4.7 supports the task-budget beta, which keeps long rewrites affordable."""
    return provider == "anthropic" and model.startswith("claude-opus-4-7")


def _build_chat(api_key: str, provider: str, model: str, session_id: Optional[str], source_path: str):
    from emergentintegrations.llm.chat import LlmChat

    kwargs = {
        "api_key": api_key,
        "session_id": session_id or f"bg-draft-{abs(hash(source_path)) % 10**10}",
        "system_message": SYSTEM_PROMPT,
    }
    if _uses_task_budget(provider, model):
        kwargs["custom_headers"] = {"anthropic-beta": "task-budgets-2026-03-13"}
    chat = LlmChat(**kwargs).with_model(provider, model)
    if _uses_task_budget(provider, model):
        return chat.with_params(
            extra_body={
                "output_config": {
                    "task_budget": {"type": "tokens", "total": 20000},
                    "effort": "medium",
                }
            },
            max_tokens=16000,
        )
    return chat.with_params(max_tokens=8000)


async def _stream_draft(chat, prompt: str) -> str:
    from emergentintegrations.llm.chat import StreamDone, TextDelta, UserMessage

    buf = []
    async for ev in chat.stream_message(UserMessage(text=prompt)):
        if isinstance(ev, TextDelta):
            buf.append(ev.content)
        elif isinstance(ev, StreamDone):
            break
    return _clean_output("".join(buf))


def _min_expected_chars(target: dict) -> int:
    """A usable rewrite is never a tiny fraction of its source."""
    source_chars = len(target.get("content") or "")
    return max(MIN_DRAFT_CHARS, int(min(source_chars, MAX_SOURCE_CHARS) * 0.18))


def _draft_record(target: dict, draft: str, provider: str, model: str,
                  quality_warning: Optional[str]) -> dict:
    new_tokens = estimate_tokens(len(draft))
    source_tokens = target["source_tokens"]
    saved = max(0, source_tokens - new_tokens)
    return {
        "source_path": target["source_path"],
        "target_filename": target["target_filename"],
        "target_type": target["target_type"],
        "impact": target["impact"],
        "effort": target["effort"],
        "draft_content": draft,
        "original_tokens": source_tokens,
        "draft_tokens": new_tokens,
        "tokens_saved_per_load": saved,
        "reduction_pct": round((saved / source_tokens * 100) if source_tokens else 0.0, 1),
        "model": f"{provider}/{model}",
        "quality_warning": quality_warning,
    }


async def generate_draft(
    target: dict,
    repo_name: str,
    api_key: str,
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    session_id: Optional[str] = None,
) -> dict:
    """Call the LLM and return a RecommendationDraft-shaped dict."""
    chat = _build_chat(api_key, provider, model, session_id, target["source_path"])
    prompt = build_user_prompt(target, repo_name)
    min_expected = _min_expected_chars(target)

    draft = await _stream_draft(chat, prompt)
    if len(draft) < min_expected:
        # One retry: over-compression loses real rules, so ask again with an explicit floor.
        draft = await _stream_draft(
            chat, f"{prompt}\n\n{RETRY_INSTRUCTION.format(min_expected=min_expected)}")

    if len(draft) < 80:
        raise RuntimeError(
            "The model returned a draft that was too short to be usable. Try again, or pick a larger file."
        )
    warning = None if len(draft) >= min_expected else SHORT_DRAFT_WARNING
    return _draft_record(target, draft, provider, model, warning)
