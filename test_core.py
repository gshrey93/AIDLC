"""BLOAT GUARDIAN - CORE PROOF OF CONCEPT (single script, no mocks).

Proves, end to end:
  A. Local zip import + extraction + full deterministic analyzer + scoring rules
  B. Zip failure paths (ZipCorrupted, ZipTooLarge)
  C. Markdown upload path + InsufficientData rule
  D. Real GitHub public repo import (success, RepoUnavailable, BranchNotFound, RepoTooLarge)
  E. Real Bitbucket public repo import
  F. Real LLM draft generation with claude-opus-4-7 via EMERGENT_LLM_KEY
  G. Exports: full PDF, redacted PDF, CSV, drafts zip, VS Code handoff zip + redaction proof

Run:  cd /app && python test_core.py
"""
from __future__ import annotations

import asyncio
import io
import os
import shutil
import sys
import tempfile
import traceback
import zipfile
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")

from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from core import config, importer  # noqa: E402
from core.analyzer import analyze  # noqa: E402
from core.classifier import build_inventory  # noqa: E402
from core.drafts import generate_draft, select_draft_targets  # noqa: E402
from core.exports import (  # noqa: E402
    build_alias_map, drafts_zip, full_pdf, handoff_zip, issues_csv, print_view_html, redacted_pdf,
)
from core.report import build_payload  # noqa: E402

OUT = "/app/poc_out"
RESULTS: list = []


def record(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  :: {detail}" if detail else ""))


def section(title: str):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


# --------------------------------------------------------------------------
# Test fixture: a realistic bloated agentic repository
# --------------------------------------------------------------------------
SHARED_BLOCK = (
    "Before you begin any task you must read the repository conventions file, confirm the ticket "
    "number, check that the branch name follows the release naming policy, and make sure the change "
    "log entry has been drafted. Never commit directly to the main branch. Always run the unit test "
    "suite and the lint task before you hand work over to the next agent in the chain."
)

REVIEW_BLOCK = (
    "## Review workflow\n\n"
    "Every change moves through the following gates in order: self review, then peer review, then "
    "code review by the owning team, then a security review, then architecture review, then product "
    "owner approval, and finally a final sign-off from the delivery manager. A human in the loop must "
    "confirm each gate. Escalation review applies when a gate is skipped.\n"
)

AGENT_BODY = (
    "# {name} agent\n\n"
    "## Purpose\n\nThis agent owns {job} for the platform.\n\n"
    "## Operating rules\n\n" + SHARED_BLOCK + "\n\n"
    + REVIEW_BLOCK +
    "\n## Tools\n\n- repository search\n- test runner\n- ticket updater\n\n"
    "## Hand-off\n\nWhen finished, write a summary into the shared memory file and notify the "
    "orchestrator so the next stage can start. Include the ticket number, the files touched, and "
    "the tests that were run.\n"
)


def build_fixture_repo(root: str) -> None:
    def write(rel: str, text: str):
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    write("README.md", "# agentic-crm\n\nA multi agent CRM automation platform.\n" + SHARED_BLOCK)

    # 16 agent files -> agent sprawl; 5 of them are near identical -> duplicates
    jobs = [
        ("intake", "lead intake and qualification"), ("triage", "ticket triage"),
        ("research", "account research"), ("proposal", "proposal drafting"),
        ("pricing", "deal pricing"), ("legal", "contract review"),
        ("onboarding", "customer onboarding"), ("support", "support replies"),
        ("billing", "invoice questions"), ("renewal", "renewal outreach"),
        ("reporting", "pipeline reporting"), ("forecast", "revenue forecasting"),
        ("qa", "quality checks"), ("escalation", "escalation handling"),
        ("notes", "call note summaries"), ("handoff", "stage hand-offs"),
    ]
    for name, job in jobs:
        write(f"agents/{name}.agent.md", AGENT_BODY.format(name=name.title(), job=job))
    # exact / near duplicates of the intake agent
    base = AGENT_BODY.format(name="Intake", job="lead intake and qualification")
    write("agents/legacy/intake-copy.agent.md", base)
    write("agents/legacy/intake-v2.agent.md", base.replace("repository search", "repo search"))
    write("agents/legacy/intake-old.agent.md", base.upper())
    write("agents/legacy/intake-backup.agent.md", base.replace("\n\n", "\n   \n"))

    # oversized context + memory files
    big = (
        "## Account history\n\n"
        + ("The customer has an established relationship with the platform and has raised "
           "several tickets about billing, onboarding and reporting over the last four quarters. "
           "Each ticket was resolved by a different agent and the notes were copied here. ") * 260
    )
    write("context/context.md", "# Working context\n\n" + SHARED_BLOCK + "\n\n" + big)
    write("memory/memory.md", "# Long term memory\n\n" + big + "\n" + big[:20000])
    write("context/product-context.md", "# Product context\n\n" + big[:40000])

    # orchestration + instructions
    write("orchestrator.md", "# Orchestrator\n\n" + REVIEW_BLOCK + "\n" + SHARED_BLOCK
          + "\n\n## Stages\n\n1. intake\n2. triage\n3. research\n4. proposal\n5. review\n")
    write("instructions.md", "# Build instructions\n\n" + SHARED_BLOCK + "\n\n" + REVIEW_BLOCK)
    write("instruction.md", "# Contributor instruction\n\n" + SHARED_BLOCK
          + "\n\nKeep pull requests small.\n")
    for i in range(1, 7):
        write(f"prompts/stage-{i}.prompt.md", f"# Stage {i} prompt\n\n" + SHARED_BLOCK
              + f"\n\nFocus on stage {i} of the pipeline and nothing else.\n")
    write("workflow.md", "# Workflow\n\n" + REVIEW_BLOCK)

    # skills, several repeating
    skill = ("# Skill: {n}\n\n" + SHARED_BLOCK + "\n\nUse this skill when the task mentions {n}.\n")
    for n in ["search", "summarise", "classify", "extract", "validate", "translate",
              "format", "escalate", "schedule", "notify", "archive", "reconcile"]:
        write(f"skills/{n}.skill.md", skill.format(n=n))
    write("skills/legacy/search-old.skill.md", skill.format(n="search"))

    # diagrams + data + docs
    write("docs/architecture.mmd", "graph TD\n  A[intake]-->B[triage]\n  B-->C[proposal]\n")
    write("docs/guide.md", "# Guide\n\nHow to run the platform locally.\n" + SHARED_BLOCK)
    write("config/settings.yaml", "service: crm\nreplicas: 2\nfeatures:\n  - agents\n  - memory\n")
    write("package.json", '{"name":"agentic-crm","version":"1.0.0"}')

    # 9 thin services with very little code -> microservice mismatch
    for i in range(1, 10):
        write(f"services/svc-{i}/package.json", '{"name":"svc-%d"}' % i)
        write(f"services/svc-{i}/index.js", f"export const handler = () => 'svc-{i}';\n")
        write(f"services/svc-{i}/Dockerfile", "FROM node:20\nCMD [\"node\",\"index.js\"]\n")

    # unsupported + binary + oversized files to exercise skip reasons
    write("assets/logo.svg", "<svg></svg>")
    write("assets/notes.docx", "not really a docx")
    for i in range(12):
        write(f"assets/asset-{i}.png.txt.bak", "unsupported extension payload")
    with open(os.path.join(root, "assets", "blob.json"), "wb") as fh:
        fh.write(b"{\x00\x01binary\x00}")
    with open(os.path.join(root, "data-dump.json"), "w", encoding="utf-8") as fh:
        fh.write('{"rows":[' + ",".join('{"identifier":%d}' % i for i in range(320000)) + "]}")


def zip_dir(src_dir: str, zip_path: str, top: str = "agentic-crm") -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirs, files in os.walk(src_dir):
            for fn in files:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, src_dir)
                zf.write(full, os.path.join(top, rel))


# --------------------------------------------------------------------------
def scan_meta(imported, inv, analysis, sid="SCN-2026-01-01-0001") -> dict:
    return {
        "id": sid,
        "source_type": imported.source_type,
        "repo_name": imported.repo_name,
        "repo_owner": imported.repo_owner,
        "branch": imported.branch,
        "status": "InsufficientData" if analysis["insufficient_data"] else "completed",
        "total_files": inv.total_files,
        "parsed_files": inv.parsed_files,
        "skipped_files": inv.skipped_files,
        "analyzed_tokens": inv.analyzed_tokens,
        "overall_score": analysis["overall_score"],
        "verdict": analysis["verdict"],
        "partial_scan": analysis["partial_scan"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        **analysis["savings"],
    }


# ============================================== A. zip import + analyzer
def test_zip_and_analyzer():
    section("A. Zip import, classification, deterministic adversary scan")
    work = importer.make_work_dir("poc-zip-")
    fixture = os.path.join(work, "fixture")
    os.makedirs(fixture, exist_ok=True)
    build_fixture_repo(fixture)
    zpath = os.path.join(work, "agentic-crm.zip")
    zip_dir(fixture, zpath)
    record("fixture zip created", os.path.getsize(zpath) > 1000,
           f"{os.path.getsize(zpath) / 1024:.0f} KB")

    imported = importer.import_zip(zpath, work, display_name="agentic-crm")
    record("zip extracted with top folder stripped",
           os.path.isfile(os.path.join(imported.root_dir, "orchestrator.md")), imported.root_dir)

    inv = build_inventory(imported.root_dir)
    record("inventory built", inv.total_files > 60,
           f"total={inv.total_files} parsed={inv.parsed_files} skipped={inv.skipped_files} "
           f"tokens={inv.analyzed_tokens:,}")

    statuses = {}
    for f in inv.files:
        statuses[f.parse_status] = statuses.get(f.parse_status, 0) + 1
    record("SkippedUnsupported detected", statuses.get("SkippedUnsupported", 0) >= 2, str(statuses))
    record("Binary detected", statuses.get("Binary", 0) >= 1, str(statuses))
    oversized = [f for f in inv.files if f.parse_status == "SkippedOversized"]
    record("SkippedOversized detected (>5MB)", len(oversized) >= 1,
           ", ".join(f"{f.path} {f.size_bytes / 1048576:.1f}MB" for f in oversized))

    groups = {}
    for f in inv.files:
        groups[f.inventory_group] = groups.get(f.inventory_group, 0) + 1
    record("inventory groups populated", len(groups) >= 6, str(groups))

    # token formula check
    sample = next(f for f in inv.files if f.path == "orchestrator.md")
    with open(os.path.join(imported.root_dir, "orchestrator.md"), encoding="utf-8") as fh:
        chars = len(fh.read())
    import math
    record("token formula ceil(chars/4)", sample.estimated_tokens == math.ceil(chars / 4),
           f"{chars} chars -> {sample.estimated_tokens} tokens")

    analysis = analyze(inv)
    det = analysis["detections"]
    print("    detections:", {k: v for k, v in det.items() if not isinstance(v, list)})

    record("near-duplicate clusters found", det["duplicate_clusters_found"] >= 1,
           f"{det['duplicate_clusters_found']} clusters, {det['duplicate_pairs_penalised']} penalised pairs")
    record("repeated instruction blocks found", det["repeated_block_groups"] >= 1,
           f"{det['repeated_block_groups']} groups")
    record("oversized context files found", det["oversized_context_files"] >= 2,
           f"{det['oversized_context_files']} files")
    record("agent sprawl detected", det["agent_like_files"] > 12, f"{det['agent_like_files']} agent-like files")
    record("review stages inferred > 4", det["review_stages_inferred"] > 4,
           ", ".join(det["review_stage_names"]))
    record("microservice mismatch detected", det["microservice_mismatch"] is True,
           f"{det['service_dir_count']} service dirs / {det['non_generated_source_files']} source files")
    record("overlapping agent groups detected", det["overlapping_agent_groups"] >= 1,
           f"{det['overlapping_agent_groups']} groups")

    # penalty caps
    ledger = {r["rule"][:28]: r for r in analysis["penalty_ledger"]}
    caps_ok = all(r["applied"] <= r["cap"] for r in analysis["penalty_ledger"])
    record("all penalties respect their caps", caps_ok,
           "; ".join(f"{r['rule'][:34]}={r['applied']}/{r['cap']}" for r in analysis["penalty_ledger"]))

    cats = {c["category"]: c for c in analysis["category_scores"]}
    record("5 category scores, integers 0-100",
           len(cats) == 5 and all(isinstance(c["score"], int) and 0 <= c["score"] <= 100 for c in cats.values()),
           ", ".join(f"{k}={v['score']}" for k, v in cats.items()))

    expected = int(round(sum(cats[k]["score"] * w for k, w in config.CATEGORY_WEIGHTS.items())))
    record("weighted overall score matches 25/25/20/20/10", analysis["overall_score"] == expected,
           f"score={analysis['overall_score']} expected={expected} verdict={analysis['verdict']}")
    record("verdict band correct",
           analysis["verdict"] == config.verdict_for_score(analysis["overall_score"]),
           f"{analysis['overall_score']} -> {analysis['verdict']}")

    record("issues generated with waste + credits", len(analysis["issues"]) >= 8,
           f"{len(analysis['issues'])} issues, top waste "
           f"{analysis['issues'][0]['estimated_token_waste']:,} tokens")
    record("top 5 waste drivers produced", len(analysis["top_drivers"]) == 5,
           analysis["top_drivers"][0]["title"])
    sv = analysis["savings"]
    lo_ok = abs(sv["estimated_savings_low"] - sv["estimated_monthly_dollar_waste"] * 0.8) < 0.05
    hi_ok = abs(sv["estimated_savings_high"] - sv["estimated_monthly_dollar_waste"] * 1.2) < 0.05
    record("savings low/high are +/-20%", lo_ok and hi_ok,
           f"${sv['estimated_savings_low']:,.2f} .. ${sv['estimated_monthly_dollar_waste']:,.2f} "
           f".. ${sv['estimated_savings_high']:,.2f}")
    rates = analysis["assumptions"]
    record("derived $ rates from owner pricing model",
           abs(rates["input_dollars_per_million"] - 4.0) < 0.001
           and abs(rates["output_dollars_per_million"] - 20.0) < 0.001,
           f"input ${rates['input_dollars_per_million']}/1M, output ${rates['output_dollars_per_million']}/1M")
    record("partial scan flag computed", isinstance(analysis["partial_scan"], bool),
           f"skip_ratio={analysis['skip_ratio']:.2%} partial={analysis['partial_scan']}")
    record("PartialScan badge triggers above 20% skipped",
           analysis["partial_scan"] is True and analysis["skip_ratio"] > 0.20,
           f"skip_ratio={analysis['skip_ratio']:.2%}")

    # determinism
    inv2 = build_inventory(imported.root_dir)
    analysis2 = analyze(inv2)
    record("deterministic across runs", analysis2["overall_score"] == analysis["overall_score"]
           and len(analysis2["issues"]) == len(analysis["issues"]),
           f"{analysis['overall_score']} == {analysis2['overall_score']}")

    return work, imported, inv, analysis


# ============================================== B. zip failure paths
def test_zip_failures():
    section("B. Zip failure paths")
    work = importer.make_work_dir("poc-zipfail-")
    bad = os.path.join(work, "broken.zip")
    with open(bad, "wb") as fh:
        fh.write(b"PK\x03\x04this-is-not-a-real-zip-file" + os.urandom(512))
    try:
        importer.import_zip(bad, work)
        record("corrupted zip -> ZipCorrupted", False, "no error raised")
    except importer.ImportError_ as exc:
        record("corrupted zip -> ZipCorrupted", exc.code == "ZipCorrupted", f"{exc.code}: {exc.message}")

    # oversize guard: shrink the limit and confirm the guard trips
    original = importer.MAX_ARCHIVE_BYTES
    try:
        importer.MAX_ARCHIVE_BYTES = 256
        big = os.path.join(work, "big.zip")
        with zipfile.ZipFile(big, "w") as zf:
            zf.writestr("a.md", "x" * 20000)
        try:
            importer.import_zip(big, work)
            record("oversized zip -> ZipTooLarge", False, "no error raised")
        except importer.ImportError_ as exc:
            record("oversized zip -> ZipTooLarge", exc.code == "ZipTooLarge", f"{exc.code}: {exc.message}")
    finally:
        importer.MAX_ARCHIVE_BYTES = original
    shutil.rmtree(work, ignore_errors=True)


# ============================================== C. markdown upload path
def test_markdown_upload():
    section("C. Markdown upload + InsufficientData rule")
    work = importer.make_work_dir("poc-md-")
    files = [(f"note-{i}.md", f"# Note {i}\n\nShort note.\n".encode()) for i in range(3)]
    imported = importer.import_markdown_files(files, work, display_name="md-upload")
    inv = build_inventory(imported.root_dir)
    analysis = analyze(inv)
    record("3 md files -> InsufficientData", analysis["insufficient_data"] is True,
           f"parsed={inv.parsed_files} (needs >= {config.MIN_TEXT_FILES_FOR_VALID_SCAN})")
    record("InsufficientData blocks savings",
           all(v == 0 for v in analysis["savings"].values()), str(analysis["savings"]))
    record("InsufficientData yields no verdict", analysis["verdict"] is None, str(analysis["verdict"]))

    more = files + [(f"agent-{i}.agent.md", (f"# Agent {i}\n\n" + SHARED_BLOCK).encode()) for i in range(4)]
    work2 = importer.make_work_dir("poc-md2-")
    imported2 = importer.import_markdown_files(more, work2, display_name="md-upload-ok")
    inv2 = build_inventory(imported2.root_dir)
    analysis2 = analyze(inv2)
    record("7 md files -> valid scan", analysis2["insufficient_data"] is False,
           f"parsed={inv2.parsed_files} score={analysis2['overall_score']} verdict={analysis2['verdict']}")
    record("repeated block across 4 md files detected",
           analysis2["detections"]["repeated_block_groups"] >= 1,
           f"{analysis2['detections']['repeated_block_groups']} groups")
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(work2, ignore_errors=True)


# ============================================== D. GitHub (real network)
GITHUB_CANDIDATES = [
    "https://github.com/github/awesome-copilot",
    "https://github.com/humanlayer/12-factor-agents",
    "https://github.com/openai/openai-agents-python",
]


def test_github():
    section("D. GitHub import (real, unauthenticated public API)")
    ok_result = None
    for url in GITHUB_CANDIDATES:
        work = importer.make_work_dir("poc-gh-")
        try:
            imported = importer.import_github(url, None, work)
            inv = build_inventory(imported.root_dir)
            analysis = analyze(inv)
            record(f"GitHub import succeeded: {url}", inv.parsed_files >= 5,
                   f"branch={imported.branch} archive={imported.archive_bytes / 1048576:.1f}MB "
                   f"files={inv.total_files} parsed={inv.parsed_files} "
                   f"tokens={inv.analyzed_tokens:,} score={analysis['overall_score']} "
                   f"verdict={analysis['verdict']} issues={len(analysis['issues'])}")
            ok_result = (work, imported, inv, analysis)
            break
        except Exception as exc:
            record(f"GitHub import {url}", False, f"{type(exc).__name__}: {exc}")
            shutil.rmtree(work, ignore_errors=True)
    if ok_result is None:
        record("GitHub import success path", False, "no candidate repo imported")

    work = importer.make_work_dir("poc-gh-bad-")
    try:
        importer.import_github("https://github.com/octocat/definitely-not-a-real-repo-9f2x", None, work)
        record("missing repo -> GitHubRepoUnavailable", False, "no error raised")
    except importer.ImportError_ as exc:
        record("missing repo -> GitHubRepoUnavailable", exc.code == "GitHubRepoUnavailable",
               f"{exc.code}: {exc.message}")
    shutil.rmtree(work, ignore_errors=True)

    work = importer.make_work_dir("poc-gh-branch-")
    try:
        importer.import_github("https://github.com/octocat/Hello-World", "no-such-branch-9f2x", work)
        record("bad branch -> BranchNotFound", False, "no error raised")
    except importer.ImportError_ as exc:
        record("bad branch -> BranchNotFound", exc.code == "BranchNotFound", f"{exc.code}: {exc.message}")
    shutil.rmtree(work, ignore_errors=True)

    work = importer.make_work_dir("poc-gh-big-")
    try:
        importer.import_github("https://github.com/torvalds/linux", None, work)
        record("huge repo -> RepoTooLarge", False, "no error raised (download completed)")
    except importer.ImportError_ as exc:
        record("huge repo -> RepoTooLarge", exc.code == "RepoTooLarge", f"{exc.code}: {exc.message}")
    shutil.rmtree(work, ignore_errors=True)

    work = importer.make_work_dir("poc-gh-url-")
    try:
        importer.import_github("https://gitlab.com/foo/bar", None, work)
        record("non-GitHub URL rejected", False, "no error raised")
    except importer.ImportError_ as exc:
        record("non-GitHub URL rejected", exc.code == "GitHubRepoUnavailable", exc.message)
    shutil.rmtree(work, ignore_errors=True)

    return ok_result


# ============================================== E. Bitbucket (real network)
BITBUCKET_CANDIDATES = [
    "https://bitbucket.org/tildeslash/monit",
    "https://bitbucket.org/atlassian/atlassian-jwt-js",
    "https://bitbucket.org/cmicdev/atlassian-connect-express",
    "https://bitbucket.org/hpk42/tox",
    "https://bitbucket.org/pypa/setuptools",
]


def test_bitbucket():
    section("E. Bitbucket import (real, unauthenticated public API)")
    success = None
    for url in BITBUCKET_CANDIDATES:
        work = importer.make_work_dir("poc-bb-")
        try:
            imported = importer.import_bitbucket(url, None, work)
            inv = build_inventory(imported.root_dir)
            analysis = analyze(inv)
            record(f"Bitbucket import succeeded: {url}", inv.total_files > 0,
                   f"branch={imported.branch} archive={imported.archive_bytes / 1048576:.1f}MB "
                   f"files={inv.total_files} parsed={inv.parsed_files} "
                   f"score={analysis['overall_score']} verdict={analysis['verdict']}")
            success = (work, imported, inv, analysis)
            break
        except Exception as exc:
            print(f"       tried {url} -> {type(exc).__name__}: {exc}")
            shutil.rmtree(work, ignore_errors=True)
    if success is None:
        record("Bitbucket import success path", False, "no candidate repo imported")

    work = importer.make_work_dir("poc-bb-bad-")
    try:
        importer.import_bitbucket("https://bitbucket.org/nobody/definitely-not-real-9f2x", None, work)
        record("missing bitbucket repo -> BitbucketRepoUnavailable", False, "no error raised")
    except importer.ImportError_ as exc:
        record("missing bitbucket repo -> BitbucketRepoUnavailable",
               exc.code == "BitbucketRepoUnavailable", f"{exc.code}: {exc.message}")
    shutil.rmtree(work, ignore_errors=True)
    if success:
        shutil.rmtree(success[0], ignore_errors=True)
    return success


# ============================================== F. LLM drafts (real call)
async def test_drafts(inv, analysis, repo_name):
    section("F. Recommendation drafts via claude-opus-4-7 (real LLM call)")
    key = os.environ.get("EMERGENT_LLM_KEY")
    record("EMERGENT_LLM_KEY present", bool(key), (key[:14] + "...") if key else "missing")
    if not key:
        return []
    targets = select_draft_targets(inv.files, analysis, limit=25)
    record("draft targets selected (agent/instruction/orchestration/context/memory only)",
           len(targets) >= 3 and all(t["target_type"] in ("instruction", "orchestrator", "context", "memory")
                                     for t in targets),
           f"{len(targets)} targets: " + ", ".join(t["target_filename"] for t in targets[:6]))
    record("no source code files selected for drafting",
           all(not t["source_path"].endswith((".py", ".js", ".ts", ".go", ".java", ".rb", ".rs", ".cs"))
               for t in targets), "ok")
    record("draft filenames carry -optimised suffix",
           all("-optimised" in t["target_filename"] for t in targets),
           targets[0]["target_filename"] if targets else "-")

    drafts = []
    for t in targets[:2]:
        try:
            d = await generate_draft(t, repo_name, key)
            drafts.append(d)
            record(f"LLM draft generated: {d['target_filename']}",
                   len(d["draft_content"]) > 200,
                   f"{d['original_tokens']:,} -> {d['draft_tokens']:,} tokens "
                   f"(-{d['reduction_pct']}%) via {d['model']}")
            print("       preview:", d["draft_content"][:220].replace("\n", " | "))
        except Exception as exc:
            record(f"LLM draft for {t['target_filename']}", False, f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
    record("at least one -optimised draft produced", len(drafts) >= 1, f"{len(drafts)} drafts")
    return drafts


# ============================================== G. exports
def test_exports(payload):
    section("G. Exports: full PDF, redacted PDF, CSV, drafts zip, handoff zip")
    os.makedirs(OUT, exist_ok=True)

    csv_text = issues_csv(payload)
    rows = csv_text.strip().splitlines()
    with open(f"{OUT}/findings.csv", "w", encoding="utf-8") as fh:
        fh.write(csv_text)
    record("CSV has one row per issue", len(rows) - 1 == len(payload["issues"]),
           f"{len(rows) - 1} data rows for {len(payload['issues'])} issues")

    pdf = full_pdf(payload)
    with open(f"{OUT}/report-full.pdf", "wb") as fh:
        fh.write(pdf)
    pages = pdf.count(b"/Type /Page") or pdf.count(b"/Type/Page")
    record("full PDF generated and <= 40 pages", pdf.startswith(b"%PDF") and 0 < pages <= 40,
           f"{len(pdf) / 1024:.0f} KB, ~{pages} pages")

    rpdf = redacted_pdf(payload)
    with open(f"{OUT}/report-redacted.pdf", "wb") as fh:
        fh.write(rpdf)
    rpages = rpdf.count(b"/Type /Page") or rpdf.count(b"/Type/Page")
    record("redacted PDF generated and <= 25 pages", rpdf.startswith(b"%PDF") and 0 < rpages <= 25,
           f"{len(rpdf) / 1024:.0f} KB, ~{rpages} pages")

    alias = build_alias_map([f["path"] for f in payload["files"]])
    rcsv = issues_csv(payload, redacted=True)
    leaks = [p for p in list(alias.keys())[:400] if p in rcsv]
    record("redacted CSV contains no real file paths", not leaks, f"leaks={leaks[:3]}")
    record("redacted CSV uses path aliases", "file-0" in rcsv or "dir-" in rcsv,
           rcsv.splitlines()[1][:120] if len(rcsv.splitlines()) > 1 else "-")

    rhtml = print_view_html(payload, redacted=True)
    fhtml = print_view_html(payload, redacted=False)
    for name, body in (("print-view.html", fhtml), ("print-view-redacted.html", rhtml)):
        with open(f"{OUT}/{name}", "w", encoding="utf-8") as fh:
            fh.write(body)
    keeps = all(str(payload["scan"][k]) in rhtml for k in ("overall_score", "parsed_files", "skipped_files"))
    record("redacted view preserves counts, score and savings", keeps, "aggregates preserved")
    record("HTML print fallback available for both variants",
           fhtml.startswith("<!doctype html") and rhtml.startswith("<!doctype html"), "ok")

    dz = drafts_zip(payload)
    with open(f"{OUT}/drafts.zip", "wb") as fh:
        fh.write(dz)
    with zipfile.ZipFile(io.BytesIO(dz)) as zf:
        names = zf.namelist()
    record("drafts zip built with -optimised files",
           any("-optimised" in n for n in names) or "drafts/NO-DRAFTS.md" in names, str(names[:6]))

    hz = handoff_zip(payload)
    with open(f"{OUT}/vscode-handoff.zip", "wb") as fh:
        fh.write(hz)
    with zipfile.ZipFile(io.BytesIO(hz)) as zf:
        names = zf.namelist()
        summary = zf.read("efficiency-summary.md").decode()
    required = ["efficiency-summary.md", "recommended-instruction.md", "recommended-orchestrator.md",
                "recommended-context.md", "findings.csv"]
    record("handoff zip has all 5 required files", all(r in names for r in required), str(names[:8]))
    record("handoff zip includes VS Code fallback instructions", "README.md" in names, "README.md present")
    record("handoff summary contains score and verdict",
           str(payload["scan"]["overall_score"]) in summary, summary.splitlines()[0])
    print(f"\n    artefacts written to {OUT}")


# ============================================================== main
async def main():
    print("BLOAT GUARDIAN - CORE POC")
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)

    work, imported, inv, analysis = test_zip_and_analyzer()
    test_zip_failures()
    test_markdown_upload()
    gh = test_github()
    test_bitbucket()

    drafts = await test_drafts(inv, analysis, imported.repo_name)

    payload = build_payload(
        scan_meta(imported, inv, analysis),
        [f.to_public() for f in inv.files],
        analysis, drafts, inv.warnings,
    )
    payload["scan"]["estimated_monthly_credit_waste"] = analysis["savings"]["estimated_monthly_credit_waste"]
    test_exports(payload)

    if gh:
        section("H. Exports for the real GitHub scan")
        gwork, gimported, ginv, ganalysis = gh
        gpayload = build_payload(
            scan_meta(gimported, ginv, ganalysis, "SCN-2026-01-01-0002"),
            [f.to_public() for f in ginv.files], ganalysis, [], ginv.warnings,
        )
        gpayload["scan"]["estimated_monthly_credit_waste"] = \
            ganalysis["savings"]["estimated_monthly_credit_waste"]
        try:
            gp = full_pdf(gpayload)
            gr = redacted_pdf(gpayload)
            with open(f"{OUT}/github-report-full.pdf", "wb") as fh:
                fh.write(gp)
            with open(f"{OUT}/github-report-redacted.pdf", "wb") as fh:
                fh.write(gr)
            fp = gp.count(b"/Type /Page") or gp.count(b"/Type/Page")
            rp = gr.count(b"/Type /Page") or gr.count(b"/Type/Page")
            record("real repo PDFs respect page caps", fp <= 40 and rp <= 25,
                   f"full ~{fp} pages, redacted ~{rp} pages")
        except Exception as exc:
            record("real repo PDF export", False, f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
        shutil.rmtree(gwork, ignore_errors=True)

    shutil.rmtree(work, ignore_errors=True)

    section("SUMMARY")
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  FAILED: {name} :: {detail}")
    print(f"\n  {passed}/{len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
