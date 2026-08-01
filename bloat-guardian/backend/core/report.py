"""Assemble the canonical report payload shared by the API and every exporter."""
from __future__ import annotations

from .config import INVENTORY_GROUPS


def inventory_summary(files: list) -> dict:
    out = {}
    for group in INVENTORY_GROUPS:
        out[group] = {"count": 0, "parsed": 0, "skipped": 0, "tokens": 0}
    for f in files:
        group = f.get("inventory_group") or "Other text assets"
        bucket = out.setdefault(group, {"count": 0, "parsed": 0, "skipped": 0, "tokens": 0})
        bucket["count"] += 1
        if f.get("parse_status") == "Scanned":
            bucket["parsed"] += 1
            bucket["tokens"] += int(f.get("estimated_tokens") or 0)
        else:
            bucket["skipped"] += 1
    return {k: v for k, v in out.items() if v["count"] > 0}


def build_payload(scan: dict, files: list, analysis: dict, drafts: list | None = None,
                  warnings: list | None = None) -> dict:
    return {
        "scan": scan,
        "files": files,
        "category_scores": analysis.get("category_scores", []),
        "issues": analysis.get("issues", []),
        "top_drivers": analysis.get("top_drivers", []),
        "recommended_actions": analysis.get("recommended_actions", []),
        "penalty_ledger": analysis.get("penalty_ledger", []),
        "assumptions": analysis.get("assumptions", {}),
        "detections": analysis.get("detections", {}),
        "clusters": analysis.get("clusters", []),
        "overlap_groups": analysis.get("overlap_groups", []),
        "drafts": drafts or [],
        "warnings": warnings or [],
        "inventory_summary": inventory_summary(files),
    }
