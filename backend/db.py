"""Mongo access layer."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from typing import Any, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL: str = os.environ["MONGO_URL"]
DB_NAME: str = os.environ.get("DB_NAME", "bloat_guardian")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

scans = db.scans
repo_series = db.repo_series
file_assets = db.file_assets
issues = db.issues
category_scores = db.category_scores
drafts = db.recommendation_drafts
export_jobs = db.export_jobs
app_settings = db.app_settings
users = db.users

DEMO_USER_ID: str = "USR-DEMO-0001"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def serialize(doc: Any) -> Any:
    """Recursively make a Mongo document JSON-safe."""
    if doc is None:
        return None
    if isinstance(doc, list):
        return [serialize(d) for d in doc]
    if isinstance(doc, dict):
        return {k: serialize(v) for k, v in doc.items() if k != "_id"}
    if isinstance(doc, datetime):
        if doc.tzinfo is None:
            doc = doc.replace(tzinfo=timezone.utc)
        return doc.isoformat()
    return doc


async def ensure_indexes() -> None:
    await scans.create_index("id", unique=True)
    await scans.create_index([("created_at", -1)])
    await scans.create_index("series_id")
    await repo_series.create_index("id", unique=True)
    await repo_series.create_index("key", unique=True)
    await repo_series.create_index("archived")
    await file_assets.create_index("scan_id")
    await file_assets.create_index([("scan_id", 1), ("estimated_tokens", -1)])
    await issues.create_index("scan_id")
    await category_scores.create_index("scan_id")
    await drafts.create_index("scan_id")
    # Draft ids must be unique. Created defensively: if legacy duplicates exist the index is
    # skipped rather than failing startup.
    try:
        await drafts.create_index("id", unique=True, name="draft_id_unique")
    except Exception:  # noqa: BLE001
        pass
    await export_jobs.create_index("scan_id")
    await users.create_index("id", unique=True)


async def ensure_demo_user() -> Optional[dict]:
    existing = await users.find_one({"id": DEMO_USER_ID})
    if not existing:
        await users.insert_one({
            "id": DEMO_USER_ID,
            "display_name": "Demo Builder",
            "created_at": utcnow(),
        })
    return await users.find_one({"id": DEMO_USER_ID})


async def next_scan_id(when: datetime | None = None) -> str:
    when = when or utcnow()
    prefix = f"SCN-{when.strftime('%Y-%m-%d')}-"
    count = await scans.count_documents({"id": {"$regex": f"^{prefix}"}})
    for i in range(count + 1, count + 500):
        candidate = f"{prefix}{i:04d}"
        if not await scans.find_one({"id": candidate}):
            return candidate
    return f"{prefix}{count + 1:04d}"


async def next_draft_id(scan_id: str) -> str:
    """First unused draft id for a scan.

    Counting existing drafts is not safe: a failed auto-draft leaves a gap in the sequence, so
    "count + 1" can collide with an id that is already taken.
    """
    prefix = f"DRF-{scan_id}-"
    used = {d["id"] async for d in drafts.find({"scan_id": scan_id}, {"id": 1})}
    for i in range(1, 1000):
        candidate = f"{prefix}{i:03d}"
        if candidate not in used:
            return candidate
    return f"{prefix}{uuid.uuid4().hex[:8]}"
