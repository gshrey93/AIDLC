# Bloat Guardian — PRD / build record

## What it is
A single-user web app that analyses agentic coding repositories for waste (duplicated agent
instructions, oversized context files, agent sprawl, review-loop overhead, architecture mismatch)
and returns a quantified, plain-language efficiency verdict plus AI-rewritten replacement files.

Audience: Product Owners, TPMs and individual builders. No authentication anywhere.

## Import sources (all real, no mocks)
| Source | Endpoint used | Verified with |
| --- | --- | --- |
| GitHub (public) | `api.github.com` metadata + `codeload.github.com` zip archive | `humanlayer/12-factor-agents` -> score 85 Lean; `github/awesome-copilot` (71 MB, 2215 files) |
| Bitbucket (public) | `api.bitbucket.org/2.0` metadata + `bitbucket.org/.../get/{ref}.zip` | `tildeslash/monit` -> 238 files, correctly `InsufficientData` |
| Zip upload | local extraction with path-traversal and zip-bomb guards | synthetic bloated repo + corrupted archive |
| `.md` upload | multi-file upload | 3 files -> `InsufficientData`; 7 files -> valid scan |

Error codes implemented and proven: `GitHubRepoUnavailable`, `GitHubRateLimited` (retry in 15 min),
`RepoTooLarge`, `BranchNotFound`, `BitbucketRepoUnavailable`, `BitbucketRateLimited`,
`ZipCorrupted`, `ZipTooLarge`, `ImportFailed`, `ParseFailed`, `InsufficientData`.

## Scoring model (two tiers, both itemised in the report)
**Tier 1 — the seven specified rules with hard caps**

| Rule | Points | Cap |
| --- | --- | --- |
| Near-duplicate agent/context pair, similarity >= 0.80 | -5 each | 32 |
| Repeated instruction block >= 150 chars in 3+ files | -4 each | 20 |
| Context/memory file over 8,000 estimated tokens | -6 each | 24 |
| Agent-like files above 12 | -2 each | 20 |
| Review/approval stages above 4 | -5 each | 15 |
| Microservice mismatch (>= 8 service dirs, < 120 source files) | -12 | 12 |
| Monolith mismatch (1 service, >= 10 overlapping agent roles) | -10 | 10 |

**Tier 2 — severity scaling.** Tier 1 alone makes any overall score below about 72 impossible,
which would leave the `Wasteful` and `Critical` verdicts unreachable. Tier 2 therefore deducts in
proportion to the share of the monthly agent context budget that each category wastes, up to a
per-category cap (redundancy 60, token bloat 60, review overhead 55, agent sprawl 60,
architecture 50). A category wasting 50% or more of the budget takes the full deduction. Every
Tier 2 row appears in the score ledger with a `tier: "scaling"` marker and its own explanation.

Weighted overall = 25% redundancy + 25% token bloat + 20% review overhead + 20% agent sprawl +
10% architecture. Verdict bands: Lean 80-100, Watchlist 60-79, Wasteful 40-59, Critical 0-39.

## Key rules honoured
- Token estimate `ceil(character_count / 4)`, shown in the report.
- Similarity = Jaccard overlap of 5-word shingles on normalised text (case- and whitespace-insensitive).
- Limits: 1,500 files, 250 MB compressed, 5 MB per-file parse cap.
- Fewer than 5 parsed text files -> `InsufficientData`, savings forced to zero, no verdict.
- More than 20% skipped -> `PartialScan` badge appended to the verdict.
- Rights acknowledgement checkbox blocks the scan until ticked (enforced client and server side).
- Retention: imported content 7 days, derived reports 30 days, 10 most recent real scans kept.

## Savings model (product-owner supplied)
- $1.00 = 100 vendor credits; 1 vendor credit = 2,500 input tokens or 500 output tokens.
- Derived: **$4.00 per 1M input tokens**, **$20.00 per 1M output tokens** (output is 5x input).
- Reporting credits: 1 credit = 100,000 tokens (spec ratio, separate from vendor billing credits).
- Waste assumed 90% input / 10% output; each agent asset loaded 200 times per month.
- Aggregate range shown at +/-20%.
- Every value editable in Settings, with an LLM-assisted "Refresh rates" action that returns a
  **suggestion plus provenance** which the user must explicitly apply. Nothing is auto-applied.

## Recommendation drafts
Rewrites of files that already exist in the repository, saved as `<stem>-optimised.md`. Only
agent, instruction, orchestration, context, memory and skill files are eligible — never source
code. Up to 25 per scan (5 written automatically, the rest on demand). Model: Anthropic
`claude-opus-4-7` via the platform universal key, swappable for a user-supplied Anthropic, Gemini
or OpenAI key in Settings. Output length is validated against the source and retried once if the
model over-compresses; a visible quality warning is attached if it is still unusually short.

## Surfaces
`/` landing, `/scan/new`, `/scan/:id/progress`, `/scan/:id`, `/scan/:id/exports`,
`/scan/:id/handoff`, `/history`, `/settings`.

## Exports
Full PDF (<= 40 pages), redacted PDF (<= 25 pages, path aliases and no contents), findings CSV
(one row per issue), drafts zip, VS Code handoff zip (`efficiency-summary.md`,
`recommended-instruction.md`, `recommended-orchestrator.md`, `recommended-context.md`,
`findings.csv`, plus `summary-prompt.txt` and a README). Fallbacks: printable HTML view for PDFs,
copy-to-clipboard for CSV.

## Seed data
20 demo scans across the last 90 days, generated by running the **real** analyzer over synthetic
repositories written to disk, so every number is internally consistent and drafts can still be
generated on demand. 12 GitHub, 4 zip, 4 markdown. 17 completed (3 Lean, 6 Watchlist, 5 Wasteful,
3 Critical) + 1 `InsufficientData` + 1 `ImportFailed` + 1 `ParseFailed`. At least one `PartialScan`.

## Design
Implements the user-supplied **DRL Brand Colors & Design System v2.1**: DRL Purple `#5225B4`
primary with the Navy-to-Purple navbar gradient, Inter typography, Courier New for code, the 8px
spacing grid, the documented radius/shadow/z-index/motion tokens, semantic colour tones, WCAG AA
contrast in both themes, a Light/Dark/Auto theme toggle persisted to localStorage, reduced-motion
support and A4 print styles.

## Out of scope (as specified)
Multi-user, RBAC, GitHub write-back or PRs, in-place file editing, private repo auth, SSO,
payments, real-time comments, fine-tuning, security/secret/license scanning, running imported code.
