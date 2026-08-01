"""Mongo access layer with hybrid live Mongo + in-memory fallback."""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

log = logging.getLogger("bloatguardian.db")

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL: str = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")
DB_NAME: str = os.environ.get("DB_NAME", "bloat_guardian")

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


class InMemoryCollection:
    def __init__(self, name: str):
        self.name = name
        self.docs: list[dict] = []

    async def create_index(self, *args, **kwargs):
        pass

    async def insert_one(self, doc: dict):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = str(uuid.uuid4())
        self.docs.append(d)

        class Res:
            inserted_id = d["_id"]
        return Res()

    async def insert_many(self, docs: list[dict]):
        res_ids = []
        for doc in docs:
            r = await self.insert_one(doc)
            res_ids.append(r.inserted_id)

        class Res:
            inserted_ids = res_ids
        return Res()

    def _matches(self, doc: dict, query: dict) -> bool:
        if not query:
            return True
        for k, v in query.items():
            if k == "$or":
                if not any(self._matches(doc, q) for q in v):
                    return False
                continue
            if k == "$and":
                if not all(self._matches(doc, q) for q in v):
                    return False
                continue
            val = doc.get(k)
            if isinstance(v, dict):
                if "$in" in v and val not in v["$in"]:
                    return False
                if "$nin" in v and val in v["$nin"]:
                    return False
                if "$ne" in v and val == v["$ne"]:
                    return False
                if "$regex" in v:
                    pattern = v["$regex"]
                    if not re.search(pattern, str(val or "")):
                        return False
                if "$gt" in v and not (val is not None and val > v["$gt"]):
                    return False
                if "$gte" in v and not (val is not None and val >= v["$gte"]):
                    return False
                if "$lt" in v and not (val is not None and val < v["$lt"]):
                    return False
                if "$lte" in v and not (val is not None and val <= v["$lte"]):
                    return False
            elif val != v:
                return False
        return True

    async def find_one(self, filter: dict = None, projection: dict = None):
        res = await self.to_list_internal(filter, projection, limit=1)
        return res[0] if res else None

    async def to_list_internal(self, filter: dict = None, projection: dict = None, limit: int = None):
        filter = filter or {}
        items = [dict(d) for d in self.docs if self._matches(d, filter)]
        if limit is not None:
            items = items[:limit]
        if projection:
            keys = [k for k, v in projection.items() if v]
            if keys:
                items = [{k: v for k, v in d.items() if k in keys or k == "_id"} for d in items]
        return items

    def find(self, filter: dict = None, projection: dict = None):
        filter = filter or {}
        matched = [dict(d) for d in self.docs if self._matches(d, filter)]

        class Cursor:
            def __init__(self, items):
                self._items = items
                self._sort_key = None
                self._sort_dir = 1
                self._skip = 0
                self._limit = None

            def sort(self, key_or_list, direction=1):
                if isinstance(key_or_list, list):
                    self._sort_key = key_or_list[0][0]
                    self._sort_dir = key_or_list[0][1]
                else:
                    self._sort_key = key_or_list
                    self._sort_dir = direction
                return self

            def skip(self, n):
                self._skip = n
                return self

            def limit(self, n):
                self._limit = n
                return self

            async def to_list(self, length=None):
                items = list(self._items)
                if self._sort_key:
                    items.sort(key=lambda x: x.get(self._sort_key) or "", reverse=(self._sort_dir < 0))
                if self._skip:
                    items = items[self._skip:]
                if self._limit is not None:
                    items = items[:self._limit]
                elif length is not None:
                    items = items[:length]
                if projection:
                    keys = [k for k, v in projection.items() if v]
                    if keys:
                        items = [{k: v for k, v in d.items() if k in keys or k == "_id"} for d in items]
                return items

            def __aiter__(self):
                self._index = 0
                self._prepared = None
                return self

            async def __anext__(self):
                if self._prepared is None:
                    self._prepared = await self.to_list(length=None)
                if self._index < len(self._prepared):
                    item = self._prepared[self._index]
                    self._index += 1
                    return item
                raise StopAsyncIteration

        return Cursor(matched)

    async def count_documents(self, filter: dict = None):
        matched = await self.to_list_internal(filter)
        return len(matched)

    async def update_one(self, filter: dict, update: dict, upsert: bool = False):
        doc = await self.find_one(filter)
        if not doc and upsert:
            doc = dict(filter)
            if "_id" not in doc:
                doc["_id"] = str(uuid.uuid4())
            self.docs.append(doc)
        if doc:
            # find index in self.docs
            for target in self.docs:
                if target.get("_id") == doc.get("_id"):
                    if "$set" in update:
                        target.update(update["$set"])
                    if "$inc" in update:
                        for k, v in update["$inc"].items():
                            target[k] = target.get(k, 0) + v
                    break

        class Res:
            matched_count = 1 if doc else 0
            modified_count = 1 if doc else 0
        return Res()

    async def update_many(self, filter: dict, update: dict):
        matched = [d for d in self.docs if self._matches(d, filter or {})]
        for doc in matched:
            if "$set" in update:
                doc.update(update["$set"])
            if "$inc" in update:
                for k, v in update["$inc"].items():
                    doc[k] = doc.get(k, 0) + v

        class Res:
            matched_count = len(matched)
            modified_count = len(matched)
        return Res()

    async def delete_one(self, filter: dict):
        doc = await self.find_one(filter)
        if doc:
            self.docs = [d for d in self.docs if d.get("_id") != doc.get("_id")]

        class Res:
            deleted_count = 1 if doc else 0
        return Res()

    async def delete_many(self, filter: dict):
        matched_ids = {d.get("_id") for d in self.docs if self._matches(d, filter or {})}
        self.docs = [d for d in self.docs if d.get("_id") not in matched_ids]

        class Res:
            deleted_count = len(matched_ids)
        return Res()


class HybridCollection:
    global_fallback = False

    def __init__(self, real_col, name: str):
        self.real_col = real_col
        self.name = name
        self.fallback = InMemoryCollection(name)

    @property
    def is_fallback(self) -> bool:
        return HybridCollection.global_fallback

    async def _exec(self, method_name: str, *args, **kwargs):
        if not HybridCollection.global_fallback:
            try:
                real_method = getattr(self.real_col, method_name)
                return await real_method(*args, **kwargs)
            except Exception as exc:
                log.warning("MongoDB method %s failed (%s), switching to in-memory fallback for all collections", method_name, exc)
                HybridCollection.global_fallback = True
        fb_method = getattr(self.fallback, method_name)
        return await fb_method(*args, **kwargs)

    async def create_index(self, *args, **kwargs):
        return await self._exec("create_index", *args, **kwargs)

    async def insert_one(self, doc: dict):
        return await self._exec("insert_one", doc)

    async def insert_many(self, docs: list[dict]):
        return await self._exec("insert_many", docs)

    async def find_one(self, filter: dict = None, projection: dict = None):
        return await self._exec("find_one", filter, projection)

    def find(self, filter: dict = None, projection: dict = None):
        if not HybridCollection.global_fallback:
            try:
                return self.real_col.find(filter, projection)
            except Exception:
                HybridCollection.global_fallback = True
        return self.fallback.find(filter, projection)

    async def count_documents(self, filter: dict = None):
        return await self._exec("count_documents", filter)

    async def update_one(self, filter: dict, update: dict, upsert: bool = False):
        return await self._exec("update_one", filter, update, upsert=upsert)

    async def update_many(self, filter: dict, update: dict):
        return await self._exec("update_many", filter, update)

    async def delete_one(self, filter: dict):
        return await self._exec("delete_one", filter)

    async def delete_many(self, filter: dict):
        return await self._exec("delete_many", filter)


client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=2000)
db = client[DB_NAME]

scans = HybridCollection(db.scans, "scans")
repo_series = HybridCollection(db.repo_series, "repo_series")
file_assets = HybridCollection(db.file_assets, "file_assets")
issues = HybridCollection(db.issues, "issues")
category_scores = HybridCollection(db.category_scores, "category_scores")
drafts = HybridCollection(db.recommendation_drafts, "recommendation_drafts")
export_jobs = HybridCollection(db.export_jobs, "export_jobs")
app_settings = HybridCollection(db.app_settings, "app_settings")
users = HybridCollection(db.users, "users")


async def ensure_indexes() -> None:
    try:
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
        try:
            await drafts.create_index("id", unique=True, name="draft_id_unique")
        except Exception:
            pass
        await export_jobs.create_index("scan_id")
        await users.create_index("id", unique=True)
    except Exception as exc:
        log.warning("Index creation skipped: %s", exc)


async def ensure_demo_user() -> Optional[dict]:
    try:
        existing = await users.find_one({"id": DEMO_USER_ID})
        if not existing:
            await users.insert_one({
                "id": DEMO_USER_ID,
                "display_name": "Demo Builder",
                "created_at": utcnow(),
            })
        return await users.find_one({"id": DEMO_USER_ID})
    except Exception as exc:
        log.warning("Demo user creation fallback: %s", exc)
        return {"id": DEMO_USER_ID, "display_name": "Demo Builder"}


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
    prefix = f"DRF-{scan_id}-"
    used = set()
    try:
        async for d in drafts.find({"scan_id": scan_id}, {"id": 1}):
            used.add(d["id"])
    except Exception:
        docs = await drafts.find({"scan_id": scan_id}).to_list(length=None)
        used = {d["id"] for d in docs if "id" in d}
    for i in range(1, 1000):
        candidate = f"{prefix}{i:03d}"
        if candidate not in used:
            return candidate
    return f"{prefix}{uuid.uuid4().hex[:8]}"
