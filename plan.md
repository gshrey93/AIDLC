# Bloat Guardian — Phased Implementation Plan

## Objectives
- Prove the **core workflow works end-to-end with no mocks**: import (GitHub/Bitbucket/zip) → parse/classify → deterministic scoring + verdict → LLM “-optimised” drafts → PDF/CSV/zip exports.
- Ship a **single-user** MVP web app with all 7 surfaces, real error states, seeded demo history, transparent savings math, and strong export/redaction.
- Add polish, harden edge cases, and implement retention/refresh mechanisms.

---

## Phase 1 — Core POC in Isolation (`/app/test_core.py`) — ✅ COMPLETE (58/58 checks passed)

**Proven with real network + real LLM, no mocks:**
- Real GitHub import of `github/awesome-copilot` (71 MB archive, 2215 files, 1445 parsed, 3.7M tokens, score 80 / Lean)
- Real error paths: `GitHubRepoUnavailable`, `BranchNotFound`, `RepoTooLarge` (torvalds/linux = 6149 MB), non-GitHub URL rejection
- Real Bitbucket import of `tildeslash/monit` + `BitbucketRepoUnavailable`
- Zip import + `ZipCorrupted` + `ZipTooLarge`; markdown upload + `InsufficientData` (savings zeroed, no verdict)
- Analyzer: `ceil(chars/4)` verified, all 7 penalty rules verified against their caps (32/20/24/20/15/12/10), 5 integer category scores, weighted 25/25/20/20/10 overall score verified, verdict bands, `PartialScan` at 26.6% skipped, deterministic across runs
- Detections verified: 2 duplicate clusters, 4 repeated instruction blocks, 3 oversized context files, 46 agent-like files, 10 review stages, microservice mismatch, overlapping agent groups
- Savings: derived $4.00/1M input, $20.00/1M output from owner pricing model; ±20% low/high range
- Real `claude-opus-4-7` drafts via `EMERGENT_LLM_KEY`: `memory-optimised.md` (20,676 → 215 tokens), `context-optimised.md` (15,766 → 244 tokens)
- Exports: full PDF (11 pages ≤ 40), redacted PDF (9 pages ≤ 25), CSV 1-row-per-issue, drafts zip, handoff zip with all 5 required files, HTML print fallbacks, redaction verified to leak zero real paths while preserving aggregates
- Reusable engine now lives at `/app/backend/core/` (config, importer, classifier, similarity, analyzer, drafts, exports, report)

### Original Phase 1 detail

### User stories (POC)
1. As a user, I want to scan a **real public GitHub repo** and get a score/verdict so I can trust imports work.
2. As a user, I want Bitbucket import to work the same way so I’m not locked to one host.
3. As a user, I want zip upload parsing to fail clearly on corruption so I know what to fix.
4. As a user, I want deterministic scoring with transparent penalties so results are explainable.
5. As a user, I want at least one real `*-optimised.md` draft generated from my file so I trust recommendation drafting.
6. As a user, I want exports (full/redacted PDF, CSV, zips) so I can share results outside the app.

### Implementation steps
1. **Web search (best practices / endpoints)**
   - Confirm GitHub archive endpoints + branch handling + rate-limit signals.
   - Confirm Bitbucket archive endpoints for public repos + branch/tag.
   - Confirm reportlab patterns for multi-page PDF + truncation for max pages.
2. **Repo import (real network, unauthenticated)**
   - GitHub: parse `https://github.com/{owner}/{repo}` + optional branch; download archive; implement:
     - `GitHubRepoUnavailable`, `GitHubRateLimited` (with retry-after guidance), `RepoTooLarge`, `BranchNotFound`.
   - Bitbucket: parse repo URL; download archive; map errors to `ImportFailed` with specific reason.
   - Zip: local zip path; detect `ZipCorrupted`, `ZipTooLarge`.
3. **Extraction + limits**
   - Enforce repo limits: `<=250MB compressed` and `<=1500 files`.
   - Extract to temp dir; collect tree + metadata.
4. **Parsing & classification**
   - Supported extensions only; detect binary; handle oversized single files (>5MB) as `SkippedOversized`.
   - Classify into required inventory buckets; “agent-like” detection by names/paths.
   - Token estimate per file: `ceil(char_count/4)`.
   - Validate scan: if parsed text files < 5 → `InsufficientData`.
5. **Deterministic adversary scan (all required detections)**
   - Near-duplicates: normalized similarity ≥ 0.80 (case/whitespace insensitive), penalty `-5` each, cap `32`.
   - Repeated instruction blocks: ≥150 chars in ≥3 files, penalty `-4` each, cap `20`.
   - Oversized context/memory: >8000 tokens, penalty `-6` each, cap `24`.
   - Agent sprawl: >12 agent-like files, `-2` per extra, cap `20`.
   - Review stages: infer stages from instruction text; if >4 stages, `-5` each finding, cap `15`.
   - Microservice mismatch: service dirs ≥8 and non-generated source <120 → `-12`.
   - Monolith mismatch: 1 service and ≥10 agent role files w/ overlap → `-10`.
   - Compute 5 integer category scores (0–100) + weighted overall + verdict enum + `PartialScan` badge if skipped >20%.
6. **Savings math (defaults only in POC)**
   - Credits assumption default: `1 credit = 100,000 tokens`.
   - Dollars: defaults derived from user rules ($1=100 credits; 1 credit=2,500 input or 500 output; output 5x).
   - Produce low/high ranges with ±20% variance.
7. **LLM draft generation (real call)**
   - Use `EMERGENT_LLM_KEY` + model `claude-opus-4-7` via `emergentintegrations`.
   - Pick one real detected file among instruction/orchestrator/context/memory; generate refined content and save as `*-optimised.md`.
8. **Exports (real files)**
   - Generate: full PDF (≤40 pages), redacted PDF (≤25 pages, aliases + no contents), CSV (1 row/issue).
   - Package `drafts.zip` and `vscode_handoff.zip` (5 required files).
9. **Run matrix**
   - Run against: 1 GitHub repo success, GitHub bad branch, GitHub unreachable, 1 Bitbucket repo success, 1 valid zip, 1 corrupted zip.

### Next actions
- Implement `/app/test_core.py` and iterate until every run path is green.

### Success criteria
- Single script produces: scores/verdict, issues, 1+ `-optimised.md` draft via real LLM call, full+redacted PDFs, CSV, drafts+handoff zips.
- All specified import error states reproduce reliably.
- `InsufficientData` and `PartialScan` conditions trigger correctly.

---

## Phase 2 — V1 App Build (FastAPI + React + Mongo) + 1 round E2E testing

### User stories (V1)
1. As a user, I want to start a scan from GitHub/Bitbucket/zip with validations and a rights checkbox so I can safely run analyses.
2. As a user, I want a progress page with the exact stages so I can see what’s happening and why it’s slow.
3. As a user, I want a results dashboard with top waste drivers and plain-language summaries so I can act without reading raw files.
4. As a user, I want to download full/redacted PDF, CSV, and draft zip so I can share findings.
5. As a user, I want a history page with the last 10 scans so I can compare outcomes over time.
6. As a user, I want a Settings page to set my own Anthropic/Gemini key and edit savings assumptions so the math matches reality.

### Implementation steps
1. **Backend core (FastAPI)**
   - Endpoints: create scan, get scan status/progress, get results, list history (last 10), delete scan, exports (PDF/CSV/zips), settings (keys + pricing assumptions), refresh rates.
   - Background worker: run the proven Phase-1 analyzer pipeline with progress persisted.
   - Real GitHub/Bitbucket public import (no PAT stored); optional user PAT field stored locally for session use only (or encrypted-at-rest) but default path is unauth.
2. **Data model + retention**
   - Implement entities: Scan, FileAsset, CategoryScore, Issue, RecommendationDraft, ExportJob.
   - Retention jobs: delete raw imported/uploaded contents after 7 days; delete derived reports after 30 days.
3. **Seed data**
   - Seed 1 demo user + 20 demo scans exactly as specified (18 completed + 2 failed), labeled “Seeded demo”.
4. **Frontend (React)**
   - 7 surfaces: Landing, New Scan, Progress, Results Dashboard, Export drawer, History, VS Code handoff.
   - States: all failure enums; PartialScan banner; InsufficientData disables savings.
   - Draft previews + copy to clipboard; download zips.
5. **Pricing/savings UI**
   - Show assumptions transparently: token→credit (default 1/100k), $/credit rules, input vs output rates.
   - “Refresh rates” action: web-search-driven update (store value + timestamp + provenance note) + manual override.
6. **LLM key settings**
   - Default: Emergent universal key.
   - Optional: user-provided Anthropic or Gemini key (stored server-side); model selection for Anthropic includes `claude-opus-4-7`.
7. **Testing (testing_agent_v3)**
   - Run full flow: import → progress → results → exports → history → delete.
   - Exercise failure paths + fallbacks (manual zip upload suggested on import failures).

### Next actions
- Implement backend + frontend in one integrated pass using the Phase-1 core module.
- Seed demo data and run one complete E2E test pass.

### Success criteria
- All 7 surfaces functional; progress updates through all stages.
- GitHub + Bitbucket + zip imports work for public repos.
- Exports work (or fall back to HTML print / clipboard).
- Seed history shows 20 scans across last 90 days; real scans append and last-10 view works.

---

## Phase 3 — Polish, hardening, and edge cases + 1 round E2E testing

### User stories (polish)
1. As a user, I want redacted reports to preserve usefulness while removing sensitive details.
2. As a user, I want clearer evidence snippets for each issue so I can trust each finding.
3. As a user, I want faster scans on large repos via smarter sampling/limits without breaking rules.
4. As a user, I want deterministic results to be stable across runs so I can compare scans.
5. As a user, I want better guidance when imports fail so I can recover via zip upload.

### Implementation steps
- Improve similarity performance (chunking, hashing) while keeping correctness.
- Strengthen review-stage inference and overlapping responsibility heuristics; keep penalties/caps exact.
- PDF formatting: enforce page caps, stable tables, better summaries; verify redaction alias mapping.
- Improve Settings: validate keys, show last refresh timestamp/provenance; add “reset to defaults”.
- Add more test fixtures + regression tests around penalty caps and partial scan math.

### Next actions
- Address issues found by testing_agent_v3; refactor into modules once stable.

### Success criteria
- No major failures across the verification checklist; stable exports; edge-case imports handled; retention jobs verified.
