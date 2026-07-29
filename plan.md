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

---

## Phase 4 — Repository series, run history and archive (Status: COMPLETED)

### Data model
`repo_series` is a new collection. A series is keyed on `source_type + owner + repo_name + branch`,
so `main` and `develop` on the same repository are two independent rows. Zip and markdown uploads
have no owner or branch, so they key on the uploaded file name: uploading `myday-2.0.zip` twice
appends a second run instead of creating a second row.

Every scan is now a *run* on a series. `scans` gained `series_id`, `series_key`, `run_number`,
`previous_score` and `score_delta`. `series.py` owns the logic: `attach_scan` binds a run (and
moves it if the branch is only resolved after the import), `recompute_series` renumbers runs and
refreshes the rolled-up columns, and `backfill` is the idempotent migration.

The migration ran on startup and attached all 24 pre-existing scans to 24 series, 20 of them the
seeded demo series which start archived. `/api/scans/{id}` and every export link are unchanged.

The old "keep only the last 10 real scans" pruning rule was removed. Content retention (7 days)
and metadata retention (30 days) are unchanged.

### API
`GET /api/series`, `GET /api/series/{id}`, `PATCH /api/series/{id}/archive`,
`DELETE /api/series/{id}` (deletes the series and all of its runs), `POST /api/series/backfill`
and `GET /api/series/export/archive`. The archive export is a zip holding the full PDF and
findings CSV for the latest completed run of every archived series, plus `manifest.csv`,
`README.txt` and `generated-at.txt`.

### History page
One row per repository: latest score, verdict, run count, delta versus the previous run and the
last run time. Expanding a row lists every run with its own score, delta and verdict. Search by
repository, owner or branch, and five sort orders. Archiving is per series, with the archive in a
collapsible section that carries the bundle download. Deleting works at both levels: a single run,
or the whole repository.

### Validation
`myday-2.0.zip` was uploaded twice. Both runs landed on one series (`myday-2.0`, 2 runs) rather
than two history rows. To prove the delta arithmetic rather than just the append, run 2 used a
variant with 12 duplicated agent files: score moved 79 -> 55, verdict Watchlist -> Wasteful,
delta -24.

### Bug found and fixed during validation
`_walk_repository` excluded any directory starting with `.git`, which silently swallowed
`.github/`. That is where `copilot-instructions.md`, `agents/*.agent.md` and `prompts/*.prompt.md`
live, so the 24 agent files in the user's own repository were invisible and it scored a misleading
100 / Lean. Only the literal `.git` object store is dropped now. The same repository scans as
82 files / 79 / Watchlist. `test_core.py` still passes 59/59.

### Two further fixes from validation
1. Markdown uploads all carried the fixed name `markdown-upload`, so every unrelated `.md` batch
   collapsed into one series. The series name now comes from the uploaded file set (single file
   name, or `first +N more (hash)`), so re-uploading the same set appends a run while a different
   set starts its own series. Verified both ways.
2. `backend_test.py` counted raw CSV lines, which over-reports records because evidence fields
   contain quoted newlines (41 issues read as 103 rows). It now uses `csv.DictReader`.

### Known non-code issue
`test_core.py` is at 56/59: the three failures are all LLM draft checks and the provider reports
"Budget has been exceeded! Current cost 42.48, max budget 41.0". The Universal Key needs a top-up
(Profile > Universal Key > Add Balance), or a personal Anthropic/Gemini key in Settings. The app
already surfaces this as an HTTP 402 with a plain-language message; nothing else is affected.
