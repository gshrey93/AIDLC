"""The adversary scan: deterministic heuristics, scoring, issues and savings."""
from __future__ import annotations

import os
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import NamedTuple
from datetime import datetime, timezone

from .classifier import Inventory, estimate_tokens, is_generated, normalise
from .config import (
    AGENT_SPRAWL_THRESHOLD, CATEGORY_AGENT, CATEGORY_CONTEXT,
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
def _score_candidate_pairs(pairs, sketches: list, shingles: list) -> list:
    """Refine LSH candidate pairs into (a, b, exact_similarity) above the overlap threshold."""
    scored = []
    for left, right in pairs:
        if sketch_jaccard(sketches[left], sketches[right]) < 0.30:
            continue
        similarity = exact_jaccard(shingles[left], shingles[right])
        if similarity >= SIMILARITY_OVERLAP_THRESHOLD:
            scored.append((left, right, similarity))
    return scored


def _build_duplicate_clusters(groups: dict, candidates: list, pair_sim: dict) -> list:
    """Turn union-find groups of >=0.80 similar files into reportable cluster records."""
    clusters = []
    for index, (_, members) in enumerate(sorted(groups.items()), start=1):
        member_files = [candidates[m] for m in members]
        sims = [v for (left, right), v in pair_sim.items() if left in members and right in members]
        group_id = f"DUP-{index:03d}"
        for member in member_files:
            member.similarity_group = group_id
        clusters.append({
            "group_id": group_id,
            "files": [f.path for f in member_files],
            "file_records": member_files,
            "max_similarity": round(max(sims) if sims else SIMILARITY_DUPLICATE_THRESHOLD, 4),
            "avg_similarity": round(sum(sims) / len(sims), 4) if sims else SIMILARITY_DUPLICATE_THRESHOLD,
            "agent_like_members": [f.path for f in member_files if f.agent_like],
            "tokens": [f.estimated_tokens for f in member_files],
        })
    return clusters


def _build_overlap_groups(groups: dict, candidates: list) -> list:
    """Groups of >=0.50 similar agent assets, used as the overlapping-responsibility signal."""
    overlap_groups = []
    for index, (_, members) in enumerate(sorted(groups.items()), start=1):
        agentish = [candidates[m] for m in members if candidates[m].agent_like]
        if len(agentish) >= 2:
            overlap_groups.append({
                "group_id": f"OVL-{index:03d}",
                "files": [f.path for f in agentish],
                "roles": len(agentish),
            })
    return overlap_groups


def detect_near_duplicates(files: list):
    """Return (clusters, overlap_groups) where clusters use >=0.80 similarity."""
    candidates = [
        f for f in files
        if f.parse_status == "Scanned" and f.norm and len(f.norm) >= MIN_CHARS_FOR_SIMILARITY
    ]
    if len(candidates) < 2:
        return [], []

    shingles = [shingle_set(f.norm) for f in candidates]
    sketches = [bottom_k_sketch(sig) for sig in shingles]
    scored = _score_candidate_pairs(candidate_pairs(sketches), sketches, shingles)

    dup_uf = UnionFind(len(candidates))
    ovl_uf = UnionFind(len(candidates))
    pair_sim = {}
    for a, b, sim in scored:
        ovl_uf.union(a, b)
        if sim >= SIMILARITY_DUPLICATE_THRESHOLD:
            dup_uf.union(a, b)
            pair_sim[(a, b)] = sim

    clusters = _build_duplicate_clusters(dup_uf.groups(), candidates, pair_sim)
    overlap_groups = _build_overlap_groups(ovl_uf.groups(), candidates)
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


# --------------------------------------------------- tier 2 severity scaling
# Tier 1 (the seven specified rules) is hard capped, which alone makes any overall score below
# about 72 impossible and would leave the Wasteful and Critical verdicts unreachable. Tier 2
# scales with HOW MUCH waste there is: for each category we take the share of the monthly agent
# context budget that the category wastes and deduct proportionally, up to that category's tier 2
# cap. A category wasting FULL_SCALE_SHARE or more of the budget takes the full deduction.
SCALE_CAPS = {
    "redundancy": 60, "token_bloat": 60, "review_overhead": 55,
    "agent_sprawl": 60, "architecture_inefficiency": 50,
}
FULL_SCALE_SHARE = 0.50


class Tier2Scaling(NamedTuple):
    monthly_agent_budget: float
    waste_by_category: dict
    waste_shares: dict
    penalties: dict


def compute_tier2_scaling(issue_records: list, agent_asset_tokens: int, runs_per_month: float,
                          insufficient: bool) -> Tier2Scaling:
    """Return the tier 2 deduction per category, plus the shares used to derive it."""
    budget = max(1.0, agent_asset_tokens * runs_per_month)
    by_category: dict = {key: 0 for key in CATEGORY_WEIGHTS}
    for record in issue_records:
        key = record["category"]
        by_category[key] = by_category.get(key, 0) + record["estimated_token_waste"]
    shares = {key: (by_category.get(key, 0) / budget) for key in CATEGORY_WEIGHTS}
    deductions = {
        key: (0 if insufficient
              else int(round(SCALE_CAPS[key] * min(1.0, shares[key] / FULL_SCALE_SHARE))))
        for key in CATEGORY_WEIGHTS
    }
    return Tier2Scaling(budget, by_category, shares, deductions)


# ---------------------------------------------------------------- scoring
def _capped(count: int, key: str) -> int:
    cfg = PENALTIES[key]
    return min(cfg["cap"], cfg["points"] * max(0, count))


@dataclass
class _Groups:
    """The file sets every later stage works from."""

    parsed: list
    agent_like: list
    agent_role: list
    context_files: list
    orchestration_files: list
    skill_files: list
    oversized_context: list


def _group_files(files: list) -> _Groups:
    context_files = [f for f in files if f.category == CATEGORY_CONTEXT]
    return _Groups(
        parsed=[f for f in files if f.parse_status == "Scanned"],
        agent_like=[f for f in files if f.agent_like],
        agent_role=[f for f in files if f.category == CATEGORY_AGENT],
        context_files=context_files,
        orchestration_files=[f for f in files if f.category == CATEGORY_ORCHESTRATION],
        skill_files=[f for f in files if f.category == CATEGORY_SKILL],
        oversized_context=[f for f in context_files if f.estimated_tokens > OVERSIZED_CONTEXT_TOKENS],
    )


@dataclass
class _Detections:
    """Raw output of the four detectors."""

    clusters: list
    overlap_groups: list
    blocks: list
    review: dict
    arch: dict


def _detect_all(files: list) -> _Detections:
    clusters, overlap_groups = detect_near_duplicates(files)
    return _Detections(
        clusters=clusters,
        overlap_groups=overlap_groups,
        blocks=detect_repeated_blocks(files),
        review=detect_review_stages(files),
        arch=detect_architecture(files),
    )


@dataclass
class _Tier1:
    """The seven specified penalty rules, each hard-capped by the specification."""

    dup_pairs: int
    near_dup: int
    blocks: int
    oversized: int
    sprawl_extra: int
    sprawl: int
    extra_stages: int
    review: int
    micro_mismatch: bool
    monolith_mismatch: bool
    micro: int
    mono: int


def _count_duplicate_pairs(clusters: list) -> int:
    pairs = 0
    for c in clusters:
        agentish = len(c["agent_like_members"])
        if agentish >= 2:
            pairs += agentish - 1
    return pairs


def _tier1_penalties(g: _Groups, d: _Detections) -> _Tier1:
    dup_pairs = _count_duplicate_pairs(d.clusters)
    sprawl_extra = max(0, len(g.agent_like) - AGENT_SPRAWL_THRESHOLD)
    extra_stages = max(0, d.review["count"] - REVIEW_STAGE_THRESHOLD)
    micro_mismatch = (
        d.arch["service_dir_count"] >= MICROSERVICE_DIR_THRESHOLD
        and d.arch["non_generated_source_files"] < MICROSERVICE_SOURCE_FLOOR
    )
    monolith_mismatch = (
        d.arch["service_dir_count"] <= 1
        and len(g.agent_role) >= MONOLITH_AGENT_ROLE_THRESHOLD
        and len(d.overlap_groups) >= 1
    )
    return _Tier1(
        dup_pairs=dup_pairs,
        near_dup=_capped(dup_pairs, "near_duplicate"),
        blocks=_capped(len(d.blocks), "repeated_block"),
        oversized=_capped(len(g.oversized_context), "oversized_context"),
        sprawl_extra=sprawl_extra,
        sprawl=_capped(sprawl_extra, "agent_sprawl"),
        extra_stages=extra_stages,
        review=_capped(extra_stages, "review_stages"),
        micro_mismatch=micro_mismatch,
        monolith_mismatch=monolith_mismatch,
        micro=PENALTIES["microservice_mismatch"]["points"] if micro_mismatch else 0,
        mono=PENALTIES["monolith_mismatch"]["points"] if monolith_mismatch else 0,
    )


class _Money:
    """Converts token counts into report credits and dollars using the scan assumptions."""

    def __init__(self, a: dict):
        self.tokens_per_credit = float(a["tokens_per_report_credit"])
        self.out_share = float(a["output_token_share"])
        self.input_per_million = a["input_dollars_per_million"]
        self.output_per_million = a["output_dollars_per_million"]

    def credits(self, tokens: float) -> float:
        return round(tokens / self.tokens_per_credit, 4)

    def dollars(self, tokens: float) -> float:
        inp = tokens * (1 - self.out_share)
        outp = tokens * self.out_share
        return round(
            inp / 1_000_000 * self.input_per_million + outp / 1_000_000 * self.output_per_million,
            2,
        )


def _severity_for(tokens: float) -> str:
    if tokens >= 4_000_000:
        return "critical"
    if tokens >= 1_000_000:
        return "high"
    if tokens >= 200_000:
        return "medium"
    return "low"


class _IssueLog:
    """Collects findings and assigns their sequential, date-stamped ids."""

    def __init__(self, date_key: str, money: _Money):
        self.items: list = []
        self._date_key = date_key
        self._money = money
        self._seq = 0

    def add(self, severity, category, title, description, evidence, impacted, monthly_tokens,
            recommendation, impact, effort, formula, files_list=None) -> None:
        self._seq += 1
        monthly_tokens = max(0.0, float(monthly_tokens))
        self.items.append({
            "id": f"ISS-{self._date_key}-{self._seq:04d}",
            "severity": severity,
            "category": category,
            "title": title,
            "description": description,
            "evidence": evidence,
            "impacted_file_count": impacted,
            "impacted_files": files_list or [],
            "estimated_token_waste": int(round(monthly_tokens)),
            "estimated_credit_waste": self._money.credits(monthly_tokens),
            "estimated_dollar_waste": self._money.dollars(monthly_tokens),
            "recommendation": recommendation,
            "impact": impact,
            "effort": effort,
            "formula": formula,
        })


@dataclass
class _Metrics:
    """Derived token totals shared by the findings, the scoring tiers and the ledger."""

    runs: float
    agent_token_total: int
    redundant_tokens_total: int
    context_excess_tokens: int
    median_agent_tokens_pre: int
    dup_share: float
    median_agent_tokens: int
    total_instruction_tokens: int
    total_agent_like_tokens: int


def _compute_metrics(g: _Groups, d: _Detections, runs: float) -> _Metrics:
    agent_token_total = max(1, sum(f.estimated_tokens for f in g.agent_like))
    redundant_tokens_total = 0
    for c in d.clusters:
        if c["agent_like_members"]:
            toks = sorted(c["tokens"], reverse=True)
            redundant_tokens_total += sum(toks[1:])
    agent_tokens = [f.estimated_tokens for f in g.agent_like if f.estimated_tokens]
    median_agent_tokens = int(statistics.median(agent_tokens)) if agent_tokens else 0
    instruction_tokens = [
        f.estimated_tokens for f in (g.orchestration_files + g.agent_role) if f.estimated_tokens
    ]
    return _Metrics(
        runs=runs,
        agent_token_total=agent_token_total,
        redundant_tokens_total=redundant_tokens_total,
        context_excess_tokens=sum(
            max(0, f.estimated_tokens - OVERSIZED_CONTEXT_TOKENS) for f in g.context_files),
        median_agent_tokens_pre=median_agent_tokens,
        dup_share=redundant_tokens_total / agent_token_total,
        median_agent_tokens=median_agent_tokens,
        total_instruction_tokens=sum(instruction_tokens),
        total_agent_like_tokens=sum(agent_tokens),
    )


@dataclass
class _Findings:
    """Bundle passed to each finding builder."""

    g: _Groups
    d: _Detections
    t1: _Tier1
    m: _Metrics


# ------------------------------------------------------------ finding builders
def _find_duplicate_clusters(f: _Findings, add) -> None:
    for c in sorted(f.d.clusters, key=lambda x: -sum(x["tokens"]))[:80]:
        tokens_sorted = sorted(c["tokens"], reverse=True)
        redundant_tokens = sum(tokens_sorted[1:])
        monthly = (redundant_tokens * f.m.runs if c["agent_like_members"]
                   else redundant_tokens * f.m.runs * 0.25)
        add(
            _severity_for(monthly), "redundancy",
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


def _find_repeated_blocks(f: _Findings, add) -> None:
    for b in f.d.blocks[:60]:
        monthly = b["block_tokens"] * (b["file_count"] - 1) * f.m.runs
        add(
            _severity_for(monthly), "redundancy",
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


def _find_oversized_context(f: _Findings, add) -> None:
    for rec in sorted(f.g.oversized_context, key=lambda x: -x.estimated_tokens)[:40]:
        excess = rec.estimated_tokens - OVERSIZED_CONTEXT_TOKENS
        monthly = excess * f.m.runs
        add(
            _severity_for(monthly), "token_bloat",
            f"Context file is very large: {os.path.basename(rec.path)}",
            "This memory or context file is bigger than a healthy working budget. Large context files "
            "are re-read on every run, so most of the cost is paid again and again.",
            f"{rec.path} is about {rec.estimated_tokens:,} tokens which is {excess:,} tokens over the "
            f"{OVERSIZED_CONTEXT_TOKENS:,} token guideline.",
            1, monthly,
            "Split this file into a short always-on summary plus detail files that load only when needed.",
            "High" if excess > 20000 else "Medium",
            "Medium",
            f"monthly_waste = (file_tokens - {OVERSIZED_CONTEXT_TOKENS}) x runs_per_month",
            [rec.path],
        )


def _find_agent_sprawl(f: _Findings, add) -> None:
    if f.t1.sprawl_extra <= 0:
        return
    monthly = f.t1.sprawl_extra * f.m.median_agent_tokens * f.m.runs
    add(
        _severity_for(monthly), "agent_sprawl",
        f"{len(f.g.agent_like)} agent-style files is more than this repo needs",
        "There are many separate agent, skill and prompt files. Each one adds instructions that "
        "have to be loaded and kept in sync. Fewer, clearer files cost less and break less often.",
        f"{len(f.g.agent_like)} agent-like files detected against a healthy guideline of "
        f"{AGENT_SPRAWL_THRESHOLD}. Median agent file size is {f.m.median_agent_tokens:,} tokens.",
        len(f.g.agent_like), monthly,
        "Group agents by job. Merge the ones that overlap and delete the ones nobody calls.",
        "High" if f.t1.sprawl_extra > 10 else "Medium", "Large",
        "monthly_waste = extra_agent_files x median_agent_tokens x runs_per_month",
        [rec.path for rec in f.g.agent_like[:25]],
    )


def _find_review_overhead(f: _Findings, add) -> None:
    if f.t1.extra_stages <= 0:
        return
    review = f.d.review
    monthly = f.t1.extra_stages * f.m.total_instruction_tokens * f.m.runs * 0.25
    add(
        _severity_for(monthly), "review_overhead",
        f"{review['count']} separate review or approval steps were found",
        "Your instructions describe many checks before work is accepted. Each extra check means "
        "another pass over the same material, which costs time and money.",
        "Stages inferred: " + ", ".join(review["stages"]) + ". Examples: "
        + "; ".join(f"{s} -> {_short(v[0])}" for s, v in list(review["evidence"].items())[:4] if v),
        len({p for v in review["evidence"].values() for p in v}), monthly,
        "Keep at most four review gates. Combine the overlapping ones into a single checklist.",
        "Medium" if f.t1.extra_stages <= 2 else "High", "Medium",
        "monthly_waste = extra_review_stages x total_instruction_tokens x runs_per_month x 0.25",
        sorted({p for v in review["evidence"].values() for p in v})[:20],
    )


def _find_architecture(f: _Findings, add) -> None:
    arch = f.d.arch
    if f.t1.micro_mismatch:
        monthly = 0.05 * f.m.total_agent_like_tokens * f.m.runs
        add(
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
    if f.t1.monolith_mismatch:
        monthly = 0.05 * sum(rec.estimated_tokens for rec in f.g.agent_role) * f.m.runs
        add(
            "medium", "architecture_inefficiency",
            "One service is carrying many overlapping agent roles",
            "Everything lives in a single service, but there are many agent role files that describe "
            "similar work. That makes it hard to tell which agent owns what, and the same guidance "
            "gets repeated.",
            f"{len(f.g.agent_role)} agent role files with {len(f.d.overlap_groups)} overlapping groups inside "
            f"{arch['service_dir_count']} service directory.",
            len(f.g.agent_role), monthly,
            "Give each agent one clear job and remove duplicated role descriptions.",
            "Medium", "Medium",
            "monthly_waste = 5% x total_agent_role_tokens x runs_per_month",
            [rec.path for rec in f.g.agent_role[:20]],
        )


def _find_repetitive_skills(f: _Findings, add) -> None:
    skill_files = f.g.skill_files
    dup_skill_paths = {
        p for c in f.d.clusters for p in c["files"]
        if "/skills/" in "/" + p.lower() or p.lower().endswith(".skill.md")
    }
    if not (len(skill_files) > 10 or len(dup_skill_paths) >= 2):
        return
    dup_tokens = sum(rec.estimated_tokens for rec in skill_files if rec.path in dup_skill_paths)
    monthly = (dup_tokens or max(0, len(skill_files) - 10) * f.m.median_agent_tokens) * f.m.runs * 0.5
    add(
        _severity_for(monthly), "agent_sprawl",
        f"{len(skill_files)} skill files, and some repeat each other",
        "Skill files are meant to be small and specific. When there are many of them and they "
        "repeat, the model reads the same guidance several times.",
        f"{len(skill_files)} skill files detected; {len(dup_skill_paths)} of them sit inside "
        f"near-duplicate groups.",
        max(len(skill_files), len(dup_skill_paths)), monthly,
        "Keep one skill file per capability and delete the near copies.",
        "Medium", "Small",
        "monthly_waste = duplicated_skill_tokens x runs_per_month x 0.5",
        sorted(dup_skill_paths)[:20] or [rec.path for rec in skill_files[:20]],
    )


def _find_orchestration_layers(f: _Findings, add) -> None:
    orchestration_files = f.g.orchestration_files
    if len(orchestration_files) <= 6:
        return
    layers = len(orchestration_files)
    avg_orch = int(statistics.mean(
        [rec.estimated_tokens for rec in orchestration_files if rec.estimated_tokens] or [0]))
    monthly = (layers - 6) * avg_orch * f.m.runs * 0.5
    add(
        _severity_for(monthly), "review_overhead",
        f"{layers} orchestration files create extra hand-offs",
        "There are many files describing how work moves between agents. Every hand-off adds "
        "instructions that must be loaded and kept in step with the others.",
        f"{layers} orchestration or prompt files detected, average size {avg_orch:,} tokens.",
        layers, monthly,
        "Describe the flow once in a single orchestrator file and let the agents stay simple.",
        "Medium", "Medium",
        "monthly_waste = (orchestration_files - 6) x avg_orchestration_tokens x runs_per_month x 0.5",
        [rec.path for rec in orchestration_files[:20]],
    )


# Order matters: issue ids are assigned sequentially as these run.
FINDING_BUILDERS = (
    _find_duplicate_clusters,
    _find_repeated_blocks,
    _find_oversized_context,
    _find_agent_sprawl,
    _find_review_overhead,
    _find_architecture,
    _find_repetitive_skills,
    _find_orchestration_layers,
)


def _collect_issues(findings: _Findings, log: _IssueLog, insufficient: bool) -> list:
    if not insufficient:
        for builder in FINDING_BUILDERS:
            builder(findings, log.add)
    log.items.sort(key=lambda i: -i["estimated_token_waste"])
    return log.items


# ------------------------------------------------------------ result assembly
def _category_penalties(t1: _Tier1, scale: dict) -> dict:
    return {
        "redundancy": t1.near_dup + t1.blocks + scale["redundancy"],
        "token_bloat": t1.oversized + scale["token_bloat"],
        "review_overhead": t1.review + scale["review_overhead"],
        "agent_sprawl": t1.sprawl + scale["agent_sprawl"],
        "architecture_inefficiency": t1.micro + t1.mono + scale["architecture_inefficiency"],
    }


def _build_savings(issues: list, money: _Money, variance: float, insufficient: bool) -> dict:
    total_tokens_waste = sum(i["estimated_token_waste"] for i in issues)
    total_dollars = round(sum(i["estimated_dollar_waste"] for i in issues), 2)
    credits = money.credits(total_tokens_waste)
    savings = {
        "estimated_monthly_token_waste": int(total_tokens_waste),
        "estimated_monthly_credit_waste": credits,
        "estimated_monthly_dollar_waste": total_dollars,
        "estimated_savings_low": round(total_dollars * (1 - variance), 2),
        "estimated_savings_high": round(total_dollars * (1 + variance), 2),
        "estimated_credit_savings_low": round(credits * (1 - variance), 2),
        "estimated_credit_savings_high": round(credits * (1 + variance), 2),
    }
    if insufficient:
        return {k: 0 for k in savings}
    return savings


def _build_category_scores(g: _Groups, d: _Detections, cat_scores: dict, cat_penalties: dict) -> list:
    summaries = {
        "redundancy": (
            f"{len(d.clusters)} groups of near-identical files and {len(d.blocks)} repeated instruction "
            f"blocks were found."
        ),
        "token_bloat": (
            f"{len(g.oversized_context)} context or memory files are over "
            f"{OVERSIZED_CONTEXT_TOKENS:,} tokens."
        ),
        "review_overhead": f"{d.review['count']} review or approval steps were inferred from your instructions.",
        "agent_sprawl": f"{len(g.agent_like)} agent-style files were found ({len(g.agent_role)} agent roles, {len(g.skill_files)} skills).",
        "architecture_inefficiency": (
            f"{d.arch['service_dir_count']} service directories against "
            f"{d.arch['non_generated_source_files']} hand written source files."
        ),
    }
    return [{
        "category": key,
        "label": CATEGORY_LABELS[key],
        "score": cat_scores[key],
        "penalty_points": cat_penalties[key],
        "weight": CATEGORY_WEIGHTS[key],
        "summary": summaries[key],
    } for key in CATEGORY_WEIGHTS]


def _build_top_drivers(issues: list) -> list:
    return [{
        "rank": i + 1,
        "title": iss["title"],
        "plain_language": iss["description"],
        "category": CATEGORY_LABELS.get(iss["category"], iss["category"]),
        "estimated_token_waste": iss["estimated_token_waste"],
        "estimated_credit_waste": iss["estimated_credit_waste"],
        "estimated_dollar_waste": iss["estimated_dollar_waste"],
        "issue_id": iss["id"],
    } for i, iss in enumerate(issues[:5])]


def _build_actions(issues: list) -> list:
    impact_rank = {"High": 0, "Medium": 1, "Low": 2}
    effort_rank = {"Small": 0, "Medium": 1, "Large": 2}
    seen: set = set()
    actions: list = []
    ordered = sorted(issues, key=lambda x: (
        impact_rank.get(x["impact"], 3), effort_rank.get(x["effort"], 3), -x["estimated_token_waste"]))
    for iss in ordered:
        key = (iss["category"], iss["recommendation"])
        if key in seen:
            continue
        seen.add(key)
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
    return actions


def _tier1_ledger(g: _Groups, d: _Detections, t1: _Tier1) -> list:
    return [
        {"rule": "Near-duplicate agent/context file pair (similarity >= 0.80)", "hits": t1.dup_pairs,
         "points_each": 5, "cap": 32, "applied": t1.near_dup, "category": "redundancy"},
        {"rule": f"Repeated instruction block >= {REPEATED_BLOCK_MIN_CHARS} chars in {REPEATED_BLOCK_MIN_FILES}+ files",
         "hits": len(d.blocks), "points_each": 4, "cap": 20, "applied": t1.blocks, "category": "redundancy"},
        {"rule": f"Context or memory file over {OVERSIZED_CONTEXT_TOKENS:,} tokens",
         "hits": len(g.oversized_context),
         "points_each": 6, "cap": 24, "applied": t1.oversized, "category": "token_bloat"},
        {"rule": f"Agent-like files above {AGENT_SPRAWL_THRESHOLD}", "hits": t1.sprawl_extra,
         "points_each": 2, "cap": 20, "applied": t1.sprawl, "category": "agent_sprawl"},
        {"rule": f"Review/approval stages above {REVIEW_STAGE_THRESHOLD}", "hits": t1.extra_stages,
         "points_each": 5, "cap": 15, "applied": t1.review, "category": "review_overhead"},
        {"rule": f"Microservice mismatch (>= {MICROSERVICE_DIR_THRESHOLD} service dirs and < {MICROSERVICE_SOURCE_FLOOR} source files)",
         "hits": 1 if t1.micro_mismatch else 0, "points_each": 12, "cap": 12, "applied": t1.micro,
         "category": "architecture_inefficiency"},
        {"rule": f"Monolith mismatch (1 service and >= {MONOLITH_AGENT_ROLE_THRESHOLD} overlapping agent roles)",
         "hits": 1 if t1.monolith_mismatch else 0, "points_each": 10, "cap": 10, "applied": t1.mono,
         "category": "architecture_inefficiency"},
    ]


def _tier2_ledger(g: _Groups, d: _Detections, m: _Metrics, tier2) -> list:
    shares = tier2.waste_shares
    applied = tier2.penalties
    by_cat = tier2.waste_by_category
    budget = tier2.monthly_agent_budget
    return [
        {"rule": "Severity scaling - share of the monthly agent context budget wasted by duplication",
         "hits": int(round(shares["redundancy"] * 100)), "points_each": 0,
         "cap": SCALE_CAPS["redundancy"], "applied": applied["redundancy"],
         "category": "redundancy", "tier": "scaling",
         "detail": f"{by_cat.get('redundancy', 0):,} of {int(budget):,} monthly "
                   f"agent context tokens ({shares['redundancy'] * 100:.1f}%); "
                   f"{m.dup_share * 100:.1f}% of agent files are duplicated copies"},
        {"rule": "Severity scaling - share of the monthly agent context budget wasted by oversized files",
         "hits": int(round(shares["token_bloat"] * 100)), "points_each": 0,
         "cap": SCALE_CAPS["token_bloat"], "applied": applied["token_bloat"],
         "category": "token_bloat", "tier": "scaling",
         "detail": f"{m.context_excess_tokens:,} tokens over the context guideline; median agent file "
                   f"{m.median_agent_tokens_pre:,} tokens; "
                   f"{shares['token_bloat'] * 100:.1f}% of the monthly budget"},
        {"rule": "Severity scaling - share of the monthly agent context budget wasted on review loops",
         "hits": int(round(shares["review_overhead"] * 100)), "points_each": 0,
         "cap": SCALE_CAPS["review_overhead"], "applied": applied["review_overhead"],
         "category": "review_overhead", "tier": "scaling",
         "detail": f"{d.review['count']} review stages, {len(g.orchestration_files)} orchestration files, "
                   f"{shares['review_overhead'] * 100:.1f}% of the monthly budget"},
        {"rule": "Severity scaling - share of the monthly agent context budget wasted on extra agents",
         "hits": int(round(shares["agent_sprawl"] * 100)), "points_each": 0,
         "cap": SCALE_CAPS["agent_sprawl"], "applied": applied["agent_sprawl"],
         "category": "agent_sprawl", "tier": "scaling",
         "detail": f"{len(g.agent_like)} agent-like files, "
                   f"{shares['agent_sprawl'] * 100:.1f}% of the monthly budget"},
        {"rule": "Severity scaling - share of the monthly agent context budget lost to the architecture",
         "hits": int(round(shares["architecture_inefficiency"] * 100)), "points_each": 0,
         "cap": SCALE_CAPS["architecture_inefficiency"],
         "applied": applied["architecture_inefficiency"],
         "category": "architecture_inefficiency", "tier": "scaling",
         "detail": f"{d.arch['service_dir_count']} service dirs, {len(d.overlap_groups)} overlapping groups, "
                   f"{shares['architecture_inefficiency'] * 100:.1f}% of the monthly budget"},
    ]


def _build_penalty_ledger(g: _Groups, d: _Detections, t1: _Tier1, m: _Metrics, tier2) -> list:
    ledger = _tier1_ledger(g, d, t1) + _tier2_ledger(g, d, m, tier2)
    for row in ledger:
        row.setdefault("tier", "specified")
        row.setdefault("detail", "")
    return ledger


def _assumption_notes(a: dict, m: _Metrics, variance: float, out_share: float,
                      monthly_agent_budget: float) -> list:
    return [
        TOKEN_FORMULA,
        f"Report credits: 1 credit = {int(a['tokens_per_report_credit']):,} tokens.",
        f"Vendor billing: $1.00 = {a['vendor_credits_per_dollar']:.0f} vendor credits; "
        f"1 vendor credit = {int(a['input_tokens_per_vendor_credit']):,} input tokens "
        f"or {int(a['output_tokens_per_vendor_credit']):,} output tokens (output costs 5x input).",
        f"Derived rates: ${a['input_dollars_per_million']:.2f} per 1M input tokens, "
        f"${a['output_dollars_per_million']:.2f} per 1M output tokens.",
        f"Waste is assumed to be {int((1 - out_share) * 100)}% input tokens and "
        f"{int(out_share * 100)}% output tokens.",
        f"Each agent asset is assumed to be loaded {int(m.runs)} times per month.",
        f"Aggregate savings show a +/-{int(variance * 100)}% range.",
        "Similarity uses normalised text so whitespace-only and case-only changes are ignored.",
        f"Files under {MIN_CHARS_FOR_SIMILARITY} characters are excluded from duplicate detection.",
        "Scoring runs in two tiers. Tier 1 is the seven specified penalty rules with their hard "
        "caps. Tier 2 is severity scaling: for each category we measure the share of the monthly "
        "agent context budget that the category wastes, and deduct proportionally up to that "
        "category's tier 2 cap, with a category that wastes 50% or more of the budget taking the "
        "full deduction. Without tier 2 the capped rules alone could never produce a score below "
        "about 72, so the Wasteful and Critical bands would be unreachable. Both tiers are "
        "itemised in the score ledger.",
        f"Monthly agent context budget for this repository = {int(monthly_agent_budget):,} tokens "
        f"({m.agent_token_total:,} agent asset tokens x {int(m.runs)} runs per month).",
    ]


def _build_assumptions_block(a: dict, m: _Metrics, variance: float, out_share: float,
                             monthly_agent_budget: float) -> dict:
    return {
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
        "input_dollars_per_million": a["input_dollars_per_million"],
        "output_dollars_per_million": a["output_dollars_per_million"],
        "notes": _assumption_notes(a, m, variance, out_share, monthly_agent_budget),
    }


def _build_detections(g: _Groups, d: _Detections, t1: _Tier1) -> dict:
    return {
        "duplicate_clusters_found": len(d.clusters),
        "duplicate_pairs_penalised": t1.dup_pairs,
        "repeated_block_groups": len(d.blocks),
        "oversized_context_files": len(g.oversized_context),
        "overlapping_agent_groups": len(d.overlap_groups),
        "review_stages_inferred": d.review["count"],
        "review_stage_names": d.review["stages"],
        "agent_like_files": len(g.agent_like),
        "agent_role_files": len(g.agent_role),
        "skill_files": len(g.skill_files),
        "context_memory_files": len(g.context_files),
        "orchestration_files": len(g.orchestration_files),
        "service_dir_count": d.arch["service_dir_count"],
        "service_dirs": d.arch["service_dirs"][:40],
        "non_generated_source_files": d.arch["non_generated_source_files"],
        "microservice_mismatch": t1.micro_mismatch,
        "monolith_mismatch": t1.monolith_mismatch,
    }


def analyze(inventory: Inventory, assumptions_overrides: dict | None = None,
            scan_date: datetime | None = None) -> dict:
    """Score a repository inventory.

    Runs as a short pipeline: group the files, run the detectors, apply the two penalty tiers,
    build the findings, then assemble the report payload.
    """
    a = merged_assumptions(assumptions_overrides)
    scan_date = scan_date or datetime.now(timezone.utc)
    files = inventory.files

    groups = _group_files(files)
    detections = _detect_all(files)
    tier1 = _tier1_penalties(groups, detections)
    money = _Money(a)
    runs = float(a["agent_runs_per_month"])
    metrics = _compute_metrics(groups, detections, runs)

    insufficient = len(groups.parsed) < MIN_TEXT_FILES_FOR_VALID_SCAN
    skip_ratio = inventory.skipped_files / (len(files) or 1)
    partial_scan = skip_ratio > PARTIAL_SCAN_SKIP_RATIO

    log = _IssueLog(scan_date.strftime("%Y-%m-%d"), money)
    issues = _collect_issues(_Findings(groups, detections, tier1, metrics), log, insufficient)

    tier2 = compute_tier2_scaling(issues, metrics.agent_token_total, runs, insufficient)
    cat_penalties = _category_penalties(tier1, tier2.penalties)
    cat_scores = {k: max(0, min(100, 100 - v)) for k, v in cat_penalties.items()}
    overall = int(round(sum(cat_scores[k] * w for k, w in CATEGORY_WEIGHTS.items())))
    overall = max(0, min(100, overall))
    variance = float(a["variance_pct"])

    return {
        "insufficient_data": insufficient,
        "overall_score": 0 if insufficient else overall,
        "verdict": None if insufficient else verdict_for_score(overall),
        "partial_scan": partial_scan,
        "skip_ratio": round(skip_ratio, 4),
        "category_scores": _build_category_scores(groups, detections, cat_scores, cat_penalties),
        "issues": issues,
        "top_drivers": _build_top_drivers(issues),
        "recommended_actions": _build_actions(issues),
        "penalty_ledger": _build_penalty_ledger(groups, detections, tier1, metrics, tier2),
        "assumptions": _build_assumptions_block(
            a, metrics, variance, float(a["output_token_share"]), tier2.monthly_agent_budget),
        "savings": _build_savings(issues, money, variance, insufficient),
        "detections": _build_detections(groups, detections, tier1),
        "clusters": [
            {k: v for k, v in cluster.items() if k != "file_records"}
            for cluster in detections.clusters[:60]
        ],
        "overlap_groups": detections.overlap_groups[:40],
    }
