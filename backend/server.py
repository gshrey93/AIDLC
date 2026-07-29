"""Bloat Guardian API."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

import series as series_mod
from core import exports as export_mod
from core import importer
from core.config import INVENTORY_GROUPS, MAX_ARCHIVE_BYTES, MAX_FILES
from core.report import build_payload, inventory_summary
from db import (
    DEMO_USER_ID, category_scores, drafts as drafts_col, ensure_demo_user, ensure_indexes,
    export_jobs, file_assets, issues as issues_col, next_scan_id, repo_series, scans, serialize,
    utcnow,
)
from scanner import (
    KEEP_RECENT_SCANS, delete_scan, delete_series, empty_kpis, enforce_retention,
    generate_single_draft, initial_progress, run_scan,
)
from seed import SEED_SPECS, seed_demo_data, seed_drafts
from settings_store import (
    get_settings, public_settings, reset_assumptions, resolve_llm_credentials, update_settings,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("bloatguardian")

app = FastAPI(title="Bloat Guardian API", version="1.0.0")
api = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SEED_STATE = {"status": "idle", "seeded": 0, "target": len(SEED_SPECS), "error": None}

# Markers that mean "the model provider refused on budget/quota grounds" rather than a code fault.
LLM_BUDGET_MARKERS = (
    "spend limit", "daily spend", "quota", "insufficient_quota", "billing",
    "credit balance", "exceeded your current quota", "rate_limit_exceeded",
)
LLM_BUDGET_MESSAGE = (
    "The language model budget has run out, so no new draft could be written. Top up your "
    "Universal Key balance (Profile > Universal Key > Add Balance), or add your own Anthropic or "
    "Gemini key in Settings. Everything else in this scan is unaffected."
)


def _is_llm_budget_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in LLM_BUDGET_MARKERS)
GITHUB_URL_HINT = "https://github.com/{owner}/{repo}"


# ------------------------------------------------------------------ models
class SettingsPatch(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None
    use_platform_key: bool | None = None
    auto_draft_count: int | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    github_token: str | None = None
    bitbucket_token: str | None = None
    assumptions: dict | None = None


class DraftRequest(BaseModel):
    source_path: str


class ArchivePatch(BaseModel):
    archived: bool


# ----------------------------------------------------------------- helpers
async def _get_scan_or_404(scan_id: str) -> dict:
    scan = await scans.find_one({"id": scan_id})
    if not scan:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id} was not found")
    return scan


async def _load_payload(scan_id: str) -> dict:
    scan = await _get_scan_or_404(scan_id)
    files = await file_assets.find({"scan_id": scan_id}).to_list(length=MAX_FILES + 50)
    issue_docs = await issues_col.find({"scan_id": scan_id}).sort("estimated_token_waste", -1).to_list(2000)
    cats = await category_scores.find({"scan_id": scan_id}).to_list(20)
    draft_docs = await drafts_col.find({"scan_id": scan_id}).sort("created_at", 1).to_list(60)
    order = {c: i for i, c in enumerate(
        ["redundancy", "token_bloat", "review_overhead", "agent_sprawl", "architecture_inefficiency"])}
    cats.sort(key=lambda c: order.get(c.get("category"), 9))
    payload = build_payload(
        serialize(scan), serialize(files),
        {
            "category_scores": serialize(cats),
            "issues": serialize(issue_docs),
            "top_drivers": serialize(scan.get("top_drivers") or []),
            "recommended_actions": serialize(scan.get("recommended_actions") or []),
            "penalty_ledger": serialize(scan.get("penalty_ledger") or []),
            "assumptions": serialize(scan.get("assumptions") or {}),
            "detections": serialize(scan.get("detections") or {}),
            "clusters": serialize(scan.get("clusters") or []),
            "overlap_groups": serialize(scan.get("overlap_groups") or []),
        },
        serialize(draft_docs), serialize(scan.get("warnings") or []),
    )
    return payload


async def _record_export(scan_id: str, export_type: str, status: str, error: str | None = None):
    doc = {
        "id": f"EXP-{scan_id}-{export_type}-{int(datetime.now(timezone.utc).timestamp())}",
        "scan_id": scan_id, "export_type": export_type, "status": status,
        "error": error, "created_at": utcnow(),
    }
    await export_jobs.insert_one(dict(doc))
    return doc


def _download(content: bytes | str, filename: str, media_type: str) -> Response:
    body = content.encode("utf-8") if isinstance(content, str) else content
    return Response(
        content=body, media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(body)),
            "Cache-Control": "no-store",
        },
    )


# ------------------------------------------------------------------ routes
@api.get("/")
async def root():
    return {"message": "Bloat Guardian API", "version": "1.0.0"}


@api.get("/health")
async def health():
    return {"status": "ok", "seed": SEED_STATE}


@api.get("/me")
async def me():
    user = await ensure_demo_user()
    return serialize(user)


@api.get("/config")
async def config_info():
    return {
        "max_archive_mb": MAX_ARCHIVE_BYTES // (1024 * 1024),
        "max_files": MAX_FILES,
        "github_url_pattern": "^https://github\\.com/[^/]+/[^/]+/?$",
        "bitbucket_url_pattern": "^https://bitbucket\\.org/[^/]+/[^/]+/?$",
        "github_url_hint": GITHUB_URL_HINT,
        "inventory_groups": INVENTORY_GROUPS,
        "retention": {
            "content_days": 7, "metadata_days": 30, "keep_recent_scans": None,
            "prune_old_scans": False,
        },
        "rights_ack_text": "I confirm I have the right to analyze this repository content",
        "seed": SEED_STATE,
    }


@api.get("/stats/overview")
async def stats_overview():
    completed = await scans.find({"status": "completed"}).to_list(200)
    redundant_files = 0
    consolidate = 0
    for s in completed:
        det = s.get("detections") or {}
        redundant_files += int(det.get("duplicate_clusters_found") or 0)
        consolidate += len(s.get("draft_candidates") or [])
    tokens = sum(int(s.get("estimated_monthly_token_waste") or 0) for s in completed)
    credits = sum(float(s.get("estimated_monthly_credit_waste") or 0) for s in completed)
    dollars = sum(float(s.get("estimated_monthly_dollar_waste") or 0) for s in completed)
    verdicts: dict = {}
    for s in completed:
        v = s.get("verdict") or "Unknown"
        verdicts[v] = verdicts.get(v, 0) + 1
    return {
        "scans_completed": len(completed),
        "duplicate_clusters_found": redundant_files,
        "estimated_monthly_token_waste": tokens,
        "estimated_monthly_credit_waste": round(credits, 2),
        "estimated_monthly_dollar_waste": round(dollars, 2),
        "files_recommended_to_consolidate": consolidate,
        "verdict_distribution": verdicts,
    }


# ------------------------------------------------------------- scan create
@api.post("/scans")
async def create_scan(
    background: BackgroundTasks,
    source_type: str = Form(...),
    rights_ack: bool = Form(False),
    repo_url: str | None = Form(None),
    branch: str | None = Form(None),
    zip_file: UploadFile | None = File(None),
    md_files: list[UploadFile] = File(default=[]),
):
    if not rights_ack:
        raise HTTPException(
            status_code=400,
            detail="You must confirm you have the right to analyze this repository content before a scan can start.",
        )
    source_type = (source_type or "").strip().lower()
    if source_type not in ("github", "bitbucket", "zip", "md"):
        raise HTTPException(status_code=400, detail=f"Unsupported source type '{source_type}'")

    work_dir = importer.make_work_dir("scan-")
    spec = {"source_type": source_type, "work_dir": work_dir, "cleanup": []}
    repo_name, repo_owner = None, None

    if source_type in ("github", "bitbucket"):
        if not repo_url or not repo_url.strip():
            raise HTTPException(status_code=400, detail="A repository URL is required")
        parsed = (importer.parse_github_url(repo_url) if source_type == "github"
                  else importer.parse_bitbucket_url(repo_url))
        if not parsed:
            host = "github.com" if source_type == "github" else "bitbucket.org"
            raise HTTPException(
                status_code=400,
                detail=f"That URL does not look right. Use https://{host}/{{owner}}/{{repo}}",
            )
        repo_owner, repo_name, url_branch = parsed
        spec["repo_url"] = repo_url.strip()
        spec["branch"] = (branch or url_branch or "").strip() or None
    elif source_type == "zip":
        if zip_file is None:
            raise HTTPException(status_code=400, detail="A .zip file is required")
        name = (zip_file.filename or "upload.zip")
        if not name.lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail="Only .zip archives can be uploaded")
        dest = os.path.join(work_dir, "upload.zip")
        size = 0
        with open(dest, "wb") as fh:
            while True:
                chunk = await zip_file.read(1024 * 512)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_ARCHIVE_BYTES:
                    fh.close()
                    os.remove(dest)
                    raise HTTPException(
                        status_code=413,
                        detail="ZipTooLarge: the archive is larger than the 250 MB limit",
                    )
                fh.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file was empty")
        repo_name = os.path.splitext(os.path.basename(name))[0]
        spec["zip_path"] = dest
        spec["repo_name"] = repo_name
    else:
        uploads = [f for f in (md_files or []) if f and f.filename]
        if not uploads:
            raise HTTPException(status_code=400, detail="At least one .md file is required")
        bad = [f.filename for f in uploads if not f.filename.lower().endswith(".md")]
        if bad:
            raise HTTPException(
                status_code=400,
                detail=f"Only .md files can be uploaded here. Rejected: {', '.join(bad[:4])}",
            )
        saved = []
        total = 0
        os.makedirs(os.path.join(work_dir, "uploads"), exist_ok=True)
        for f in uploads:
            data = await f.read()
            total += len(data)
            if total > MAX_ARCHIVE_BYTES:
                raise HTTPException(status_code=413, detail="Uploads exceed the 250 MB limit")
            path = os.path.join(work_dir, "uploads", os.path.basename(f.filename))
            with open(path, "wb") as fh:
                fh.write(data)
            saved.append((os.path.basename(f.filename), path))
        repo_name = "markdown-upload"
        spec["md_files"] = saved
        spec["repo_name"] = repo_name

    scan_id = await next_scan_id()
    now = utcnow()
    doc = {
        "id": scan_id, "user_id": DEMO_USER_ID, "is_seed": False,
        "source_type": source_type, "repo_name": repo_name, "repo_owner": repo_owner,
        "branch": spec.get("branch"), "status": "queued",
        "rights_ack": True, "source_url": spec.get("repo_url"),
        "total_files": 0, "parsed_files": 0, "skipped_files": 0, "analyzed_tokens": 0,
        "overall_score": 0, "verdict": None, "partial_scan": False, "skip_ratio": 0,
        "estimated_monthly_token_waste": 0, "estimated_monthly_credit_waste": 0,
        "estimated_monthly_dollar_waste": 0, "estimated_savings_low": 0, "estimated_savings_high": 0,
        "estimated_credit_savings_low": 0, "estimated_credit_savings_high": 0,
        "issue_count": 0, "draft_count": 0, "draft_status": "pending",
        "kpis": empty_kpis(), "warnings": [], "progress": initial_progress(),
        "detections": {}, "assumptions": {}, "penalty_ledger": [], "top_drivers": [],
        "recommended_actions": [], "clusters": [], "overlap_groups": [], "draft_candidates": [],
        "created_at": now, "updated_at": now, "completed_at": None,
        "error_code": None, "error_message": None, "retry_after_minutes": None,
        "workspace_dir": None,
    }
    await scans.insert_one(doc)
    # Bind the run to its repository series straight away so it shows up in history while queued.
    # For git sources the branch may still be unresolved; the scanner re-binds after the import.
    await series_mod.attach_scan(scan_id, source_type, repo_owner, repo_name, spec.get("branch"))
    background.add_task(run_scan, scan_id, spec)
    log.info("queued scan %s (%s)", scan_id, source_type)
    return serialize(await scans.find_one({"id": scan_id}))


# --------------------------------------------------------------- scan read
@api.get("/scans")
async def list_scans(limit: int = Query(100, ge=1, le=500), only_recent: bool = False):
    cursor = scans.find({}, {
        "detections": 0, "penalty_ledger": 0, "clusters": 0, "overlap_groups": 0,
        "draft_candidates": 0, "recommended_actions": 0, "assumptions": 0,
    }).sort("created_at", -1)
    docs = await cursor.to_list(length=limit)
    if only_recent:
        docs = docs[:KEEP_RECENT_SCANS]
    return {
        "scans": serialize(docs),
        "total": await scans.count_documents({}),
        "real_total": await scans.count_documents({"is_seed": {"$ne": True}}),
        "seed_total": await scans.count_documents({"is_seed": True}),
        "keep_recent_scans": KEEP_RECENT_SCANS,
        "seed": SEED_STATE,
    }


@api.get("/scans/{scan_id}")
async def get_scan(scan_id: str):
    scan = await _get_scan_or_404(scan_id)
    out = serialize(scan)
    if scan.get("series_id"):
        series = await repo_series.find_one({"id": scan["series_id"]})
        out["series"] = serialize(series)
    return out


@api.get("/scans/{scan_id}/results")
async def get_results(scan_id: str):
    payload = await _load_payload(scan_id)
    payload["inventory_groups"] = INVENTORY_GROUPS
    payload["handoff_prompt"] = export_mod.handoff_prompt(payload)
    return payload


@api.get("/scans/{scan_id}/files")
async def get_files(scan_id: str, group: str | None = None, status: str | None = None,
                    limit: int = Query(500, ge=1, le=2000), skip: int = 0):
    await _get_scan_or_404(scan_id)
    query: dict = {"scan_id": scan_id}
    if group:
        query["inventory_group"] = group
    if status:
        query["parse_status"] = status
    total = await file_assets.count_documents(query)
    docs = await file_assets.find(query).sort("estimated_tokens", -1).skip(skip).to_list(length=limit)
    all_files = await file_assets.find({"scan_id": scan_id}, {
        "inventory_group": 1, "parse_status": 1, "estimated_tokens": 1}).to_list(MAX_FILES + 50)
    return {"files": serialize(docs), "total": total, "summary": inventory_summary(serialize(all_files))}


@api.delete("/scans/{scan_id}")
async def remove_scan(scan_id: str):
    ok = await delete_scan(scan_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id} was not found")
    return {"deleted": scan_id}


# ------------------------------------------------------------ repo series
@api.get("/series")
async def list_repo_series(include_archived: bool = True):
    result = await series_mod.list_series(include_archived=include_archived)
    return {
        "series": serialize(result["series"]),
        "counts": result["counts"],
        "seed": SEED_STATE,
    }


@api.post("/series/backfill")
async def run_series_backfill():
    """Idempotent migration that attaches any unassigned scan to a series."""
    return await series_mod.backfill()


@api.get("/series/export/archive")
async def export_archived_bundle():
    """Zip of the latest completed report for every archived series, plus a manifest CSV."""
    series_docs = await series_mod.archived_series()
    if not series_docs:
        raise HTTPException(
            status_code=404,
            detail="There are no archived series yet. Archive a repository from the history page first.",
        )
    entries = []
    for s in series_docs:
        manifest = {
            "series_id": s.get("id"),
            "display_name": s.get("display_name"),
            "source_type": s.get("source_type"),
            "repo_owner": s.get("repo_owner") or "",
            "repo_name": s.get("repo_name"),
            "branch": s.get("branch") or "",
            "run_count": s.get("run_count") or 0,
            "completed_run_count": s.get("completed_run_count") or 0,
            "first_run_at": serialize(s.get("first_run_at")) or "",
            "latest_run_at": serialize(s.get("latest_run_at")) or "",
            "latest_scan_id": s.get("latest_completed_scan_id") or s.get("latest_scan_id") or "",
            "latest_score": s.get("latest_score") if s.get("latest_score") is not None else "",
            "latest_verdict": s.get("latest_verdict") or "",
            "previous_score": s.get("previous_score") if s.get("previous_score") is not None else "",
            "score_delta": s.get("score_delta") if s.get("score_delta") is not None else "",
            "best_score": s.get("best_score") if s.get("best_score") is not None else "",
            "archived_at": serialize(s.get("archived_at")) or "",
            "note": "",
        }
        payload = None
        target = s.get("latest_completed_scan_id")
        if target:
            try:
                payload = await _load_payload(target)
                scan = payload["scan"]
                manifest["estimated_monthly_credit_waste"] = scan.get("estimated_monthly_credit_waste") or 0
                manifest["estimated_monthly_dollar_waste"] = scan.get("estimated_monthly_dollar_waste") or 0
            except HTTPException:
                payload = None
                manifest["note"] = "The run referenced by this series no longer exists."
        entries.append({"manifest": manifest, "payload": payload})

    try:
        data = await asyncio.to_thread(export_mod.archive_bundle_zip, entries)
    except Exception as exc:  # noqa: BLE001
        log.exception("archive bundle failed")
        raise HTTPException(
            status_code=500,
            detail=f"The archive bundle could not be built: {exc}. Download individual reports instead.",
        ) from exc
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _download(data, f"bloat-guardian-archive-{stamp}.zip", "application/zip")


@api.get("/series/{series_id}")
async def get_repo_series(series_id: str):
    series = await repo_series.find_one({"id": series_id})
    if not series:
        raise HTTPException(status_code=404, detail=f"Series {series_id} was not found")
    runs = await scans.find({"series_id": series_id}, series_mod.RUN_FIELDS).sort("created_at", -1).to_list(500)
    out = serialize(series)
    out["runs"] = serialize(runs)
    return out


@api.patch("/series/{series_id}/archive")
async def archive_repo_series(series_id: str, body: ArchivePatch):
    series = await series_mod.set_archived(series_id, body.archived)
    if not series:
        raise HTTPException(status_code=404, detail=f"Series {series_id} was not found")
    return serialize(series)


@api.delete("/series/{series_id}")
async def remove_repo_series(series_id: str):
    series = await repo_series.find_one({"id": series_id})
    if not series:
        raise HTTPException(status_code=404, detail=f"Series {series_id} was not found")
    removed = await delete_series(series_id)
    return {"deleted": series_id, "runs_deleted": removed}


# ------------------------------------------------------------------ drafts
@api.post("/scans/{scan_id}/drafts")
async def create_draft(scan_id: str, body: DraftRequest):
    await _get_scan_or_404(scan_id)
    draft: dict | None = None
    try:
        draft = await generate_single_draft(scan_id, body.source_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="The model took too long to answer. Try again.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        if _is_llm_budget_error(exc):
            log.warning("draft blocked by LLM budget: %s", exc)
            raise HTTPException(status_code=402, detail=LLM_BUDGET_MESSAGE) from exc
        log.exception("draft generation failed")
        raise HTTPException(status_code=500, detail=f"Draft generation failed: {exc}") from exc
    return serialize(draft)


# ----------------------------------------------------------------- exports
EXPORT_TYPES = {"pdf_full", "pdf_redacted", "csv", "draft_zip", "handoff_zip"}


@api.get("/scans/{scan_id}/export/{export_type}")
async def export_scan(scan_id: str, export_type: str):
    if export_type not in EXPORT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown export type '{export_type}'")
    payload = await _load_payload(scan_id)
    base = (payload["scan"].get("repo_name") or "scan").replace("/", "-")
    sid = payload["scan"]["id"]
    try:
        if export_type == "pdf_full":
            data = await asyncio.to_thread(export_mod.full_pdf, payload)
            await _record_export(scan_id, export_type, "completed")
            return _download(data, f"{base}-{sid}-full-report.pdf", "application/pdf")
        if export_type == "pdf_redacted":
            data = await asyncio.to_thread(export_mod.redacted_pdf, payload)
            await _record_export(scan_id, export_type, "completed")
            return _download(data, f"{base}-{sid}-redacted-report.pdf", "application/pdf")
        if export_type == "csv":
            text = export_mod.issues_csv(payload)
            await _record_export(scan_id, export_type, "completed")
            return _download(text, f"{base}-{sid}-findings.csv", "text/csv")
        if export_type == "draft_zip":
            data = await asyncio.to_thread(export_mod.drafts_zip, payload)
            await _record_export(scan_id, export_type, "completed")
            return _download(data, f"{base}-{sid}-drafts.zip", "application/zip")
        data = await asyncio.to_thread(export_mod.handoff_zip, payload)
        await _record_export(scan_id, export_type, "completed")
        return _download(data, f"{base}-{sid}-vscode-handoff.zip", "application/zip")
    except Exception as exc:  # noqa: BLE001
        log.exception("export %s failed", export_type)
        await _record_export(scan_id, export_type, "failed", str(exc))
        raise HTTPException(
            status_code=500,
            detail=f"{export_type} generation failed: {exc}. Use the print view or copy fallback instead.",
        ) from exc


@api.get("/scans/{scan_id}/print", response_class=HTMLResponse)
async def print_view(scan_id: str, redacted: bool = False):
    payload = await _load_payload(scan_id)
    return HTMLResponse(export_mod.print_view_html(payload, redacted=redacted))


@api.get("/scans/{scan_id}/export-preview")
async def export_preview(scan_id: str):
    payload = await _load_payload(scan_id)
    scan = payload["scan"]
    jobs = await export_jobs.find({"scan_id": scan_id}).sort("created_at", -1).to_list(20)
    return {
        "scan_id": scan_id,
        "file_count": len(payload["files"]),
        "issue_count": len(payload["issues"]),
        "draft_count": len(payload["drafts"]),
        "skipped_count": int(scan.get("skipped_files") or 0),
        "included_sections": [
            "Cover with score and verdict", "Key numbers", "Category scores",
            "Top 5 waste drivers in plain language", "Savings assumptions and formulas",
            "How the score was calculated (penalty ledger)", "Findings table",
            "Evidence detail (full report only)", "Recommended actions",
            "File inventory by category", "Largest files", "Skipped files and warnings",
            "Draft replacement files (full report only)",
        ],
        "redaction_rules": [
            "File contents and code samples are removed",
            "Exact file and folder names are replaced with path aliases such as dir-01/file-007.md",
            "Evidence samples are stripped",
            "Draft file contents are removed, only the reduction summary is kept",
            "Counts, scores, category findings, penalties and savings estimates are preserved",
        ],
        "page_limits": {"pdf_full": 40, "pdf_redacted": 25},
        "csv_columns": export_mod.CSV_COLUMNS,
        "recent_jobs": serialize(jobs),
    }


@api.get("/scans/{scan_id}/handoff")
async def handoff(scan_id: str):
    payload = await _load_payload(scan_id)
    return {
        "scan_id": scan_id,
        "prompt": export_mod.handoff_prompt(payload),
        "summary_markdown": export_mod.efficiency_summary_md(payload),
        "package_files": [
            "efficiency-summary.md", "recommended-instruction.md", "recommended-orchestrator.md",
            "recommended-context.md", "findings.csv", "summary-prompt.txt", "README.md",
        ],
        "draft_count": len(payload["drafts"]),
        "vscode_uri_hint": "vscode://file/<absolute-path-to-unzipped-folder>",
        "manual_instructions": [
            "Download the handoff package and unzip it inside your project, for example ./bloat-guardian/.",
            "Open the folder in VS Code with: code ./bloat-guardian",
            "Or use File > Open Folder... and pick the unzipped folder.",
            "Open efficiency-summary.md first, then paste summary-prompt.txt into your coding agent.",
        ],
    }


# ---------------------------------------------------------------- settings
@api.get("/settings")
async def read_settings():
    return public_settings(await get_settings())


@api.put("/settings")
async def write_settings(patch: SettingsPatch):
    updated: dict
    try:
        updated = await update_settings(patch.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return public_settings(updated)


@api.post("/settings/assumptions/reset")
async def reset_assumption_defaults():
    return public_settings(await reset_assumptions())


RATE_PROMPT = (
    "You are a pricing researcher. For the model \"{model}\" from provider \"{provider}\", report the "
    "current published list price. Reply with STRICT JSON only, no prose, using exactly these keys:\n"
    '{{"input_dollars_per_million": <number>, "output_dollars_per_million": <number>, '
    '"as_of": "<YYYY-MM or best known date>", "source": "<where this price is published>", '
    '"confidence": "high|medium|low", "note": "<one short sentence>"}}\n'
    "If you are not certain, still give your best estimate and set confidence to low."
)


@api.post("/settings/refresh-rates")
async def refresh_rates():
    settings = await get_settings()
    api_key = provider = model = key_source = ""
    try:
        api_key, provider, model, key_source = resolve_llm_credentials(settings)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    from emergentintegrations.llm.chat import LlmChat, StreamDone, TextDelta, UserMessage

    chat = LlmChat(
        api_key=api_key, session_id=f"rates-{int(datetime.now(timezone.utc).timestamp())}",
        system_message="You answer with strict JSON and nothing else.",
    ).with_model(provider, model).with_params(max_tokens=1200)
    buf = []
    try:
        async for ev in chat.stream_message(UserMessage(text=RATE_PROMPT.format(model=model, provider=provider))):
            if isinstance(ev, TextDelta):
                buf.append(ev.content)
            elif isinstance(ev, StreamDone):
                break
    except Exception as exc:  # noqa: BLE001
        if _is_llm_budget_error(exc):
            raise HTTPException(status_code=402, detail=LLM_BUDGET_MESSAGE) from exc
        log.exception("rate refresh failed")
        raise HTTPException(status_code=502, detail=f"Could not reach the model: {exc}") from exc

    raw = "".join(buf).strip()
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise HTTPException(status_code=502, detail=f"The model did not return usable JSON: {raw[:200]}")
    parsed: dict = {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"The model returned invalid JSON: {raw[:200]}") from exc

    in_rate = float(parsed.get("input_dollars_per_million") or 0)
    out_rate = float(parsed.get("output_dollars_per_million") or 0)
    if in_rate <= 0 or out_rate <= 0:
        raise HTTPException(status_code=502, detail="The model returned a non-positive price")
    credits_per_dollar = float(settings["assumptions"].get("vendor_credits_per_dollar") or 100)
    suggestion = {
        "input_dollars_per_million": round(in_rate, 4),
        "output_dollars_per_million": round(out_rate, 4),
        "input_tokens_per_vendor_credit": int(round(1_000_000 / (in_rate * credits_per_dollar))),
        "output_tokens_per_vendor_credit": int(round(1_000_000 / (out_rate * credits_per_dollar))),
        "vendor_credits_per_dollar": credits_per_dollar,
    }
    return {
        "suggested": suggestion,
        "as_of": parsed.get("as_of"),
        "source": parsed.get("source"),
        "confidence": parsed.get("confidence"),
        "note": parsed.get("note"),
        "provenance": (
            f"Suggested by {provider}/{model} ({key_source}) on "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
            "These are model-reported list prices, not a live billing feed. Confirm against the "
            "provider pricing page before you apply them."
        ),
        "fetched_at": utcnow().isoformat(),
        "applied": False,
    }


# --------------------------------------------------------- admin utilities
@api.post("/admin/seed")
async def trigger_seed(background: BackgroundTasks, force: bool = False):
    if SEED_STATE["status"] == "running":
        return {"status": "running", "seed": SEED_STATE}
    background.add_task(_run_seed, force)
    return {"status": "started", "seed": SEED_STATE}


@api.post("/admin/retention")
async def trigger_retention():
    return await enforce_retention()


async def _run_seed(force: bool = False):
    SEED_STATE.update({"status": "running", "error": None})
    try:
        result = await seed_demo_data(force=force)
        SEED_STATE.update({"status": "drafting", "seeded": await scans.count_documents({"is_seed": True})})
        log.info("seed complete: %s", result)
        try:
            draft_result = await seed_drafts()
            log.info("seed drafts: %s", draft_result)
        except Exception:  # noqa: BLE001
            log.exception("seed drafts failed")
        try:
            # Seeded scans arrive without a series, so group them (archived by default).
            log.info("series backfill after seed: %s", await series_mod.backfill())
        except Exception:  # noqa: BLE001
            log.exception("series backfill after seed failed")
        SEED_STATE.update({"status": "done"})
    except Exception as exc:  # noqa: BLE001
        log.exception("seeding failed")
        SEED_STATE.update({"status": "failed", "error": str(exc)})


app.include_router(api)


@app.exception_handler(404)
async def not_found(_request, exc):
    detail = getattr(exc, "detail", "Not found")
    return JSONResponse(status_code=404, content={"detail": detail})


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    await ensure_demo_user()
    try:
        migration = await series_mod.backfill()
        log.info("series migration on startup: %s", migration)
    except Exception:  # noqa: BLE001
        log.exception("series migration failed")
    existing = await scans.count_documents({"is_seed": True})
    if existing < len(SEED_SPECS):
        asyncio.create_task(_run_seed(False))
    else:
        SEED_STATE.update({"status": "done", "seeded": existing})
    asyncio.create_task(_retention_loop())


async def _retention_loop():
    while True:
        try:
            await asyncio.sleep(3600)
            result = await enforce_retention()
            if result["content_purged"] or result["scans_purged"]:
                log.info("retention: %s", result)
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001
            log.exception("retention loop error")
