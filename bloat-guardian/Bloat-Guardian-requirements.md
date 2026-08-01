# Bloat Guardian — Requirements Document

## 1. Introduction

### 1.1 Purpose
Bloat Guardian is a web application that helps Product Owners, Technical Program Managers (TPMs), and individual builders analyze agentic coding repositories. It identifies and quantifies waste from token bloat, duplicated agent instructions, oversized context files, and review inefficiency, then returns a quantified, plain-language efficiency verdict with actionable savings recommendations.

### 1.2 Scope
Defines the requirements for Bloat Guardian v1.0.

### 1.3 Out of Scope
- Multi-user collaboration and team workspaces
- Role-based permissions beyond a single user
- Direct GitHub/Bitbucket write-back or pull request creation
- Direct file editing inside VS Code / in-place code modification
- Private GitHub/Bitbucket repository authentication
- SSO / OAuth beyond the minimum needed for public repo import
- Payment processing, subscriptions, billing
- Real-time collaborative comments
- Model fine-tuning
- Source code quality linting unrelated to agentic efficiency
- Security auditing, secret/license scanning, dependency vulnerability analysis
- Running arbitrary code from imported repositories
- Native desktop or mobile applications

## 2. Identity & Context
A single-user web app for Product Owners, TPMs, and individual builders to analyze agentic coding repositories for waste, token bloat, duplicated agent instructions, oversized context files, and review inefficiency, returning a quantified, plain-language efficiency verdict with actionable savings recommendations.

## 3. Core Flow (7 Stages)

### 3.1 Stage 1: Intake
Start a new scan from one of four sources:
- **GitHub repository import** (public repo URL)
- **Bitbucket repository import** (public repo URL)
- **Zip upload** (`.zip` archive)
- **File upload** (`.md` files)

**Constraints:** Up to 1,500 files or 250 MB compressed, whichever is hit first.

**Supported file types:** `.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.mmd`, `.ts`, `.tsx`, `.js`, `.jsx`, `.py`, `.go`, `.java`, `.rb`, `.rs`, `.cs`

**Agent-file classification (by filename/path):** `*.agent.md`, `instruction.md`, `instructions.md`, `orchestrator.md`, `workflow.md`, `context.md`, `prompt.md`, `memory.md`, `system.md`; directories `/agents/`, `/skills/`, `/prompts/`, `/context/`, `/memory/`

### 3.2 Stage 2: Repository Parsing
- Extract repo tree, file metadata (sizes, line counts, token estimates), and path categories
- Build file inventory grouped into: Agents, Skills, Context & Memory, Prompt & Orchestration, Source code, Diagrams, Other text assets, Docs
- Mark file status: `Scanned`, `Skipped`, `Unsupported`, `Binary`, `Oversized`
- Skip content parsing for any single file > 5 MB (still include metadata)
- If archive extraction fails, stop scan and show `ImportFailed`

### 3.3 Stage 3: Adversary Scan
Run heuristic analysis across 5 categories: **Redundancy, Token bloat, Review overhead, Agent sprawl, Architecture inefficiency.**

Detects and quantifies:
- Near-duplicate files by text similarity
- Repeated instruction blocks across agent/context files
- Oversized context files
- Overlapping agent responsibilities
- Excessive orchestration layers
- Excessive/repetitive skills files
- Monolith vs. microservice mismatch signals
- Review loop overhead

**Output:** Issue records with severity, evidence, impacted files, estimated token waste, estimated credit waste.

### 3.4 Stage 4: Verdict Generation
- Weighted overall efficiency score 0–100
- Verdict enum: `Lean` (80–100), `Watchlist` (60–79), `Wasteful` (40–59), `Critical` (0–39)
- Summarize top 5 waste drivers in non-technical language
- Show transparent savings assumptions and formulas

### 3.5 Stage 5: Recommendation Drafting
- Per issue: Impact (`Low`/`Medium`/`High`), Effort (`Small`/`Medium`/`Large`), estimated token/credit reduction, estimated dollar savings
- Draft replacement content for up to 25 files: `instruction.md`, `instructions.md`, `orchestrator.md`, `context.md`, `memory.md`
- Drafts copyable in-app and downloadable as `.zip`

### 3.6 Stage 6: Share & Export
- Download updated `.md` files for agent/skills/instructions
- Download full report PDF / redacted report PDF
- Download findings CSV
- Download recommendation drafts `.zip`

**Redacted report:** removes file contents, replaces exact names with path aliases, preserves counts/score/category findings/savings estimates.

### 3.7 Stage 7: History
- Store last 10 scans for the single user
- Show: scan date, source, repo name, branch, overall score, verdict, files scanned, files skipped, estimated savings

## 4. Rules

### 4.1 General
- Single-user app (no team workspace behavior)
- Valid scan requires ≥ 5 successfully parsed text files
- If < 5 parsed, mark `InsufficientData` and do not calculate savings

### 4.2 Token Estimation
- `tokens = ceil(character_count / 4)` — formula must be displayed in the report

### 4.3 Overall Score Weighting
- Redundancy 25% · Token bloat 25% · Review overhead 20% · Agent sprawl 20% · Architecture inefficiency 10%

### 4.4 Category Scores
- Integers 0–100

### 4.5 Score Penalties
| Condition | Penalty | Cap/Scan |
|---|---|---|
| Near-duplicate agent/context pair (similarity ≥ 0.80) | −5 each | 32 |
| Repeated instruction block ≥ 150 chars in ≥ 3 files | −4 each | 20 |
| Context/memory file > 8,000 tokens | −6 each | 24 |
| > 12 agent-like files | −2 per extra file | 20 |
| > 4 review/approval stages | −5 | 15 |
| Service dirs ≥ 8 AND non-generated source files < 120 (microservice mismatch) | −12 | — |
| 1 service dir AND ≥ 10 overlapping agent role files (monolith mismatch) | −10 | — |

### 4.6 Near-Duplicate Detection
- Normalized text similarity on supported text files; ignore whitespace-only and case-only differences

### 4.7 Oversized File Handling
- If > 5 MB: do not parse, mark `SkippedOversized`, include path/size/reason in report

### 4.8 Unsupported File Handling
- Unsupported extension → mark `SkippedUnsupported`

### 4.9 Partial Scan Handling
- If ≥ 1 file skipped, show warning banner with count and reasons
- If > 20% skipped, append `PartialScan` badge to final verdict

### 4.10 Savings Model
- Estimate monthly token waste per issue using issue-specific formulas
- Convert to credits at configurable default: 1 credit / 100,000 tokens
- Show both token and credit estimates with assumptions
- Aggregate savings shown as low/high range using ±20% variance

### 4.11 Recommendation Generation
- Only draft replacements for agent/orchestration/instruction/context/memory files
- Never draft replacements for source code files

### 4.12 Plain-Language Rule
- Finding summaries readable at ~grade 8 level; avoid unexplained jargon in summary cards

### 4.13 Download Rules
- Full report PDF ≤ 40 pages · Redacted PDF ≤ 25 pages · CSV = one row per issue

### 4.14 Data Retention
- Uploaded zip / imported repo content: max 7 days
- Derived scan metadata and reports: 30 days

### 4.15 Privacy Warnings
- Pre-import checkbox: "I confirm I have the right to analyze this repository content" — must be checked before scan starts

## 5. Roles & Access
Single role: **User**. Can connect a GitHub or Bitbucket repo, upload `.zip` or `.md`, start/view/delete scans, view findings and drafts, download full/redacted/CSV reports, trigger VS Code handoff, and see skipped-file warnings and partial-scan status.

## 6. Surfaces

### 6.1 Landing Page
- Explains what the app analyzes; CTAs: **Scan a GitHub Repo**, **Scan a Bitbucket Repo**, **Upload Repo Zip**
- 4 static example metrics: redundant files found, estimated token/credit waste, estimated dollar waste, recommended files to consolidate

### 6.2 New Scan Page
- Source selector: GitHub / Bitbucket / Zip Upload / File Upload
- GitHub: repo URL + optional branch · Bitbucket: repo URL + optional branch · Zip: `.zip` picker · File: `.md` picker
- Rights acknowledgment checkbox + Start button
- **Validations:** GitHub URL matches `https://github.com/{owner}/{repo}`; Bitbucket URL matches `https://bitbucket.org/{workspace}/{repo}`; zip must be `.zip` and ≤ 250 MB; Start disabled until valid and checkbox checked

### 6.3 Scan Progress Page
- Stages: Importing → Extracting file tree → Classifying files → Estimating tokens/credits → Running adversary scan → Drafting recommendations → Building reports
- KPIs: files discovered, files parsed, files skipped, agent-like files detected, estimated tokens analyzed
- Failure states: `ImportFailed`, `ParseFailed`, `InsufficientData`

### 6.4 Scan Results Dashboard
- **Top KPIs:** overall score, verdict, monthly token/credit waste, monthly dollar waste, savings range, files scanned, files skipped, duplicate clusters, oversized context files, overlapping agent groups, review stages inferred
- **Category cards:** redundancy, token bloat, review overhead, agent sprawl, architecture inefficiency
- **Sections:** top 5 waste drivers, issue table, file inventory by category, skipped files & warnings, savings assumptions, ranked recommended actions, draft replacement file previews

### 6.5 Report Export Page/Drawer
- Actions: full PDF, redacted PDF, CSV, draft files zip
- Preview: included sections, redaction rules, file/issue counts

### 6.6 Scan History Page
- Columns: scan date, source type, repo name, branch, overall score, verdict, files scanned, files skipped, estimated monthly credit savings
- Actions: Open, Download report, Delete

### 6.7 VS Code Handoff Page
- Actions: copy summary prompt, download handoff package, open local VS Code via generated files + URI instructions
- Package contents: `efficiency-summary.md`, `recommended-instruction.md`, `recommended-orchestrator.md`, `recommended-context.md`, `findings.csv`

## 7. Integrations

### 7.1 GitHub Import (public repos, v1)
- Input: repo URL + optional branch; fetch archive and metadata
- Errors: `GitHubRepoUnavailable`, `GitHubRateLimited`, `RepoTooLarge` (> 250 MB), `BranchNotFound`
- Fallback: offer manual zip upload on any failure

### 7.2 Bitbucket Import (public repos, v1)
- Input: repo URL + optional branch; fetch archive and metadata
- Errors: `BitbucketRepoUnavailable`, `BitbucketRateLimited`, `RepoTooLarge` (> 250 MB), `BranchNotFound`
- Fallback: offer manual zip upload on any failure

### 7.3 VS Code Handoff
- No in-place editing in v1; generate local export package + "Open in VS Code" helper
- Fallback: manual instructions + always-available downloadable package

### 7.4 File Upload
- Accepts `.zip` or `.md` only
- Errors: `ZipCorrupted`, `ZipTooLarge` (> 250 MB)
- Fallback: re-upload without losing scan settings

### 7.5 PDF & CSV Export
- PDF failure → HTML print view · CSV failure → issue table copy-to-clipboard

## 8. Data Model

**User:** id, created_at, display_name

**Scan:** id (`SCN-YYYY-mm-dd-0001`), user_id, source_type (`github`/`bitbucket`/`zip`), repo_name, repo_owner?, branch?, status (`queued`/`running`/`completed`/`ImportFailed`/`ParseFailed`/`InsufficientData`), total_files, parsed_files, skipped_files, analyzed_tokens, overall_score, verdict (`Lean`/`Watchlist`/`Wasteful`/`Critical`), partial_scan, estimated_monthly_token_waste, estimated_monthly_dollar_waste, estimated_savings_low, estimated_savings_high, created_at, completed_at

**FileAsset:** id, scan_id, path, extension, category (`agent`/`skill`/`context_memory`/`orchestration`/`source`/`diagram`/`other`), size_bytes, line_count, estimated_tokens, parse_status (`Scanned`/`SkippedOversized`/`SkippedUnsupported`/`Binary`/`ParseError`), similarity_group?

**CategoryScore:** id, scan_id, category (`redundancy`/`token_bloat`/`review_overhead`/`agent_sprawl`/`architecture_inefficiency`), score, penalty_points, summary

**Issue:** id (`ISS-YYYY-mm-dd-0001`), scan_id, severity (`low`/`medium`/`high`/`critical`), category, title, description, evidence, impacted_file_count, estimated_token_waste, estimated_credit_waste, recommendation

**RecommendationDraft:** id, scan_id, target_filename, target_type (`instruction`/`orchestrator`/`context`/`memory`), impact (`Low`/`Medium`/`High`), effort (`Small`/`Medium`/`Large`), draft_content

**ExportJob:** id, scan_id, export_type (`pdf_full`/`pdf_redacted`/`csv`/`draft_zip`), status (`queued`/`completed`/`failed`), created_at

### 8.1 Seed Data
- 1 demo user
- 20 scans (18 completed, 2 failed) over last 90 days
- Realistic names: `agentic-crm`, `support-copilot`, `proposal-writer`, `multi-agent-ops`, `sow-estimator`, `customer-onboarding-bot`
- Source mix: 10 GitHub, 4 Bitbucket, 4 zip, 2 `.md`
- Verdict mix: 3 Lean, 7 Watchlist, 8 Wasteful, 4 Critical, 2 failed
- Per completed scan: 40–900 total files, 12–180 parsed, 0–140 skipped, 20k–1.8M tokens, 4–60 issues, 0–10 drafts
- Seeded patterns: duplicate `*.agent.md` clusters (≥8 scans), oversized `context.md` >8k tokens (≥10), review chains 5–7 steps (≥6), microservice mismatch (≥4)
- At least 1 `PartialScan` and 1 `InsufficientData` scan

## 9. Verification Checklist
1. Seed data creates 20 scans over 90 days on history page
2. GitHub scan: valid URL, invalid URL, non-existent branch, >250 MB failure path
3. Bitbucket scan: valid URL, invalid URL, non-existent branch, >250 MB failure path
4. Zip scan: valid, corrupted, >250 MB failure path; `.md` file upload valid
5. Progress updates through all 7 stages; completed scan shows score, verdict, 5 category scores, issue table, skipped warnings, savings assumptions, draft content
6. `PartialScan` badge when >20% skipped; `InsufficientData` blocks savings
7. Full PDF, redacted PDF, CSV, draft zip exports work; fallbacks (HTML print, copy-to-clipboard) functional
8. VS Code handoff package downloads with all 5 files; local-open fallback instructions appear when URI launch unsupported
9. Deleting a scan removes it from history
10. Full end-to-end single-user flow from import to export passes