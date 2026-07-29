"""Seeded demo history.

The seed does NOT fabricate scores. It generates realistic synthetic agentic repositories,
then runs the exact same inventory + analyzer pipeline that a real scan uses, tuning a single
"badness" dial by bisection until the resulting verdict lands in the requested band. Every
number in the seeded history therefore comes from the real scoring engine.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import timedelta

from core.analyzer import analyze
from core.classifier import inventory_from_entries
from core.drafts import MAX_DRAFTS, select_draft_targets
from db import (
    DEMO_USER_ID, category_scores, drafts as drafts_col, file_assets, issues as issues_col,
    scans, utcnow,
)
from scanner import STAGES
from settings_store import get_settings

log = logging.getLogger("bloatguardian.seed")

SEED_WORKSPACE = os.environ.get("BG_SEED_WORKSPACE", "/tmp/bloatguardian/seed")

BAND_TARGETS = {
    "Lean": (83, 94),
    "Watchlist": (65, 77),
    "Wasteful": (45, 57),
    "Critical": (20, 38),
}

REVIEW_PHRASES = [
    "self review", "peer review", "code review", "security review", "architecture review",
    "product owner approval", "manager approval", "final sign-off", "validation gate",
    "human in the loop",
]

SHARED_BLOCK = (
    "Before starting any task, read the repository conventions file, confirm the ticket number, "
    "check that the branch name follows the release naming policy, and make sure a change log entry "
    "has been drafted. Never commit straight to the main branch. Always run the unit tests and the "
    "lint task before handing work to the next agent in the chain."
)

FILLER_PARA = (
    "The account has an established relationship with the platform and has raised tickets about "
    "billing, onboarding and reporting across the last four quarters. Each ticket was handled by a "
    "different agent and the notes were copied into this file rather than summarised. "
)

# 20 seeded scans across the last 90 days: 12 GitHub, 4 zip uploads, 4 markdown uploads.
SEED_SPECS = [
    {"repo": "agentic-crm", "owner": "northwind-labs", "source": "github", "band": "Critical",
     "days": 3, "branch": "main", "partial": True, "files": 780, "tokens": 1_240_000},
    {"repo": "support-copilot", "owner": "northwind-labs", "source": "github", "band": "Wasteful",
     "days": 7, "branch": "main", "files": 640, "tokens": 410_000},
    {"repo": "proposal-writer", "owner": "northwind-labs", "source": "github", "band": "Watchlist",
     "days": 11, "branch": "develop", "files": 320, "tokens": 180_000},
    {"repo": "multi-agent-ops", "owner": "orbital-works", "source": "github", "band": "Critical",
     "days": 15, "branch": "main", "files": 900, "tokens": 1_780_000},
    {"repo": "sow-estimator", "owner": "orbital-works", "source": "github", "band": "Wasteful",
     "days": 19, "branch": "main", "files": 410, "tokens": 260_000},
    {"repo": "customer-onboarding-bot", "owner": "orbital-works", "source": "github",
     "band": "Watchlist", "days": 24, "branch": "release/2.1", "files": 275, "tokens": 145_000},
    {"repo": "rfp-responder", "owner": "brightpath", "source": "github", "band": "Lean",
     "days": 29, "branch": "main", "files": 130, "tokens": 62_000},
    {"repo": "contract-analyzer", "owner": "brightpath", "source": "github", "band": "Wasteful",
     "days": 34, "branch": "main", "files": 520, "tokens": 330_000},
    {"repo": "ticket-triage-agents", "owner": "brightpath", "source": "github", "band": "Watchlist",
     "days": 39, "branch": "main", "files": 240, "tokens": 128_000},
    {"repo": "finance-close-copilot", "owner": "ledgerline", "source": "github", "band": "Critical",
     "days": 45, "branch": "main", "files": 700, "tokens": 890_000},
    {"repo": "field-service-planner", "owner": "ledgerline", "source": "github", "band": "Watchlist",
     "days": 52, "branch": "main", "files": 210, "tokens": 96_000},
    {"repo": "release-notes-agent", "owner": "ledgerline", "source": "github", "status": "ImportFailed",
     "error_code": "GitHubRepoUnavailable", "days": 58, "branch": "main",
     "error": "GitHub could not find a public repository at ledgerline/release-notes-agent."},
    {"repo": "agentic-crm-export", "source": "zip", "band": "Wasteful", "days": 62,
     "files": 380, "tokens": 240_000},
    {"repo": "legacy-orchestrator", "source": "zip", "band": "Watchlist", "days": 68,
     "files": 190, "tokens": 88_000},
    {"repo": "partner-portal-agents", "source": "zip", "band": "Lean", "days": 74,
     "files": 105, "tokens": 44_000},
    {"repo": "broken-archive", "source": "zip", "status": "ParseFailed", "error_code": "ParseFailed",
     "days": 79, "error": "The archive extracted but no readable file tree could be built."},
    {"repo": "instruction-pack", "source": "md", "band": "Wasteful", "days": 82,
     "files": 46, "tokens": 96_000, "md_only": True},
    {"repo": "context-pack", "source": "md", "band": "Watchlist", "days": 85,
     "files": 40, "tokens": 58_000, "md_only": True},
    {"repo": "prompt-library", "source": "md", "band": "Lean", "days": 88,
     "files": 44, "tokens": 30_000, "md_only": True},
    {"repo": "tiny-notes", "source": "md", "status": "InsufficientData", "days": 90,
     "error_code": "InsufficientData", "files": 3,
     "error": "Only 3 text files were parsed. A scan needs at least 5 parsed text files before we "
              "can score it or estimate savings."},
]

AGENT_JOBS = [
    ("intake", "lead intake and qualification"), ("triage", "ticket triage"),
    ("research", "account research"), ("proposal", "proposal drafting"),
    ("pricing", "deal pricing"), ("legal", "contract review"),
    ("onboarding", "customer onboarding"), ("support", "support replies"),
    ("billing", "invoice questions"), ("renewal", "renewal outreach"),
    ("reporting", "pipeline reporting"), ("forecast", "revenue forecasting"),
    ("quality", "quality checks"), ("escalation", "escalation handling"),
    ("notes", "call note summaries"), ("handoff", "stage hand-offs"),
    ("scheduling", "meeting scheduling"), ("enrichment", "data enrichment"),
    ("routing", "queue routing"), ("compliance", "policy checks"),
    ("migration", "data migration"), ("insights", "trend insights"),
    ("outreach", "cold outreach"), ("survey", "feedback surveys"),
    ("refunds", "refund handling"), ("upsell", "upsell suggestions"),
    ("churn", "churn signals"), ("tagging", "record tagging"),
    ("dedupe", "record de-duplication"), ("audit", "activity audit"),
]

SKILL_NAMES = [
    "search", "summarise", "classify", "extract", "validate", "translate", "format",
    "escalate", "schedule", "notify", "archive", "reconcile", "redact", "compare",
    "rank", "cluster", "annotate", "export", "diff",
]


def _agent_body(name: str, job: str, include_block: bool, stages: list, padding: int) -> str:
    parts = [
        f"# {name.title()} agent",
        "",
        "## Purpose",
        "",
        f"This agent owns {job} for the platform.",
        "",
        "## Operating rules",
        "",
    ]
    if include_block:
        parts += [SHARED_BLOCK, ""]
    else:
        parts += [f"Handle {job} and stop when the ticket is updated.", ""]
    if stages:
        parts += ["## Review workflow", "",
                  "Every change moves through these gates in order: " + ", ".join(stages) + ".", ""]
    parts += ["## Tools", "", "- repository search", "- test runner", "- ticket updater", "",
              "## Hand-off", "",
              "When finished, write a summary into the shared memory file and notify the "
              "orchestrator so the next stage can start.", ""]
    for i in range(padding):
        parts += [f"### Note {i + 1}", "",
                  f"Additional guidance for {job}: keep the response short, cite the record id, and "
                  f"never guess a value that is not present in the record.", ""]
    return "\n".join(parts)


def build_entries(spec: dict, badness: float, final: bool = False) -> list:
    """Generate the file entries for one synthetic repository."""
    # Fully deterministic: every knob below is derived from the badness dial and the spec,
    # so a given seed spec always produces byte-identical demo data. No RNG is involved.
    b = max(0.0, min(1.0, badness))
    md_only = bool(spec.get("md_only"))
    entries: list = []

    def add(path: str, content: str):
        entries.append({"path": path, "content": content})

    n_agents = 5 + int(b * 90)
    dup_copies = 0 if b < 0.18 else 1 + int(b * 18)
    n_skills = 1 + int(b * 26)
    n_context = 1 + int(b * 6)
    ctx_tokens = int(2200 + b * 46000)
    n_orch = 1 + int(b * 26)
    n_stages = min(len(REVIEW_PHRASES), int(3 + b * 8))
    block_files = max(3, int(b * 40))
    n_services = 0 if md_only else 1 + int(b * 30)
    max_source = max(3, int(spec.get("files") or 400) // 3)
    n_source = 0 if md_only else min(max_source, max(3, int(140 - b * 136)))
    n_doc_dups = 2 + int(b * 5)
    agent_padding = int(b * 14)
    stages = REVIEW_PHRASES[:n_stages]

    prefix = "" if md_only else "agents/"
    jobs = [AGENT_JOBS[i % len(AGENT_JOBS)] for i in range(n_agents)]
    for i, (name, job) in enumerate(jobs):
        add(f"{prefix}{name}-{i:02d}.agent.md",
            _agent_body(name, job, include_block=i < block_files, stages=stages if i < 3 else [],
                        padding=agent_padding))

    if dup_copies:
        base = _agent_body("intake", "lead intake and qualification", True, stages, agent_padding)
        variants = [base, base.replace("repository search", "repo search"), base.upper(),
                    base.replace("\n\n", "\n   \n"), base + "\n"]
        folder = "" if md_only else "agents/legacy/"
        for i in range(dup_copies):
            add(f"{folder}intake-copy-{i:02d}.agent.md", variants[i % len(variants)])

    ctx_body = "# Working context\n\n" + SHARED_BLOCK + "\n\n## Account history\n\n" + (
        FILLER_PARA * max(1, ctx_tokens * 4 // len(FILLER_PARA)))
    cprefix = "" if md_only else "context/"
    mprefix = "" if md_only else "memory/"
    add(f"{cprefix}context.md", ctx_body)
    add(f"{mprefix}memory.md", "# Long term memory\n\n" + ctx_body[: max(600, len(ctx_body) // 2)])
    for i in range(max(0, n_context - 1)):
        add(f"{cprefix}context-{i:02d}.md",
            f"# Context {i}\n\n" + ctx_body[: max(500, len(ctx_body) // (3 + i))])
    if dup_copies >= 4:
        for i in range(min(4, dup_copies // 3)):
            add(f"{cprefix}archive/context-copy-{i:02d}.md",
                ctx_body if i % 2 == 0 else ctx_body.upper())

    oprefix = "" if md_only else ""
    add(f"{oprefix}orchestrator.md",
        "# Orchestrator\n\n" + SHARED_BLOCK + "\n\n## Review workflow\n\nEvery change moves through "
        + ", ".join(stages or ["self review"]) + ".\n\n## Stages\n\n"
        + "\n".join(f"{i + 1}. {name}" for i, (name, _) in enumerate(jobs[:8])) + "\n")
    add("instructions.md", "# Build instructions\n\n" + SHARED_BLOCK
        + "\n\n## Review workflow\n\nGates: " + ", ".join(stages or ["self review"]) + ".\n")
    add("instruction.md", "# Contributor instruction\n\n" + SHARED_BLOCK
        + "\n\nKeep pull requests small and reference the ticket id.\n")
    pprefix = "" if md_only else "prompts/"
    for i in range(n_orch):
        add(f"{pprefix}stage-{i:02d}.prompt.md",
            f"# Stage {i} prompt\n\n" + (SHARED_BLOCK if i < block_files else "Focus on this stage.")
            + f"\n\nHandle stage {i} of the pipeline and nothing else.\n")
    add("workflow.md", "# Workflow\n\nGates: " + ", ".join(stages or ["self review"]) + ".\n")

    sprefix = "" if md_only else "skills/"
    for i in range(n_skills):
        name = SKILL_NAMES[i % len(SKILL_NAMES)]
        add(f"{sprefix}{name}-{i:02d}.skill.md",
            f"# Skill: {name}\n\n" + (SHARED_BLOCK if i % 3 == 0 else f"Use for {name} tasks.")
            + f"\n\nUse this skill when the task mentions {name}.\n")

    add("README.md", f"# {spec['repo']}\n\nA multi agent platform for {spec['repo'].replace('-', ' ')}.\n")
    dup_doc = ("# Runbook\n\n## Deploy\n\nRun the deploy pipeline, wait for the health check, then "
               "announce in the release channel. If the health check fails, roll back and open an "
               "incident ticket with the release id and the failing check name.\n")
    for i in range(n_doc_dups):
        folder = "" if md_only else "docs/"
        add(f"{folder}runbook-{chr(97 + i)}.md", dup_doc if i % 2 == 0 else dup_doc + "\n")

    if not md_only:
        add("docs/architecture.mmd", "graph TD\n  A[intake]-->B[triage]\n  B-->C[proposal]\n")
        add("config/settings.yaml", f"service: {spec['repo']}\nreplicas: 2\n")
        add("package.json", '{"name":"%s","version":"1.0.0"}' % spec["repo"])
        for i in range(n_services):
            add(f"services/svc-{i:02d}/package.json", '{"name":"svc-%02d"}' % i)
            add(f"services/svc-{i:02d}/index.js", f"export const handler = () => 'svc-{i}';\n")
        for i in range(n_source):
            add(f"src/module_{i:03d}.py",
                f"def handler_{i}(payload):\n    \"\"\"Handle payload {i}.\"\"\"\n    return payload\n")

    if not final:
        return entries

    # ---- final pass only: pad to the requested totals -------------------
    target_tokens = int(spec.get("tokens") or 0)
    current_tokens = sum(len(e["content"]) for e in entries) // 4
    if target_tokens > current_tokens:
        need_chars = (target_tokens - current_tokens) * 4
        chunk = FILLER_PARA * max(1, need_chars // len(FILLER_PARA) + 1)
        folder = "" if md_only else "docs/"
        add(f"{folder}knowledge-base.md", "# Knowledge base\n\n" + chunk[:need_chars])

    target_files = int(spec.get("files") or len(entries))
    skipped_target = 0
    if target_files > len(entries):
        remaining = target_files - len(entries)
        skipped_target = min(remaining, max(0, int(remaining * (0.35 if spec.get("partial") else 0.15))))
        for i in range(skipped_target):
            kind = i % 4
            if kind == 0:
                entries.append({"path": f"assets/image-{i:03d}.png", "size_bytes": 40000 + i,
                                "parse_status": "SkippedUnsupported",
                                "skip_reason": "Extension '.png' is not in the supported analysis list"})
            elif kind == 1:
                entries.append({"path": f"assets/doc-{i:03d}.pdf", "size_bytes": 220000 + i,
                                "parse_status": "SkippedUnsupported",
                                "skip_reason": "Extension '.pdf' is not in the supported analysis list"})
            elif kind == 2:
                entries.append({"path": f"vendor/bundle-{i:03d}.json", "size_bytes": 7 * 1024 * 1024 + i,
                                "parse_status": "SkippedOversized",
                                "skip_reason": "File is 7.0 MB which is above the 5 MB parse limit"})
            else:
                entries.append({"path": f"assets/blob-{i:03d}.json", "size_bytes": 90000 + i,
                                "parse_status": "Binary", "skip_reason": "File contains binary data"})
        for i in range(remaining - skipped_target):
            add(f"docs/notes/note_{i:03d}.txt", f"Note {i}: archived meeting note for the delivery team.\n")
    return entries


async def seed_drafts(limit_scans: int = 3, per_scan: int = 2) -> dict:
    """Generate a small number of REAL LLM drafts so the demo history shows draft output."""
    from scanner import generate_single_draft

    made, failed = 0, []
    cursor = scans.find({"is_seed": True, "status": "completed"}).sort("created_at", -1)
    picked = await cursor.to_list(length=limit_scans)
    for scan in picked:
        for cand in (scan.get("draft_candidates") or [])[:per_scan]:
            try:
                await generate_single_draft(scan["id"], cand["source_path"])
                made += 1
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{scan['id']}/{cand['source_path']}: {exc}")
                log.warning("seed draft failed: %s", exc)
    return {"drafts": made, "failed": failed[:5]}


async def _tune(spec: dict, assumptions: dict):
    """Bisect the badness dial until the real analyzer lands in the requested verdict band."""
    lo_score, hi_score = BAND_TARGETS[spec["band"]]
    low, high = 0.02, 0.99
    best = None
    for _ in range(9):
        mid = (low + high) / 2
        entries = build_entries(spec, mid, final=False)
        inv = inventory_from_entries(entries)
        analysis = analyze(inv, assumptions)
        score = analysis["overall_score"]
        if best is None or abs(score - (lo_score + hi_score) / 2) < abs(best[1] - (lo_score + hi_score) / 2):
            best = (mid, score)
        if score > hi_score:
            low = mid
        elif score < lo_score:
            high = mid
        else:
            return mid, score
        await asyncio.sleep(0)
    return best


def _write_workspace(spec: dict, entries: list) -> str:
    root = os.path.join(SEED_WORKSPACE, f"scan-{spec['repo']}", spec["repo"])
    os.makedirs(root, exist_ok=True)
    for e in entries:
        if "content" not in e:
            continue
        target = os.path.join(root, e["path"])
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(e["content"])
    return root


def _progress_all_done() -> dict:
    return {
        "stages": [{"key": k, "label": label, "status": "done", "detail": ""} for k, label in STAGES],
        "current_stage": "reports",
        "percent": 100,
    }


def _progress_failed(fail_key: str) -> dict:
    stages = []
    hit = False
    for k, label in STAGES:
        if k == fail_key:
            stages.append({"key": k, "label": label, "status": "failed", "detail": ""})
            hit = True
        elif hit:
            stages.append({"key": k, "label": label, "status": "pending", "detail": ""})
        else:
            stages.append({"key": k, "label": label, "status": "done", "detail": ""})
    return {"stages": stages, "current_stage": fail_key, "percent": 20}


async def _insert_failed(spec: dict, created_at):
    scan_id = f"SCN-{created_at.strftime('%Y-%m-%d')}-0001"
    fail_key = "importing" if spec["status"] == "ImportFailed" else "extracting"
    if spec["status"] == "InsufficientData":
        fail_key = "adversary"
    doc = {
        "id": scan_id, "user_id": DEMO_USER_ID, "is_seed": True, "seed_label": "Seeded demo",
        "source_type": spec["source"], "repo_name": spec["repo"], "repo_owner": spec.get("owner"),
        "branch": spec.get("branch"), "status": spec["status"],
        "error_code": spec.get("error_code"), "error_message": spec.get("error"),
        "retry_after_minutes": None,
        "total_files": spec.get("files") or 0,
        "parsed_files": spec.get("files") or 0 if spec["status"] == "InsufficientData" else 0,
        "skipped_files": 0, "analyzed_tokens": 0,
        "overall_score": 0, "verdict": None, "partial_scan": False, "skip_ratio": 0,
        "estimated_monthly_token_waste": 0, "estimated_monthly_credit_waste": 0,
        "estimated_monthly_dollar_waste": 0, "estimated_savings_low": 0, "estimated_savings_high": 0,
        "estimated_credit_savings_low": 0, "estimated_credit_savings_high": 0,
        "issue_count": 0, "draft_count": 0, "draft_status": "skipped",
        "kpis": {"files_discovered": spec.get("files") or 0,
                 "files_parsed": spec.get("files") or 0 if spec["status"] == "InsufficientData" else 0,
                 "files_skipped": 0, "agent_like_files": 0, "tokens_analyzed": 0},
        "warnings": [spec.get("error")] if spec.get("error") else [],
        "progress": _progress_failed(fail_key),
        "created_at": created_at, "completed_at": created_at + timedelta(seconds=9),
        "updated_at": created_at, "workspace_dir": None,
        "detections": {}, "assumptions": {}, "penalty_ledger": [], "top_drivers": [],
        "recommended_actions": [], "clusters": [], "overlap_groups": [], "draft_candidates": [],
    }
    await scans.insert_one(doc)
    return scan_id


async def seed_demo_data(force: bool = False) -> dict:
    existing = await scans.count_documents({"is_seed": True})
    if existing >= len(SEED_SPECS) and not force:
        return {"seeded": 0, "already": existing}
    if force:
        seed_ids = [s["id"] async for s in scans.find({"is_seed": True}, {"id": 1})]
        for sid in seed_ids:
            await file_assets.delete_many({"scan_id": sid})
            await issues_col.delete_many({"scan_id": sid})
            await category_scores.delete_many({"scan_id": sid})
            await drafts_col.delete_many({"scan_id": sid})
        await scans.delete_many({"is_seed": True})

    settings = await get_settings()
    assumptions = settings["assumptions"]
    now = utcnow()
    created = 0

    for spec in SEED_SPECS:
        created_at = now - timedelta(days=spec["days"], hours=(spec["days"] * 7) % 20,
                                     minutes=(spec["days"] * 13) % 60)
        if spec.get("status"):
            await _insert_failed(spec, created_at)
            created += 1
            continue

        badness, _score = await _tune(spec, assumptions)
        entries = build_entries(spec, badness, final=True)
        inv = inventory_from_entries(entries)
        analysis = analyze(inv, assumptions, scan_date=created_at)
        root = _write_workspace(spec, entries)

        scan_id = f"SCN-{created_at.strftime('%Y-%m-%d')}-0001"
        suffix = 1
        while await scans.find_one({"id": scan_id}):
            suffix += 1
            scan_id = f"SCN-{created_at.strftime('%Y-%m-%d')}-{suffix:04d}"

        warnings = list(inv.warnings)
        if inv.skipped_files:
            reasons = ", ".join(f"{v} {k}" for k, v in sorted(inv.skip_reasons.items()))
            warnings.append(
                f"{inv.skipped_files} of {len(inv.files)} files were skipped ({reasons}). "
                "Skipped files still appear in the inventory with their reason."
            )
        if analysis["partial_scan"]:
            warnings.append(
                f"More than 20% of files were skipped ({analysis['skip_ratio'] * 100:.1f}%), so this "
                "verdict carries a PartialScan badge."
            )

        candidates = select_draft_targets(inv.files, analysis, limit=MAX_DRAFTS)
        doc = {
            "id": scan_id, "user_id": DEMO_USER_ID, "is_seed": True, "seed_label": "Seeded demo",
            "source_type": spec["source"], "repo_name": spec["repo"], "repo_owner": spec.get("owner"),
            "branch": spec.get("branch"), "status": "completed",
            "error_code": None, "error_message": None, "retry_after_minutes": None,
            "total_files": inv.total_files, "parsed_files": inv.parsed_files,
            "skipped_files": inv.skipped_files, "analyzed_tokens": inv.analyzed_tokens,
            "overall_score": analysis["overall_score"], "verdict": analysis["verdict"],
            "partial_scan": analysis["partial_scan"], "skip_ratio": analysis["skip_ratio"],
            "issue_count": len(analysis["issues"]), "draft_count": 0, "draft_status": "none",
            "kpis": {
                "files_discovered": inv.total_files, "files_parsed": inv.parsed_files,
                "files_skipped": inv.skipped_files,
                "agent_like_files": sum(1 for f in inv.files if f.agent_like),
                "tokens_analyzed": inv.analyzed_tokens,
            },
            "warnings": warnings,
            "detections": analysis["detections"], "assumptions": analysis["assumptions"],
            "penalty_ledger": analysis["penalty_ledger"], "top_drivers": analysis["top_drivers"],
            "recommended_actions": analysis["recommended_actions"],
            "clusters": analysis["clusters"], "overlap_groups": analysis["overlap_groups"],
            "draft_candidates": [{k: v for k, v in c.items() if k != "content"} for c in candidates],
            "progress": _progress_all_done(),
            "created_at": created_at,
            "completed_at": created_at + timedelta(seconds=45 + inv.total_files // 20),
            "updated_at": created_at,
            "workspace_dir": root,
            "content_expires_at": now + timedelta(days=7),
            "metadata_expires_at": now + timedelta(days=30),
            "archive_bytes": sum(len(e.get("content", "")) for e in entries),
            **analysis["savings"],
        }
        await scans.insert_one(doc)

        assets = []
        for i, f in enumerate(inv.files):
            d = f.to_public()
            d["id"] = f"FIL-{scan_id}-{i + 1:05d}"
            d["scan_id"] = scan_id
            assets.append(d)
        for chunk in range(0, len(assets), 500):
            await file_assets.insert_many(assets[chunk:chunk + 500])
        if analysis["issues"]:
            await issues_col.insert_many([{**i, "scan_id": scan_id} for i in analysis["issues"]])
        if analysis["category_scores"]:
            await category_scores.insert_many([
                {**c, "scan_id": scan_id, "id": f"CAT-{scan_id}-{c['category']}"}
                for c in analysis["category_scores"]])
        created += 1
        log.info("seeded %s %s score=%s verdict=%s issues=%s files=%s tokens=%s",
                 scan_id, spec["repo"], analysis["overall_score"], analysis["verdict"],
                 len(analysis["issues"]), inv.total_files, inv.analyzed_tokens)
        await asyncio.sleep(0)

    return {"seeded": created}
