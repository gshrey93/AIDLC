"""RepoSeries: one row per repository + branch, with scans attached as runs.

A series is keyed on ``source_type + owner + repo_name + branch`` so that, for example,
``github/acme/app@main`` and ``github/acme/app@develop`` are two independent series.
Zip and markdown uploads have no owner or branch, so they key on the uploaded name.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from db import repo_series, scans, utcnow

log = logging.getLogger("bloatguardian.series")

RUN_FIELDS = {
    "id": 1, "status": 1, "source_type": 1, "repo_name": 1, "repo_owner": 1, "branch": 1,
    "overall_score": 1, "verdict": 1, "partial_scan": 1, "parsed_files": 1, "total_files": 1,
    "skipped_files": 1, "estimated_monthly_credit_waste": 1, "estimated_monthly_token_waste": 1,
    "estimated_monthly_dollar_waste": 1, "issue_count": 1, "draft_count": 1, "is_seed": 1,
    "created_at": 1, "completed_at": 1, "run_number": 1, "score_delta": 1, "previous_score": 1,
    "error_code": 1, "error_message": 1, "series_id": 1, "analyzed_tokens": 1,
}


def _norm(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip().lower()


def series_key(source_type: str, repo_owner: str | None, repo_name: str | None,
               branch: str | None) -> str:
    """Stable identity for a series. Branch-aware: main and develop are separate series."""
    return "|".join([
        _norm(source_type) or "unknown",
        _norm(repo_owner),
        _norm(repo_name) or "unnamed",
        _norm(branch) or "-",
    ])


def display_name(source_type: str, repo_owner: str | None, repo_name: str | None) -> str:
    name = (repo_name or "unnamed").strip()
    if repo_owner:
        return f"{repo_owner.strip()}/{name}"
    return name


def new_series_id() -> str:
    return f"SER-{uuid.uuid4().hex[:12].upper()}"


async def get_or_create_series(source_type: str, repo_owner: str | None, repo_name: str | None,
                               branch: str | None, *, is_seed: bool = False) -> dict:
    key = series_key(source_type, repo_owner, repo_name, branch)
    existing = await repo_series.find_one({"key": key})
    if existing:
        return existing
    now = utcnow()
    doc = {
        "id": new_series_id(),
        "key": key,
        "source_type": (source_type or "unknown").strip().lower(),
        "repo_owner": (repo_owner or None),
        "repo_name": (repo_name or "unnamed"),
        "branch": (branch or None),
        "display_name": display_name(source_type, repo_owner, repo_name),
        # Seeded demo series start life in the archive so the user's own work leads the page.
        "archived": bool(is_seed),
        "is_seed": bool(is_seed),
        "run_count": 0,
        "latest_scan_id": None,
        "latest_status": None,
        "latest_score": None,
        "latest_verdict": None,
        "latest_run_at": None,
        "previous_score": None,
        "score_delta": None,
        "best_score": None,
        "first_run_at": None,
        "created_at": now,
        "updated_at": now,
        "archived_at": now if is_seed else None,
    }
    try:
        await repo_series.insert_one(dict(doc))
    except Exception:  # noqa: BLE001 - concurrent create, fall back to the winner
        found = await repo_series.find_one({"key": key})
        if found:
            return found
        raise
    return await repo_series.find_one({"key": key})


async def recompute_series(series_id: str) -> Optional[dict]:
    """Renumber the runs of a series and refresh its rolled-up columns.

    Deletes the series when it has no runs left.
    """
    series = await repo_series.find_one({"id": series_id})
    if not series:
        return None
    runs = await scans.find({"series_id": series_id}, RUN_FIELDS).sort("created_at", 1).to_list(2000)
    if not runs:
        await repo_series.delete_one({"id": series_id})
        return None

    prev_completed_score: int | None = None
    completed_scores: list[int] = []
    latest_completed: dict | None = None
    for index, run in enumerate(runs):
        update: dict = {"run_number": index + 1}
        if run.get("status") == "completed":
            score = int(run.get("overall_score") or 0)
            update["previous_score"] = prev_completed_score
            update["score_delta"] = (
                score - prev_completed_score if prev_completed_score is not None else None
            )
            prev_completed_score = score
            completed_scores.append(score)
            latest_completed = {**run, **update, "overall_score": score}
        else:
            update["previous_score"] = None
            update["score_delta"] = None
        await scans.update_one({"id": run["id"]}, {"$set": update})

    latest = runs[-1]
    patch = {
        "run_count": len(runs),
        "latest_scan_id": latest["id"],
        "latest_status": latest.get("status"),
        "latest_run_at": latest.get("created_at"),
        "first_run_at": runs[0].get("created_at"),
        "latest_score": latest_completed.get("overall_score") if latest_completed else None,
        "latest_verdict": latest_completed.get("verdict") if latest_completed else None,
        "latest_completed_scan_id": latest_completed["id"] if latest_completed else None,
        "previous_score": latest_completed.get("previous_score") if latest_completed else None,
        "score_delta": latest_completed.get("score_delta") if latest_completed else None,
        "best_score": max(completed_scores) if completed_scores else None,
        "completed_run_count": len(completed_scores),
        "is_seed": all(bool(r.get("is_seed")) for r in runs),
        "source_type": latest.get("source_type") or series.get("source_type"),
        "updated_at": utcnow(),
    }
    await repo_series.update_one({"id": series_id}, {"$set": patch})
    return await repo_series.find_one({"id": series_id})


async def attach_scan(scan_id: str, source_type: str, repo_owner: str | None,
                      repo_name: str | None, branch: str | None,
                      *, is_seed: bool = False) -> Optional[dict]:
    """Bind a scan to its series, moving it if the resolved identity changed."""
    scan = await scans.find_one({"id": scan_id}, {"series_id": 1, "is_seed": 1})
    if not scan:
        return None
    seed = bool(is_seed or scan.get("is_seed"))
    series = await get_or_create_series(source_type, repo_owner, repo_name, branch, is_seed=seed)
    old_id = scan.get("series_id")
    if old_id == series["id"]:
        return await recompute_series(series["id"])
    await scans.update_one({"id": scan_id}, {"$set": {
        "series_id": series["id"], "series_key": series["key"], "updated_at": utcnow(),
    }})
    if old_id:
        await recompute_series(old_id)
    return await recompute_series(series["id"])


async def set_archived(series_id: str, archived: bool) -> Optional[dict]:
    series = await repo_series.find_one({"id": series_id})
    if not series:
        return None
    await repo_series.update_one({"id": series_id}, {"$set": {
        "archived": bool(archived),
        "archived_at": utcnow() if archived else None,
        "updated_at": utcnow(),
    }})
    return await repo_series.find_one({"id": series_id})


async def list_series(include_archived: bool = True) -> dict:
    query: dict = {} if include_archived else {"archived": {"$ne": True}}
    docs = await repo_series.find(query).to_list(1000)
    ids = [d["id"] for d in docs]
    runs = await scans.find({"series_id": {"$in": ids}}, RUN_FIELDS).sort("created_at", -1).to_list(5000)
    grouped: dict[str, list] = {i: [] for i in ids}
    for run in runs:
        grouped.setdefault(run["series_id"], []).append(run)
    out = []
    for doc in docs:
        doc = dict(doc)
        doc.pop("_id", None)
        doc["runs"] = grouped.get(doc["id"], [])
        out.append(doc)

    def sort_key(s: dict):
        latest = s.get("latest_run_at")
        return (latest is not None, latest)

    out.sort(key=sort_key, reverse=True)
    return {
        "series": out,
        "counts": {
            "total": len(out),
            "active": sum(1 for s in out if not s.get("archived")),
            "archived": sum(1 for s in out if s.get("archived")),
            "runs": len(runs),
        },
    }


async def archived_series(with_runs: bool = False) -> list:
    docs = await repo_series.find({"archived": True}).to_list(1000)
    docs.sort(key=lambda d: (d.get("latest_run_at") is not None, d.get("latest_run_at")), reverse=True)
    if with_runs:
        for doc in docs:
            doc["runs"] = await scans.find(
                {"series_id": doc["id"]}, RUN_FIELDS).sort("created_at", -1).to_list(500)
    return docs


async def backfill() -> dict:
    """Give every scan that predates the series model a home. Idempotent."""
    attached = 0
    async for scan in scans.find(
        {"$or": [{"series_id": {"$exists": False}}, {"series_id": None}]},
        {"id": 1, "source_type": 1, "repo_owner": 1, "repo_name": 1, "branch": 1, "is_seed": 1},
    ):
        await attach_scan(
            scan["id"], scan.get("source_type") or "unknown", scan.get("repo_owner"),
            scan.get("repo_name"), scan.get("branch"), is_seed=bool(scan.get("is_seed")),
        )
        attached += 1
    # Re-roll every series so the aggregate columns are always trustworthy after a migration.
    async for series in repo_series.find({}, {"id": 1}):
        await recompute_series(series["id"])
    total_series = await repo_series.count_documents({})
    result = {
        "scans_attached": attached,
        "series_total": total_series,
        "series_archived": await repo_series.count_documents({"archived": True}),
    }
    if attached:
        log.info("series backfill: %s", result)
    return result
