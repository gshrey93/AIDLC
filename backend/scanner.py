"""Scan orchestration: runs the proven core engine as a background job."""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from datetime import timedelta

from core import importer
from core.analyzer import analyze
from core.classifier import build_inventory
from core.drafts import MAX_DRAFTS, generate_draft, select_draft_targets
from db import category_scores, drafts as drafts_col, file_assets, issues as issues_col, scans, utcnow
from settings_store import get_settings, resolve_llm_credentials

log = logging.getLogger("bloatguardian.scanner")

STAGES = [
    ("importing", "Importing"),
    ("extracting", "Extracting file tree"),
    ("classifying", "Classifying files"),
    ("estimating", "Estimating tokens or credits"),
    ("adversary", "Running adversary scan"),
    ("drafting", "Drafting recommendations"),
    ("reports", "Building reports"),
]

CONTENT_RETENTION_DAYS = 7
METADATA_RETENTION_DAYS = 30
KEEP_RECENT_SCANS = 10

IMPORT_ERROR_CODES = {
    "GitHubRepoUnavailable", "GitHubRateLimited", "RepoTooLarge", "BranchNotFound",
    "ZipCorrupted", "ZipTooLarge", "BitbucketRepoUnavailable", "BitbucketRateLimited",
    "ImportFailed", "ArchiveNotFound", "RateLimited",
}


def initial_progress() -> dict:
    return {
        "stages": [{"key": k, "label": label, "status": "pending", "detail": ""} for k, label in STAGES],
        "current_stage": None,
        "percent": 0,
    }


def empty_kpis() -> dict:
    return {
        "files_discovered": 0, "files_parsed": 0, "files_skipped": 0,
        "agent_like_files": 0, "tokens_analyzed": 0,
    }


async def _set_stage(scan_id: str, key: str, status: str, detail: str = "", kpis: dict | None = None):
    scan = await scans.find_one({"id": scan_id})
    if not scan:
        return
    progress = scan.get("progress") or initial_progress()
    stages = progress["stages"]
    for i, st in enumerate(stages):
        if st["key"] == key:
            st["status"] = status
            st["detail"] = detail
            if status == "running":
                st["started_at"] = utcnow().isoformat()
                for prev in stages[:i]:
                    if prev["status"] in ("pending", "running"):
                        prev["status"] = "done"
            if status in ("done", "failed"):
                st["completed_at"] = utcnow().isoformat()
    done = sum(1 for st in stages if st["status"] == "done")
    running = 1 if any(st["status"] == "running" for st in stages) else 0
    progress["current_stage"] = key
    progress["percent"] = int(round((done + running * 0.5) / len(stages) * 100))
    update = {"progress": progress, "updated_at": utcnow()}
    if kpis:
        update["kpis"] = kpis
    await scans.update_one({"id": scan_id}, {"$set": update})


async def _fail(scan_id: str, status: str, code: str, message: str, retry_after: int | None = None,
               stage_key: str = "importing"):
    await _set_stage(scan_id, stage_key, "failed", message)
    await scans.update_one({"id": scan_id}, {"$set": {
        "status": status,
        "error_code": code,
        "error_message": message,
        "retry_after_minutes": retry_after,
        "completed_at": utcnow(),
        "updated_at": utcnow(),
    }})
    log.warning("scan %s failed: %s %s", scan_id, code, message)


def _do_import(spec: dict, work_dir: str, settings: dict):
    source = spec["source_type"]
    if source == "github":
        return importer.import_github(
            spec["repo_url"], spec.get("branch"), work_dir,
            token=(settings.get("github_token") or None))
    if source == "bitbucket":
        return importer.import_bitbucket(
            spec["repo_url"], spec.get("branch"), work_dir,
            token=(settings.get("bitbucket_token") or None))
    if source == "zip":
        return importer.import_zip(spec["zip_path"], work_dir, display_name=spec.get("repo_name"))
    if source == "md":
        files = [(name, open(path, "rb").read()) for name, path in spec["md_files"]]
        return importer.import_markdown_files(files, work_dir, display_name=spec.get("repo_name"))
    raise importer.ImportError_("ImportFailed", f"Unknown source type '{source}'")


async def run_scan(scan_id: str, spec: dict):
    settings = await get_settings()
    work_dir = spec["work_dir"]
    try:
        await scans.update_one({"id": scan_id}, {"$set": {"status": "running", "updated_at": utcnow()}})

        # ---------------------------------------------------------- import
        await _set_stage(scan_id, "importing", "running", "Fetching repository content")
        try:
            imported = await asyncio.to_thread(_do_import, spec, work_dir, settings)
        except importer.ImportError_ as exc:
            code = exc.code if exc.code in IMPORT_ERROR_CODES else "ImportFailed"
            await _fail(scan_id, "ImportFailed", code, exc.message, exc.retry_after_minutes)
            return
        except Exception as exc:  # noqa: BLE001
            await _fail(scan_id, "ImportFailed", "ImportFailed", f"Import failed: {exc}")
            return

        await scans.update_one({"id": scan_id}, {"$set": {
            "repo_name": imported.repo_name,
            "repo_owner": imported.repo_owner,
            "branch": imported.branch,
            "archive_bytes": imported.archive_bytes,
            "workspace_dir": imported.root_dir,
            "content_expires_at": utcnow() + timedelta(days=CONTENT_RETENTION_DAYS),
            "metadata_expires_at": utcnow() + timedelta(days=METADATA_RETENTION_DAYS),
            "updated_at": utcnow(),
        }})
        await _set_stage(scan_id, "importing", "done",
                         f"{imported.source_type} import complete"
                         + (f" ({imported.archive_bytes / 1048576:.1f} MB archive)" if imported.archive_bytes else ""))

        # ------------------------------------------------- extract + classify
        await _set_stage(scan_id, "extracting", "running", "Walking the repository tree")
        inv = await asyncio.to_thread(build_inventory, imported.root_dir)
        kpis = {
            "files_discovered": inv.total_files,
            "files_parsed": inv.parsed_files,
            "files_skipped": inv.skipped_files,
            "agent_like_files": sum(1 for f in inv.files if f.agent_like),
            "tokens_analyzed": inv.analyzed_tokens,
        }
        await _set_stage(scan_id, "extracting", "done", f"{inv.total_files} files discovered", kpis)
        await _set_stage(scan_id, "classifying", "running", "Grouping agent, skill, context and source files")
        await asyncio.sleep(0)
        await _set_stage(scan_id, "classifying", "done",
                         f"{kpis['agent_like_files']} agent-like files classified", kpis)
        await _set_stage(scan_id, "estimating", "running", "Estimating tokens with ceil(chars / 4)")
        await _set_stage(scan_id, "estimating", "done",
                         f"{inv.analyzed_tokens:,} tokens estimated across {inv.parsed_files} parsed files", kpis)

        if inv.total_files == 0:
            await _fail(scan_id, "ParseFailed", "ParseFailed",
                        "No files were found inside the imported archive.", stage_key="extracting")
            return

        # ------------------------------------------------------ adversary scan
        await _set_stage(scan_id, "adversary", "running", "Looking for duplication, bloat and review overhead")
        analysis = await asyncio.to_thread(analyze, inv, settings["assumptions"])
        await _set_stage(scan_id, "adversary", "done",
                         f"{len(analysis['issues'])} issues found", kpis)

        # -------------------------------------------------- persist inventory
        docs = []
        for i, f in enumerate(inv.files):
            d = f.to_public()
            d["id"] = f"FIL-{scan_id}-{i + 1:05d}"
            d["scan_id"] = scan_id
            docs.append(d)
        if docs:
            await file_assets.delete_many({"scan_id": scan_id})
            for chunk in range(0, len(docs), 500):
                await file_assets.insert_many(docs[chunk:chunk + 500])

        await issues_col.delete_many({"scan_id": scan_id})
        if analysis["issues"]:
            await issues_col.insert_many([{**i, "scan_id": scan_id} for i in analysis["issues"]])
        await category_scores.delete_many({"scan_id": scan_id})
        if analysis["category_scores"]:
            await category_scores.insert_many([
                {**c, "scan_id": scan_id, "id": f"CAT-{scan_id}-{c['category']}"}
                for c in analysis["category_scores"]
            ])

        insufficient = analysis["insufficient_data"]
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
        if insufficient:
            warnings.append(
                f"Only {inv.parsed_files} text files could be parsed. At least 5 are needed, so savings "
                "were not calculated."
            )

        candidates = select_draft_targets(inv.files, analysis, limit=MAX_DRAFTS)
        candidate_meta = [{k: v for k, v in c.items() if k != "content"} for c in candidates]

        await scans.update_one({"id": scan_id}, {"$set": {
            "total_files": inv.total_files,
            "parsed_files": inv.parsed_files,
            "skipped_files": inv.skipped_files,
            "analyzed_tokens": inv.analyzed_tokens,
            "overall_score": analysis["overall_score"],
            "verdict": analysis["verdict"],
            "partial_scan": analysis["partial_scan"],
            "skip_ratio": analysis["skip_ratio"],
            "kpis": kpis,
            "warnings": warnings,
            "detections": analysis["detections"],
            "assumptions": analysis["assumptions"],
            "penalty_ledger": analysis["penalty_ledger"],
            "top_drivers": analysis["top_drivers"],
            "recommended_actions": analysis["recommended_actions"],
            "clusters": analysis["clusters"],
            "overlap_groups": analysis["overlap_groups"],
            "issue_count": len(analysis["issues"]),
            "draft_candidates": candidate_meta,
            "updated_at": utcnow(),
            **analysis["savings"],
        }})

        if insufficient:
            await _set_stage(scan_id, "drafting", "skipped", "Not enough text files to draft rewrites")
            await _set_stage(scan_id, "reports", "done", "Report ready with limited data")
            await scans.update_one({"id": scan_id}, {"$set": {
                "status": "InsufficientData",
                "error_code": "InsufficientData",
                "error_message": (
                    f"Only {inv.parsed_files} text files were parsed. A scan needs at least 5 parsed "
                    "text files before we can score it or estimate savings."
                ),
                "completed_at": utcnow(),
                "draft_status": "skipped",
                "updated_at": utcnow(),
            }})
            return

        # ------------------------------------------------------------ drafts
        await _set_stage(scan_id, "drafting", "running", "Rewriting your agent files with the model")
        await drafts_col.delete_many({"scan_id": scan_id})
        auto_count = int(settings.get("auto_draft_count") or 0)
        made, draft_errors = 0, []
        if auto_count > 0 and candidates:
            try:
                api_key, provider, model, key_source = resolve_llm_credentials(settings)
            except RuntimeError as exc:
                draft_errors.append(str(exc))
                api_key = None
            if api_key:
                for idx, target in enumerate(candidates[:auto_count]):
                    try:
                        d = await asyncio.wait_for(
                            generate_draft(target, imported.repo_name, api_key, provider, model,
                                           session_id=f"{scan_id}-{idx}"),
                            timeout=300,
                        )
                        d.update({
                            "id": f"DRF-{scan_id}-{idx + 1:03d}",
                            "scan_id": scan_id,
                            "created_at": utcnow(),
                            "key_source": key_source,
                        })
                        await drafts_col.insert_one(dict(d))
                        made += 1
                        await _set_stage(scan_id, "drafting", "running",
                                         f"{made} of {min(auto_count, len(candidates))} drafts written")
                    except Exception as exc:  # noqa: BLE001
                        text = str(exc).lower()
                        if any(m in text for m in ("spend limit", "quota", "billing", "credit balance")):
                            draft_errors.append(
                                "The language model budget has run out, so drafts were not written. "
                                "Top up your Universal Key balance or add your own key in Settings, "
                                "then use Generate on any eligible file."
                            )
                            break
                        log.exception("draft failed for %s", target["source_path"])
                        draft_errors.append(f"{target['target_filename']}: {exc}")
        detail = f"{made} draft file(s) written" if made else "No drafts were generated"
        await _set_stage(scan_id, "drafting", "done" if made or not draft_errors else "failed", detail)

        # ----------------------------------------------------------- reports
        await _set_stage(scan_id, "reports", "running", "Assembling report sections")
        await _set_stage(scan_id, "reports", "done", "Report ready")
        await scans.update_one({"id": scan_id}, {"$set": {
            "status": "completed",
            "completed_at": utcnow(),
            "draft_count": made,
            "draft_status": "completed" if made else ("failed" if draft_errors else "none"),
            "draft_errors": draft_errors[:10],
            "updated_at": utcnow(),
        }})
        log.info("scan %s completed score=%s verdict=%s", scan_id, analysis["overall_score"], analysis["verdict"])
    except Exception as exc:  # noqa: BLE001
        log.exception("scan %s crashed", scan_id)
        await _fail(scan_id, "ParseFailed", "ParseFailed", f"The scan could not be completed: {exc}",
                    stage_key="adversary")
    finally:
        for name, path in (spec.get("cleanup") or []):
            try:
                os.remove(path)
            except OSError:
                pass


# ------------------------------------------------------- on demand drafting
async def generate_single_draft(scan_id: str, source_path: str) -> dict:
    scan = await scans.find_one({"id": scan_id})
    if not scan:
        raise ValueError("Scan not found")
    candidates = scan.get("draft_candidates") or []
    target = next((c for c in candidates if c["source_path"] == source_path), None)
    if not target:
        raise ValueError("That file is not eligible for a draft rewrite")
    existing_count = await drafts_col.count_documents({"scan_id": scan_id})
    if existing_count >= MAX_DRAFTS:
        raise ValueError(f"This scan already has the maximum of {MAX_DRAFTS} draft files")
    root = scan.get("workspace_dir")
    full = os.path.join(root or "", source_path)
    if not root or not os.path.isfile(full):
        raise ValueError(
            "The imported repository content has expired (kept for 7 days). Re-run the scan to "
            "generate more drafts."
        )
    with open(full, encoding="utf-8", errors="replace") as fh:
        content = fh.read()
    settings = await get_settings()
    api_key, provider, model, key_source = resolve_llm_credentials(settings)
    d = await asyncio.wait_for(
        generate_draft({**target, "content": content}, scan.get("repo_name") or "repository",
                       api_key, provider, model, session_id=f"{scan_id}-ondemand-{existing_count}"),
        timeout=300,
    )
    d.update({
        "id": f"DRF-{scan_id}-{existing_count + 1:03d}",
        "scan_id": scan_id,
        "created_at": utcnow(),
        "key_source": key_source,
    })
    await drafts_col.delete_many({"scan_id": scan_id, "source_path": source_path})
    await drafts_col.insert_one(dict(d))
    total = await drafts_col.count_documents({"scan_id": scan_id})
    await scans.update_one({"id": scan_id}, {"$set": {
        "draft_count": total, "draft_status": "completed", "updated_at": utcnow()}})
    return d


# ------------------------------------------------------------- retention
async def enforce_retention():
    """7 day raw content retention, 30 day metadata retention, keep last 10 real scans."""
    now = utcnow()
    removed_content, removed_scans = 0, 0
    async for scan in scans.find({"workspace_dir": {"$ne": None}}):
        expires = scan.get("content_expires_at")
        if expires and expires.replace(tzinfo=expires.tzinfo or now.tzinfo) < now:
            path = scan.get("workspace_dir")
            if path:
                parent = os.path.dirname(path)
                shutil.rmtree(parent if os.path.basename(parent).startswith("scan-") else path,
                              ignore_errors=True)
            await scans.update_one({"id": scan["id"]}, {"$set": {"workspace_dir": None}})
            removed_content += 1

    stale = scans.find({"is_seed": {"$ne": True}, "metadata_expires_at": {"$lt": now}})
    async for scan in stale:
        await delete_scan(scan["id"])
        removed_scans += 1

    keep_ids = [s["id"] async for s in scans.find({"is_seed": {"$ne": True}})
                .sort("created_at", -1).limit(KEEP_RECENT_SCANS)]
    async for scan in scans.find({"is_seed": {"$ne": True}, "id": {"$nin": keep_ids}}):
        await delete_scan(scan["id"])
        removed_scans += 1
    return {"content_purged": removed_content, "scans_purged": removed_scans}


async def delete_scan(scan_id: str) -> bool:
    scan = await scans.find_one({"id": scan_id})
    if not scan:
        return False
    path = scan.get("workspace_dir")
    if path:
        parent = os.path.dirname(path)
        shutil.rmtree(parent if os.path.basename(parent).startswith("scan-") else path, ignore_errors=True)
    await file_assets.delete_many({"scan_id": scan_id})
    await issues_col.delete_many({"scan_id": scan_id})
    await category_scores.delete_many({"scan_id": scan_id})
    await drafts_col.delete_many({"scan_id": scan_id})
    await scans.delete_one({"id": scan_id})
    return True
