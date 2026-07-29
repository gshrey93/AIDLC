"""The adversary scan: deterministic heuristics, scoring, issues and savings."""
from __future__ import annotations

import os
import re
import statistics
from collections import defaultdict
from datetime import datetime, timezone

from .classifier import Inventory, estimate_tokens, is_generated, normalise
from .config import (
    AGENT_LIKE_CATEGORIES, AGENT_SPRAWL_THRESHOLD, CATEGORY_AGENT, CATEGORY_CONTEXT,
    CATEGORY_LABELS, CATEGORY_ORCHESTRATION, CATEGORY_SKILL, CATEGORY_SOURCE,
    CATEGORY_WEIGHTS, MICROSERVICE_DIR_THRESHOLD, MICROSERVICE_SOURCE_FLOOR,
    MIN_CHARS_FOR_SIMILARITY, MIN_TEXT_FILES_FOR_VALID_SCAN, MONOLITH_AGENT_ROLE_THRESHOLD,
    OVERSIZED_CONTEXT_TOKENS, PARTIAL_SCAN_SKIP_RATIO, PENALTIES, REPEATED_BLOCK_MIN_CHARS,
    REPEATED_BLOCK_MIN_FILES, REVIEW_STAGE_PATTERNS, REVIEW_STAGE_THRESHOLD,
    SERVICE_MARKER_FILES, SERVICE_PARENT_DIRS, SIMILARITY_DUPLICATE_THRESHOLD,
    SIMILARITY_FORMULA, SIMILARITY_OVERLAP_THRESHOLD, TOKEN_FORMULA,
    merged_assumptions, verdict_for_score,
)
from .similarity import (
    UnionFind, bottom_k_sketch, candidate_pairs, exact_jaccard, sketch_jaccard, shingle_set,
)

BLOCK_SPLIT_RE = re.compile(r"\n\s*\n")


def _short(path: str, width: int = 58) -> str:
    return path if len(path) <= width else "..." + path[-(width - 3):]


# ------------------------------------------------------------- detections
def detect_near_duplicates(files: list):
    """Return (clusters, overlap_groups) where clusters use >=0.80 similarity."""
    candidates = [
        f for f in files
        if f.parse_status == "Scanned" and f.norm and len(f.norm) >= MIN_CHARS_FOR_SIMILARITY
    ]
    if len(candidates) < 2:
        return [], []

    shingles = [shingle_set(f.norm) for f in candidates]
    sketches = [bottom_k_sketch(s) for s in shingles]
    pairs = candidate_pairs(sketches)

    scored = []
    for a, b in pairs:
        est = sketch_jaccard(sketches[a], sketches[b])
        if est < 0.30:
            continue
        sim = exact_jaccard(shingles[a], shingles[b])
        if sim >= SIMILARITY_OVERLAP_THRESHOLD:
            scored.append((a, b, sim))

    dup_uf = UnionFind(len(candidates))
    ovl_uf = UnionFind(len(candidates))
    pair_sim = {}
    for a, b, sim in scored:
        ovl_uf.union(a, b)
        if sim >= SIMILARITY_DUPLICATE_THRESHOLD:
            dup_uf.union(a, b)
            pair_sim[(a, b)] = sim

    clusters = []
    for gi, (_, members) in enumerate(sorted(dup_uf.groups().items()), start=1):
        member_files = [candidates[m] for m in members]
        sims = [s for (a, b), s in pair_sim.items() if a in members and b in members]
        group_id = f"DUP-{gi:03d}"
        for mf in member_files:
            mf.similarity_group = group_id
        clusters.append({
            "group_id": group_id,
            "files": [f.path for f in member_files],
            "file_records": member_files,
            "max_similarity": round(max(sims) if sims else SIMILARITY_DUPLICATE_THRESHOLD, 4),
            "avg_similarity": round(sum(sims) / len(sims), 4) if sims else SIMILARITY_DUPLICATE_THRESHOLD,
            "agent_like_members": [f.path for f in member_files if f.agent_like],
            "tokens": [f.estimated_tokens for f in member_files],
        })

    overlap_groups = []
    for gi, (_, members) in enumerate(sorted(ovl_uf.groups().items()), start=1):
        member_files = [candidates[m] for m in members]
        agentish = [f for f in member_files if f.agent_like]
        if len(agentish) >= 2:
            overlap_groups.append({
                "group_id": f"OVL-{gi:03d}",
                "files": [f.path for f in agentish],
                "roles": len(agentish),
            })
    return clusters, overlap_groups


def detect_repeated_blocks(files: list):
    targets = [f for f in files if f.parse_status == "Scanned" and f.agent_like and f.content]
    index = defaultdict(lambda: {"files": set(), "sample": "", "chars": 0})
    for f in targets:
        seen_local = set()
        for raw_block in BLOCK_SPLIT_RE.split(f.content):
            norm = normalise(raw_block)
            if len(norm) < REPEATED_BLOCK_MIN_CHARS:
                continue
            key = norm[:4000]
            if key in seen_local:
                continue
            seen_local.add(key)
            entry = index[key]
            entry["files"].add(f.path)
            entry["chars"] = len(norm)
            if not entry["sample"]:
                entry["sample"] = raw_block.strip()[:400]
    groups = []
    for key, entry in index.items():
        if len(entry["files"]) >= REPEATED_BLOCK_MIN_FILES:
            groups.append({
                "files": sorted(entry["files"]),
                "file_count": len(entry["files"]),
                "block_chars": entry["chars"],
                "block_tokens": estimate_tokens(entry["chars"]),
                "sample": entry["sample"],
            })
    groups.sort(key=lambda g: (-g["file_count"], -g["block_chars"]))
    return groups


def detect_review_stages(files: list):
    text_parts = []
    evidence_files = defaultdict(set)
    for f in files:
        if f.parse_status != "Scanned" or not f.content:
            continue
        if not (f.agent_like or f.extension in (".md", ".txt")):
            continue
        low = f.content.lower()
        text_parts.append((f.path, low))
    found = {}
    for stage, patterns in REVIEW_STAGE_PATTERNS.items():
        for path, low in text_parts:
            if any(re.search(p, low) for p in patterns):
                found[stage] = found.get(stage, 0) + 1
                evidence_files[stage].add(path)
    stages = sorted(found.keys())
    return {
        "stages": stages,
        "count": len(stages),
        "evidence": {s: sorted(list(evidence_files[s]))[:4] for s in stages},
    }


def detect_architecture(files: list):
    service_dirs = set()
    for f in files:
        parts = f.path.split("/")
        name = parts[-1].lower()
        for i, part in enumerate(parts[:-1]):
            if part.lower() in SERVICE_PARENT_DIRS and i + 1 < len(parts) - 1:
                service_dirs.add("/".join(parts[: i + 2]))
        if name in SERVICE_MARKER_FILES or name.endswith(".csproj"):
            parent = "/".join(parts[:-1])
            if parent and len(parts) <= 4:
                service_dirs.add(parent)
    non_generated_source = [
        f for f in files
        if f.category == CATEGORY_SOURCE and not is_generated(f.path) and f.parse_status == "Scanned"
    ]
    return {
        "service_dirs": sorted(service_dirs),
        "service_dir_count": len(service_dirs),
        "non_generated_source_files": len(non_generated_source),
    }


# ---------------------------------------------------------------- scoring
def _capped(count: int, key: str) -> int:
    cfg = PENALTIES[key]
    return min(cfg["cap"], cfg["points"] * max(0, count))


def analyze(inventory: Inventory, assumptions_overrides: dict | None = None, scan_date: datetime | None = None) -> dict:
    a = merged_assumptions(assumptions_overrides)
    scan_date = scan_date or datetime.now(timezone.utc)
    date_key = scan_date.strftime("%Y-%m-%d")
    files = inventory.files
    parsed = [f for f in files if f.parse_status == "Scanned"]

    agent_like = [f for f in files if f.agent_like]
    agent_role = [f for f in files if f.category == CATEGORY_AGENT]
    context_files = [f for f in files if f.category == CATEGORY_CONTEXT]
    orchestration_files = [f for f in files if f.category == CATEGORY_ORCHESTRATION]
    skill_files = [f for f in files if f.category == CATEGORY_SKILL]

    insufficient = len(parsed) < MIN_TEXT_FILES_FOR_VALID_SCAN

    clusters, overlap_groups = detect_near_duplicates(files)
    blocks = detect_repeated_blocks(files)
    review = detect_review_stages(files)
    arch = detect_architecture(files)

    oversized_context = [f for f in context_files if f.estimated_tokens > OVERSIZED_CONTEXT_TOKENS]

    # ---- penalty counting -------------------------------------------------
    dup_pairs = 0
    for c in clusters:
        agentish = len(c["agent_like_members"])
        if agentish >= 2:
            dup_pairs += agentish - 1
    penalty_near_dup = _capped(dup_pairs, "near_duplicate")
    penalty_blocks = _capped(len(blocks), "repeated_block")
    penalty_oversized = _capped(len(oversized_context), "oversized_context")
    sprawl_extra = max(0, len(agent_like) - AGENT_SPRAWL_THRESHOLD)
    penalty_sprawl = _capped(sprawl_extra, "agent_sprawl")
    extra_stages = max(0, review["count"] - REVIEW_STAGE_THRESHOLD)
    penalty_review = _capped(extra_stages, "review_stages")

    micro_mismatch = (
        arch["service_dir_count"] >= MICROSERVICE_DIR_THRESHOLD
        and arch["non_generated_source_files"] < MICROSERVICE_SOURCE_FLOOR
    )
    monolith_mismatch = (
        arch["service_dir_count"] <= 1
        and len(agent_role) >= MONOLITH_AGENT_ROLE_THRESHOLD
        and len(overlap_groups) >= 1
    )
    penalty_micro = PENALTIES["microservice_mismatch"]["points"] if micro_mismatch else 0
    penalty_mono = PENALTIES["monolith_mismatch"]["points"] if monolith_mismatch else 0

    cat_penalties = {
        "redundancy": penalty_near_dup + penalty_blocks,
        "token_bloat": penalty_oversized,
        "review_overhead": penalty_review,
        "agent_sprawl": penalty_sprawl,
        "architecture_inefficiency": penalty_micro + penalty_mono,
    }
    cat_scores = {k: max(0, min(100, 100 - v)) for k, v in cat_penalties.items()}
    overall = int(round(sum(cat_scores[k] * w for k, w in CATEGORY_WEIGHTS.items())))
    overall = max(0, min(100, overall))
    verdict = verdict_for_score(overall)

    total_considered = len(files) or 1
    skip_ratio = inventory.skipped_files / total_considered
    partial_scan = skip_ratio > PARTIAL_SCAN_SKIP_RATIO

    # ---- savings helpers --------------------------------------------------
    runs = float(a["agent_runs_per_month"])
    out_share = float(a["output_token_share"])
    tokens_per_credit = float(a["tokens_per_report_credit"])

    def to_credits(tokens: float) -> float:
        return round(tokens / tokens_per_credit, 4)

    def to_dollars(tokens: float) -> float:
        inp = tokens * (1 - out_share)
        outp = tokens * out_share
        return round(
            inp / 1_000_000 * a["input_dollars_per_million"]
            + outp / 1_000_000 * a["output_dollars_per_million"],
            2,
        )

    agent_tokens = [f.estimated_tokens for f in agent_like if f.estimated_tokens]
    median_agent_tokens = int(statistics.median(agent_tokens)) if agent_tokens else 0
    instruction_tokens = [f.estimated_tokens for f in (orchestration_files + agent_role) if f.estimated_tokens]
    avg_instruction_tokens = int(statistics.mean(instruction_tokens)) if instruction_tokens else 0
    total_agent_like_tokens = sum(agent_tokens)

    issues = []
    seq = 0

    def add_issue(severity, category, title, description, evidence, impacted, monthly_tokens,
                  recommendation, impact, effort, formula, files_list=None):
        nonlocal seq
        seq += 1
        monthly_tokens = max(0.0, float(monthly_tokens))
        issues.append({
            "id": f"ISS-{date_key}-{seq:04d}",
            "severity": severity,
            "category": category,
            "title": title,
            "description": description,
            "evidence": evidence,
            "impacted_file_count": impacted,
            "impacted_files": files_list or [],
            "estimated_token_waste": int(round(monthly_tokens)),
            "estimated_credit_waste": to_credits(monthly_tokens),
            "estimated_dollar_waste": to_dollars(monthly_tokens),
            "recommendation": recommendation,
            "impact": impact,
            "effort": effort,
            "formula": formula,
        })

    def severity_for(tokens: float) -> str:
        if tokens >= 4_000_000:
            return "critical"
        if tokens >= 1_000_000:
            return "high"
        if tokens >= 200_000:
            return "medium"
        return "low"

    if not insufficient:
        # 1. duplicate clusters
        for c in sorted(clusters, key=lambda x: -sum(x["tokens"]))[:80]:
            tokens_sorted = sorted(c["tokens"], reverse=True)
            redundant_tokens = sum(tokens_sorted[1:])
            monthly = redundant_tokens * runs if c["agent_like_members"] else redundant_tokens * runs * 0.25
            add_issue(
                severity_for(monthly), "redundancy",
                f"{len(c['files'])} files are near copies of each other",
                "These files say almost the same thing. Every time your agents run, the same words get "
                "sent to the model more than once. Keeping one source of truth removes the repeat cost.",
                f"Group {c['group_id']} - highest similarity {c['max_similarity'] * 100:.0f}%. "
                f"Files: {', '.join(_short(p) for p in c['files'][:6])}"
                + (" ..." if len(c["files"]) > 6 else ""),
                len(c["files"]), monthly,
                "Keep the most complete file, delete or shrink the copies, and link to the kept file instead.",
                "High" if redundant_tokens > 4000 else "Medium",
                "Small" if len(c["files"]) <= 3 else "Medium",
                "monthly_waste = (sum of duplicate file tokens - largest file tokens) x runs_per_month",
                c["files"],
            )

        # 2. repeated instruction blocks
        for b in blocks[:60]:
            monthly = b["block_tokens"] * (b["file_count"] - 1) * runs
            add_issue(
                severity_for(monthly), "redundancy",
                f"The same instruction block is pasted into {b['file_count']} files",
                "One block of instructions has been copied into several agent files. Only one copy is "
                "needed. The rest is paid for on every run.",
                f"Block of {b['block_chars']} characters (~{b['block_tokens']} tokens) found in: "
                + ", ".join(_short(p) for p in b["files"][:6]) + (" ..." if len(b["files"]) > 6 else "")
                + f" | Sample: \"{b['sample'][:160]}\"",
                b["file_count"], monthly,
                "Move the shared block into one file and reference it from the others.",
                "High" if b["file_count"] >= 5 else "Medium", "Small",
                "monthly_waste = block_tokens x (files_containing_block - 1) x runs_per_month",
                b["files"],
            )

        # 3. oversized context/memory files
        for f in sorted(oversized_context, key=lambda x: -x.estimated_tokens)[:40]:
            excess = f.estimated_tokens - OVERSIZED_CONTEXT_TOKENS
            monthly = excess * runs
            add_issue(
                severity_for(monthly), "token_bloat",
                f"Context file is very large: {os.path.basename(f.path)}",
                "This memory or context file is bigger than a healthy working budget. Large context files "
                "are re-read on every run, so most of the cost is paid again and again.",
                f"{f.path} is about {f.estimated_tokens:,} tokens which is {excess:,} tokens over the "
                f"{OVERSIZED_CONTEXT_TOKENS:,} token guideline.",
                1, monthly,
                "Split this file into a short always-on summary plus detail files that load only when needed.",
                "High" if excess > 20000 else "Medium",
                "Medium",
                f"monthly_waste = (file_tokens - {OVERSIZED_CONTEXT_TOKENS}) x runs_per_month",
                [f.path],
            )

        # 4. agent sprawl
        if sprawl_extra > 0:
            monthly = sprawl_extra * median_agent_tokens * runs * 0.5
            add_issue(
                severity_for(monthly), "agent_sprawl",
                f"{len(agent_like)} agent-style files is more than this repo needs",
                "There are many separate agent, skill and prompt files. Each one adds instructions that "
                "have to be loaded and kept in sync. Fewer, clearer files cost less and break less often.",
                f"{len(agent_like)} agent-like files detected against a healthy guideline of "
                f"{AGENT_SPRAWL_THRESHOLD}. Median agent file size is {median_agent_tokens:,} tokens.",
                len(agent_like), monthly,
                "Group agents by job. Merge the ones that overlap and delete the ones nobody calls.",
                "High" if sprawl_extra > 10 else "Medium", "Large",
                "monthly_waste = extra_agent_files x median_agent_tokens x runs_per_month x 0.5",
                [f.path for f in agent_like[:25]],
            )

        # 5. review overhead
        if extra_stages > 0:
            monthly = extra_stages * avg_instruction_tokens * runs * 0.25
            add_issue(
                severity_for(monthly), "review_overhead",
                f"{review['count']} separate review or approval steps were found",
                "Your instructions describe many checks before work is accepted. Each extra check means "
                "another pass over the same material, which costs time and money.",
                "Stages inferred: " + ", ".join(review["stages"]) + ". Examples: "
                + "; ".join(f"{s} -> {_short(v[0])}" for s, v in list(review["evidence"].items())[:4] if v),
                len({p for v in review["evidence"].values() for p in v}), monthly,
                "Keep at most four review gates. Combine the overlapping ones into a single checklist.",
                "Medium" if extra_stages <= 2 else "High", "Medium",
                "monthly_waste = extra_review_stages x avg_instruction_tokens x runs_per_month x 0.25",
                sorted({p for v in review["evidence"].values() for p in v})[:20],
            )

        # 6. architecture mismatches
        if micro_mismatch:
            monthly = 0.05 * total_agent_like_tokens * runs
            add_issue(
                "high", "architecture_inefficiency",
                "Split into many services but there is little code in them",
                "The repo is arranged as many small services, yet the amount of real code is small. "
                "Each service still needs its own setup and its own instructions, so the overhead is "
                "larger than the work being done.",
                f"{arch['service_dir_count']} service directories detected with only "
                f"{arch['non_generated_source_files']} hand written source files.",
                arch["service_dir_count"], monthly,
                "Fold the thin services back together until each one has a clear, separate job.",
                "High", "Large",
                "monthly_waste = 5% x total_agent_asset_tokens x runs_per_month",
                arch["service_dirs"][:20],
            )
        if monolith_mismatch:
            monthly = 0.05 * sum(f.estimated_tokens for f in agent_role) * runs
            add_issue(
                "medium", "architecture_inefficiency",
                "One service is carrying many overlapping agent roles",
                "Everything lives in a single service, but there are many agent role files that describe "
                "similar work. That makes it hard to tell which agent owns what, and the same guidance "
                "gets repeated.",
                f"{len(agent_role)} agent role files with {len(overlap_groups)} overlapping groups inside "
                f"{arch['service_dir_count']} service directory.",
                len(agent_role), monthly,
                "Give each agent one clear job and remove duplicated role descriptions.",
                "Medium", "Medium",
                "monthly_waste = 5% x total_agent_role_tokens x runs_per_month",
                [f.path for f in agent_role[:20]],
            )

        # 7. repetitive skills
        dup_skill_paths = {p for c in clusters for p in c["files"] if "/skills/" in "/" + p.lower() or p.lower().endswith(".skill.md")}
        if len(skill_files) > 10 or len(dup_skill_paths) >= 2:
            dup_tokens = sum(f.estimated_tokens for f in skill_files if f.path in dup_skill_paths)
            monthly = (dup_tokens or max(0, len(skill_files) - 10) * median_agent_tokens) * runs * 0.5
            add_issue(
                severity_for(monthly), "agent_sprawl",
                f"{len(skill_files)} skill files, and some repeat each other",
                "Skill files are meant to be small and specific. When there are many of them and they "
                "repeat, the model reads the same guidance several times.",
                f"{len(skill_files)} skill files detected; {len(dup_skill_paths)} of them sit inside "
                f"near-duplicate groups.",
                max(len(skill_files), len(dup_skill_paths)), monthly,
                "Keep one skill file per capability and delete the near copies.",
                "Medium", "Small",
                "monthly_waste = duplicated_skill_tokens x runs_per_month x 0.5",
                sorted(dup_skill_paths)[:20] or [f.path for f in skill_files[:20]],
            )

        # 8. orchestration layers
        if len(orchestration_files) > 6:
            layers = len(orchestration_files)
            avg_orch = int(statistics.mean([f.estimated_tokens for f in orchestration_files if f.estimated_tokens] or [0]))
            monthly = (layers - 6) * avg_orch * runs * 0.2
            add_issue(
                severity_for(monthly), "review_overhead",
                f"{layers} orchestration files create extra hand-offs",
                "There are many files describing how work moves between agents. Every hand-off adds "
                "instructions that must be loaded and kept in step with the others.",
                f"{layers} orchestration or prompt files detected, average size {avg_orch:,} tokens.",
                layers, monthly,
                "Describe the flow once in a single orchestrator file and let the agents stay simple.",
                "Medium", "Medium",
                "monthly_waste = (orchestration_files - 6) x avg_orchestration_tokens x runs_per_month x 0.2",
                [f.path for f in orchestration_files[:20]],
            )

    issues.sort(key=lambda i: -i["estimated_token_waste"])

    total_tokens_waste = sum(i["estimated_token_waste"] for i in issues)
    total_dollars = round(sum(i["estimated_dollar_waste"] for i in issues), 2)
    variance = float(a["variance_pct"])
    savings = {
        "estimated_monthly_token_waste": int(total_tokens_waste),
        "estimated_monthly_credit_waste": to_credits(total_tokens_waste),
        "estimated_monthly_dollar_waste": total_dollars,
        "estimated_savings_low": round(total_dollars * (1 - variance), 2),
        "estimated_savings_high": round(total_dollars * (1 + variance), 2),
        "estimated_credit_savings_low": round(to_credits(total_tokens_waste) * (1 - variance), 2),
        "estimated_credit_savings_high": round(to_credits(total_tokens_waste) * (1 + variance), 2),
    }
    if insufficient:
        savings = {k: 0 for k in savings}

    category_scores = []
    summaries = {
        "redundancy": (
            f"{len(clusters)} groups of near-identical files and {len(blocks)} repeated instruction "
            f"blocks were found."
        ),
        "token_bloat": (
            f"{len(oversized_context)} context or memory files are over "
            f"{OVERSIZED_CONTEXT_TOKENS:,} tokens."
        ),
        "review_overhead": f"{review['count']} review or approval steps were inferred from your instructions.",
        "agent_sprawl": f"{len(agent_like)} agent-style files were found ({len(agent_role)} agent roles, {len(skill_files)} skills).",
        "architecture_inefficiency": (
            f"{arch['service_dir_count']} service directories against "
            f"{arch['non_generated_source_files']} hand written source files."
        ),
    }
    for key in CATEGORY_WEIGHTS:
        category_scores.append({
            "category": key,
            "label": CATEGORY_LABELS[key],
            "score": cat_scores[key],
            "penalty_points": cat_penalties[key],
            "weight": CATEGORY_WEIGHTS[key],
            "summary": summaries[key],
        })

    top_drivers = [{
        "rank": i + 1,
        "title": iss["title"],
        "plain_language": iss["description"],
        "category": CATEGORY_LABELS.get(iss["category"], iss["category"]),
        "estimated_token_waste": iss["estimated_token_waste"],
        "estimated_credit_waste": iss["estimated_credit_waste"],
        "estimated_dollar_waste": iss["estimated_dollar_waste"],
        "issue_id": iss["id"],
    } for i, iss in enumerate(issues[:5])]

    impact_rank = {"High": 0, "Medium": 1, "Low": 2}
    effort_rank = {"Small": 0, "Medium": 1, "Large": 2}
    seen_titles = set()
    actions = []
    for iss in sorted(issues, key=lambda x: (impact_rank.get(x["impact"], 3), effort_rank.get(x["effort"], 3), -x["estimated_token_waste"])):
        key = (iss["category"], iss["recommendation"])
        if key in seen_titles:
            continue
        seen_titles.add(key)
        actions.append({
            "issue_id": iss["id"],
            "action": iss["recommendation"],
            "category": CATEGORY_LABELS.get(iss["category"], iss["category"]),
            "impact": iss["impact"],
            "effort": iss["effort"],
            "estimated_token_reduction": iss["estimated_token_waste"],
            "estimated_credit_reduction": iss["estimated_credit_waste"],
            "estimated_dollar_savings": iss["estimated_dollar_waste"],
        })
        if len(actions) >= 20:
            break

    penalty_ledger = [
        {"rule": "Near-duplicate agent/context file pair (similarity >= 0.80)", "hits": dup_pairs,
         "points_each": 5, "cap": 32, "applied": penalty_near_dup, "category": "redundancy"},
        {"rule": f"Repeated instruction block >= {REPEATED_BLOCK_MIN_CHARS} chars in {REPEATED_BLOCK_MIN_FILES}+ files",
         "hits": len(blocks), "points_each": 4, "cap": 20, "applied": penalty_blocks, "category": "redundancy"},
        {"rule": f"Context or memory file over {OVERSIZED_CONTEXT_TOKENS:,} tokens", "hits": len(oversized_context),
         "points_each": 6, "cap": 24, "applied": penalty_oversized, "category": "token_bloat"},
        {"rule": f"Agent-like files above {AGENT_SPRAWL_THRESHOLD}", "hits": sprawl_extra,
         "points_each": 2, "cap": 20, "applied": penalty_sprawl, "category": "agent_sprawl"},
        {"rule": f"Review/approval stages above {REVIEW_STAGE_THRESHOLD}", "hits": extra_stages,
         "points_each": 5, "cap": 15, "applied": penalty_review, "category": "review_overhead"},
        {"rule": f"Microservice mismatch (>= {MICROSERVICE_DIR_THRESHOLD} service dirs and < {MICROSERVICE_SOURCE_FLOOR} source files)",
         "hits": 1 if micro_mismatch else 0, "points_each": 12, "cap": 12, "applied": penalty_micro,
         "category": "architecture_inefficiency"},
        {"rule": f"Monolith mismatch (1 service and >= {MONOLITH_AGENT_ROLE_THRESHOLD} overlapping agent roles)",
         "hits": 1 if monolith_mismatch else 0, "points_each": 10, "cap": 10, "applied": penalty_mono,
         "category": "architecture_inefficiency"},
    ]

    rates = {
        "input_dollars_per_million": a["input_dollars_per_million"],
        "output_dollars_per_million": a["output_dollars_per_million"],
    }
    assumptions_block = {
        "token_formula": TOKEN_FORMULA,
        "similarity_formula": SIMILARITY_FORMULA,
        "tokens_per_report_credit": a["tokens_per_report_credit"],
        "agent_runs_per_month": a["agent_runs_per_month"],
        "output_token_share": a["output_token_share"],
        "variance_pct": a["variance_pct"],
        "vendor_credits_per_dollar": a["vendor_credits_per_dollar"],
        "input_tokens_per_vendor_credit": a["input_tokens_per_vendor_credit"],
        "output_tokens_per_vendor_credit": a["output_tokens_per_vendor_credit"],
        "rates_last_refreshed": a.get("rates_last_refreshed"),
        "rates_source": a.get("rates_source"),
        **rates,
        "notes": [
            TOKEN_FORMULA,
            f"Report credits: 1 credit = {int(a['tokens_per_report_credit']):,} tokens.",
            f"Vendor billing: $1.00 = {a['vendor_credits_per_dollar']:.0f} vendor credits; "
            f"1 vendor credit = {int(a['input_tokens_per_vendor_credit']):,} input tokens "
            f"or {int(a['output_tokens_per_vendor_credit']):,} output tokens (output costs 5x input).",
            f"Derived rates: ${rates['input_dollars_per_million']:.2f} per 1M input tokens, "
            f"${rates['output_dollars_per_million']:.2f} per 1M output tokens.",
            f"Waste is assumed to be {int((1 - out_share) * 100)}% input tokens and "
            f"{int(out_share * 100)}% output tokens.",
            f"Each agent asset is assumed to be loaded {int(runs)} times per month.",
            f"Aggregate savings show a +/-{int(variance * 100)}% range.",
            "Similarity uses normalised text so whitespace-only and case-only changes are ignored.",
            f"Files under {MIN_CHARS_FOR_SIMILARITY} characters are excluded from duplicate detection.",
        ],
    }

    return {
        "insufficient_data": insufficient,
        "overall_score": 0 if insufficient else overall,
        "verdict": None if insufficient else verdict,
        "partial_scan": partial_scan,
        "skip_ratio": round(skip_ratio, 4),
        "category_scores": category_scores,
        "issues": issues,
        "top_drivers": top_drivers,
        "recommended_actions": actions,
        "penalty_ledger": penalty_ledger,
        "assumptions": assumptions_block,
        "savings": savings,
        "detections": {
            "duplicate_clusters_found": len(clusters),
            "duplicate_pairs_penalised": dup_pairs,
            "repeated_block_groups": len(blocks),
            "oversized_context_files": len(oversized_context),
            "overlapping_agent_groups": len(overlap_groups),
            "review_stages_inferred": review["count"],
            "review_stage_names": review["stages"],
            "agent_like_files": len(agent_like),
            "agent_role_files": len(agent_role),
            "skill_files": len(skill_files),
            "context_memory_files": len(context_files),
            "orchestration_files": len(orchestration_files),
            "service_dir_count": arch["service_dir_count"],
            "service_dirs": arch["service_dirs"][:40],
            "non_generated_source_files": arch["non_generated_source_files"],
            "microservice_mismatch": micro_mismatch,
            "monolith_mismatch": monolith_mismatch,
        },
        "clusters": [
            {k: v for k, v in c.items() if k != "file_records"} for c in clusters[:60]
        ],
        "overlap_groups": overlap_groups[:40],
    }
