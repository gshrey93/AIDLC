# Bloat Guardian — Implementation Plan & Status

## Phase 1 — Core POC in isolation — COMPLETE (59/59 checks passed)

`/app/test_core.py`, run with `cd /app && python test_core.py`. Real network, real LLM, no mocks.

Proven:
- Real GitHub import of `github/awesome-copilot` (71 MB archive, 2215 files, 1445 parsed, 3.7M tokens)
- Real GitHub error paths: `GitHubRepoUnavailable`, `BranchNotFound`, `RepoTooLarge`
  (`torvalds/linux` = 6149 MB), non-GitHub URL rejection
- Real Bitbucket import of `tildeslash/monit` + `BitbucketRepoUnavailable`
- Zip import, `ZipCorrupted`, `ZipTooLarge`; markdown upload + `InsufficientData` with zeroed savings
- Analyzer: `ceil(chars/4)` verified against the raw file, all seven penalty rules verified against
  their caps, five integer category scores, weighted 25/25/20/20/10 overall verified arithmetically,
  verdict bands, `PartialScan` at 26.6% skipped, deterministic across repeated runs
- Detections: duplicate clusters, repeated instruction blocks, oversized context files, agent
  sprawl, 10 review stages, microservice mismatch, overlapping agent groups
- Savings: derived $4.00/1M input and $20.00/1M output from the owner pricing model, +/-20% range
- Real `claude-opus-4-7` drafts: `memory-optimised.md` 20,676 -> 215 tokens,
  `context-optimised.md` 15,766 -> 244 tokens
- Exports: full PDF (<= 40 pages), redacted PDF (<= 25 pages), CSV one row per issue, drafts zip,
  handoff zip with all five required files, HTML print fallbacks, and a redaction proof showing
  zero real paths leaked while aggregates are preserved

Engine lives at `/app/backend/core/`: `config.py`, `importer.py`, `classifier.py`, `similarity.py`,
`analyzer.py`, `drafts.py`, `exports.py`, `report.py`.

### Scoring finding worth remembering
The specified penalty caps alone put a floor of about 72 on the overall score, which makes the
`Wasteful` and `Critical` verdicts unreachable. A second, clearly labelled tier of severity-scaling
deductions was added so all four verdicts are reachable. Both tiers are itemised in the score
ledger and explained in the assumptions block.

---

## Phase 2 — Full app build — COMPLETE

### Backend (`/app/backend`)
`server.py` (API), `scanner.py` (7-stage background pipeline, on-demand drafting, retention),
`seed.py` (20 demo scans generated through the real analyzer), `settings_store.py`, `db.py`.

Endpoints: health/config/me/stats, scan create (multipart, all four sources), scan read, results,
files (paged + grouped), delete, on-demand draft, five export types, printable HTML views, export
preview, handoff package, settings read/write/reset, LLM-assisted rate refresh, admin seed and
retention.

### Frontend (`/app/frontend/src`)
Eight surfaces: landing, new scan, progress, results dashboard, exports, VS Code handoff, history,
settings. All states handled: queued, running with the seven named stages, completed,
`ImportFailed`, `ParseFailed`, `InsufficientData`, partial-scan warning, empty history, zero-issue
Lean result, export failure fallbacks, expired-content draft errors.

### Design
The user-supplied **DRL Brand Colors & Design System v2.1** supersedes the earlier internal design
brief. Implemented in `index.css`: full token set, DRL Purple primary with gradient CTAs and the
Navy-to-Purple navbar, Inter typography and type scale, 8px spacing grid, radius/shadow/z-index/
motion tokens, semantic tone tokens with dark-mode equivalents, Light/Dark/Auto toggle, reduced
motion, and A4 print styles.

### Testing
- Iteration 1 (backend + frontend): 28/31, no critical bugs.
- Iteration 2 (frontend interactions): 16/16 feature areas passed.
- Fixed from the reports: draft over-compression (minimum length relative to source, one retry,
  quality warning), theme toggle visibility at small widths, mobile horizontal overflow caused by
  grid items defaulting to `min-width: auto`.
- Bitbucket end-to-end path verified through the API after testing (238 files imported, correct
  `InsufficientData` outcome, all seven stages tracked).

---

## Phase 3 — Optional next steps (not started)

1. Private repository support via a stored, encrypted token (currently out of scope).
2. Scan-to-scan comparison so a user can prove an improvement after applying the drafts.
3. Richer duplicate evidence: inline diff between the members of a duplicate cluster.
4. Batch draft generation with a progress indicator for all 25 eligible files.
5. Saved assumption profiles, for example one per model vendor.
6. Regression fixtures pinning penalty-cap arithmetic and partial-scan maths.
