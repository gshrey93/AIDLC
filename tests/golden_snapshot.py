"""Golden snapshot harness.

Captures a precise behavioural fingerprint of the analysis and export layers so that pure
refactors can be proven not to change any output.

    python tests/golden_snapshot.py --write   # record the fingerprint (run BEFORE refactoring)
    python tests/golden_snapshot.py --check   # compare against the record (run AFTER refactoring)

What is captured, per fixture:
  * the complete dict returned by core.analyzer.analyze (scores, verdict, penalty ledger,
    issues, detections, savings, clusters, top drivers, recommended actions)
  * the full file inventory produced by the classifier
  * the draft targets chosen by core.drafts.select_draft_targets
  * the findings CSV, both plain and redacted
  * the efficiency summary markdown and the handoff prompt
  * a structural fingerprint of the PDF story built by core.exports._common_sections, taken by
    walking the reportlab flowables and reading their text and table cells. This checks the PDF
    content without rendering, so it is not disturbed by embedded timestamps.

Fixtures are built in memory from the deterministic seed generator, so the harness needs no
network, no database and no files left over from an earlier scan.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from core import exports as export_mod  # noqa: E402
from core.analyzer import analyze  # noqa: E402
from core.classifier import inventory_from_entries  # noqa: E402
from core.config import DEFAULT_ASSUMPTIONS, INVENTORY_GROUPS  # noqa: E402
from core.drafts import MAX_DRAFTS, select_draft_targets  # noqa: E402
from core.report import build_payload, inventory_summary  # noqa: E402
from seed import SEED_SPECS, build_entries  # noqa: E402

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")

# One fixture per band so every scoring path and penalty cap is exercised, plus the two
# degenerate cases (too few files, and a repository with nothing wrong).
FIXTURES = [
    ("critical", "agentic-crm", 0.95),
    ("wasteful", "support-copilot", 0.7),
    ("watchlist", "proposal-writer", 0.45),
    ("lean", "rfp-responder", 0.1),
    ("md-only", "instruction-pack", 0.8),
]


def _spec(repo: str) -> dict:
    for spec in SEED_SPECS:
        if spec["repo"] == repo:
            return spec
    raise SystemExit(f"seed spec '{repo}' not found")


def _fingerprint_story(story) -> list:
    """Flatten a reportlab story into comparable text, ignoring styling objects."""
    out = []
    for item in story:
        name = type(item).__name__
        if hasattr(item, "text"):
            out.append(f"{name}: {item.text}")
        elif hasattr(item, "_cellvalues"):
            rows = []
            for row in item._cellvalues:
                cells = []
                for cell in row:
                    if hasattr(cell, "text"):
                        cells.append(str(cell.text))
                    elif isinstance(cell, list):
                        cells.append(" | ".join(
                            str(getattr(c, "text", c)) for c in cell))
                    else:
                        cells.append(str(cell))
                rows.append(cells)
            out.append({name: rows})
        elif hasattr(item, "_content"):  # KeepTogether and friends
            out.append({name: _fingerprint_story(item._content)})
        else:
            out.append(name)
    return out


def _pdf_story(payload: dict, redacted: bool) -> list:
    st = export_mod._styles()
    alias = (export_mod.build_alias_map([f["path"] for f in payload.get("files", [])])
             if redacted else {})
    limits = (40, 25) if not redacted else (25, 15)
    story = export_mod._common_sections(payload, st, redacted, alias, limits[0], limits[1])
    return _fingerprint_story(story)


def snapshot(name: str, repo: str, badness: float) -> dict:
    spec = _spec(repo)
    entries = build_entries(spec, badness, final=True)
    inv = inventory_from_entries(entries)
    assumptions = json.loads(json.dumps(DEFAULT_ASSUMPTIONS))
    analysis = analyze(inv, assumptions)

    files = [f.to_public() for f in inv.files]
    targets = select_draft_targets(inv.files, analysis, limit=MAX_DRAFTS)
    scan = {
        "id": f"SCN-GOLDEN-{name}",
        "repo_name": repo,
        "repo_owner": spec.get("owner"),
        "branch": spec.get("branch"),
        "source_type": spec.get("source", "zip"),
        "status": "completed",
        "overall_score": analysis["overall_score"],
        "verdict": analysis["verdict"],
        "partial_scan": analysis["partial_scan"],
        "skip_ratio": analysis["skip_ratio"],
        "total_files": inv.total_files,
        "parsed_files": inv.parsed_files,
        "skipped_files": inv.skipped_files,
        "analyzed_tokens": inv.analyzed_tokens,
        "issue_count": len(analysis["issues"]),
        "draft_count": 0,
        "created_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:00:00+00:00",
        **analysis["savings"],
    }
    payload = build_payload(
        scan, files,
        {
            "category_scores": analysis["category_scores"],
            "issues": analysis["issues"],
            "top_drivers": analysis["top_drivers"],
            "recommended_actions": analysis["recommended_actions"],
            "penalty_ledger": analysis["penalty_ledger"],
            "assumptions": analysis["assumptions"],
            "detections": analysis["detections"],
            "clusters": analysis["clusters"],
            "overlap_groups": analysis["overlap_groups"],
        },
        [], [],
    )
    payload["inventory_groups"] = INVENTORY_GROUPS

    return {
        "analysis": analysis,
        "inventory": files,
        "inventory_summary": inventory_summary(files),
        "draft_targets": [{k: v for k, v in t.items() if k != "content"} for t in targets],
        "csv": export_mod.issues_csv(payload),
        "csv_redacted": export_mod.issues_csv(payload, redacted=True),
        "efficiency_summary_md": export_mod.efficiency_summary_md(payload),
        "handoff_prompt": export_mod.handoff_prompt(payload),
        "print_html_len": len(export_mod.print_view_html(payload)),
        "print_html_redacted_len": len(export_mod.print_view_html(payload, redacted=True)),
        "pdf_story_full": _pdf_story(payload, redacted=False),
        "pdf_story_redacted": _pdf_story(payload, redacted=True),
    }


def build_all() -> dict:
    return {name: snapshot(name, repo, badness) for name, repo, badness in FIXTURES}


def _diff(path: str, expected, actual, out: list) -> None:
    if type(expected) is not type(actual):
        out.append(f"{path}: type {type(expected).__name__} -> {type(actual).__name__}")
        return
    if isinstance(expected, dict):
        for key in sorted(set(expected) | set(actual)):
            if key not in expected:
                out.append(f"{path}.{key}: ADDED ({actual[key]!r:.120})")
            elif key not in actual:
                out.append(f"{path}.{key}: REMOVED")
            else:
                _diff(f"{path}.{key}", expected[key], actual[key], out)
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            out.append(f"{path}: length {len(expected)} -> {len(actual)}")
        for i, (e, a) in enumerate(zip(expected, actual)):
            _diff(f"{path}[{i}]", e, a, out)
    elif expected != actual:
        out.append(f"{path}: {str(expected)[:120]!r} -> {str(actual)[:120]!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="record the current behaviour")
    parser.add_argument("--check", action="store_true", help="compare against the record")
    args = parser.parse_args()
    if not (args.write or args.check):
        parser.error("choose --write or --check")

    os.makedirs(GOLDEN_DIR, exist_ok=True)
    target = os.path.join(GOLDEN_DIR, "snapshot.json")
    current = build_all()

    if args.write:
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(current, fh, indent=1, sort_keys=True, default=str)
        totals = {k: v["analysis"]["overall_score"] for k, v in current.items()}
        print(f"wrote {target}")
        print(f"fixtures: {len(current)}  scores: {totals}")
        return 0

    if not os.path.isfile(target):
        print(f"no snapshot at {target}; run --write first")
        return 2
    with open(target, encoding="utf-8") as fh:
        expected = json.load(fh)
    # Round-trip the fresh result through JSON so tuple/str coercion matches the record.
    actual = json.loads(json.dumps(current, sort_keys=True, default=str))
    diffs: list = []
    _diff("", expected, actual, diffs)
    if diffs:
        print(f"BEHAVIOUR CHANGED - {len(diffs)} difference(s):")
        for line in diffs[:60]:
            print("  ", line)
        if len(diffs) > 60:
            print(f"   ... and {len(diffs) - 60} more")
        return 1
    scores = {k: v["analysis"]["overall_score"] for k, v in current.items()}
    print(f"IDENTICAL across {len(current)} fixtures. scores: {scores}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
