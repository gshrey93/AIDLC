
Action: file_editor create /app/README.md --file-text "# Bloat Guardian

Analyse an agentic coding repository for waste — duplicated agent instructions, oversized context
files, agent sprawl, review-loop overhead and architecture mismatch — and return a quantified,
plain-language efficiency verdict with AI-rewritten replacement files.

Single user. No authentication. Nothing is ever written back to your repository.

---

## 1. The prompt that went in

The build started from a full product specification for **Bloat Guardian**: a web app for Product
Owners, TPMs and individual builders that ingests a repository, classifies its agent assets, scores
five waste categories into a weighted 0–100 efficiency score, maps that to a verdict
(`Lean` / `Watchlist` / `Wasteful` / `Critical`), and exports shareable reports.

The spec fixed: the 7-stage scan pipeline, supported file extensions, agent-file naming and path
patterns, the token formula `ceil(chars/4)`, the five category weights (25/25/20/20/10), seven
penalty rules with hard caps, the `InsufficientData` and `PartialScan` rules, export formats and page
limits, redaction rules, the entity model, and 20 seeded demo scans.

Five clarifications were taken from the product owner before any code was written:

| # | Question | Decision |
|---|---|---|
| 1 | How are recommendation drafts produced? | AI rewrites of **existing** files via `claude-opus-4-7`, saved as `<name>-optimised.md`; user may supply their own key |
| 2 | Which import sources? | **All three**: GitHub, Bitbucket, and zip / `.md` upload |
| 3 | Savings maths | `$1 = 100 credits`; `1 credit = 2,500 input` **or** `500 output` tokens (output 5× input); values editable and refreshable |
| 4 | Seed data | Yes — 20 demo scans over 90 days |
| 5 | Repo access | **Real** unauthenticated public-repo import; no PAT stored |

A **DRL Brand Colors & Design System v2.1** document was supplied later and supersedes the initial
visual direction.

---

## 2. What we built

- **Core-first delivery.** The hardest part — import, scoring, LLM drafting, exports — was proven in
  isolation (`test_core.py`, **59/59 checks**, real network and real LLM) *before* any app code.
- **Four real import sources** with every specified error state.
- **Two-tier scoring.** Tier 1 is the seven specified capped rules. Tier 2 is a documented
  severity-scaling deduction based on the share of the monthly agent-context budget each category
  wastes. **Why:** the spec's caps put a floor of ~72 on the score, making `Wasteful` and `Critical`
  unreachable. Both tiers are itemised line-by-line in the in-app ledger and the PDF.
- **Eight surfaces**, light + dark mode, keyboard/contrast accessibility, A4 print styles.

---

## 3. Repository structure

```
/app
├── backend/
│   ├── server.py              FastAPI app, all /api routes
│   ├── scanner.py             7-stage background pipeline, on-demand drafts, retention
│   ├── seed.py                20 demo scans, generated through the REAL analyzer
│   ├── settings_store.py      provider/model/keys + savings assumptions
│   ├── db.py                  Mongo access + JSON serialisation helpers
│   ├── core/
│   │   ├── config.py          limits, patterns, weights, penalties, pricing defaults
│   │   ├── importer.py        GitHub / Bitbucket / zip / md import + error codes
│   │   ├── classifier.py      walk, classify, token estimate, inventory
│   │   ├── similarity.py      shingles, bottom-k sketch, LSH, union-find
│   │   ├── analyzer.py        detections, penalties, scores, issues, savings
│   │   ├── drafts.py          claude-opus-4-7 \"-optimised\" rewrites
│   │   ├── exports.py         PDF / CSV / zip / printable HTML
│   │   └── report.py          canonical report payload
│   ├── requirements.txt
│   └── .env                   MONGO_URL, DB_NAME, CORS_ORIGINS, EMERGENT_LLM_KEY
├── frontend/src/
│   ├── pages/                 Landing, NewScan, ScanProgress, ScanResults,
│   │                          ExportsPage, Handoff, History, SettingsPage, NotFound
│   ├── components/            AppShell, ThemeToggle, KpiTile, VerdictBadge,
│   │                          CategoryScoreCard, StageStepper, WarningBanner,
│   │                          IssuesTable, FileInventory, DraftPreview, ExportPanel,
│   │                          ResultsSections, AssumptionsEditor, DonutChart, ui/ (shadcn)
│   ├── lib/                   api.js (axios + endpoints), format.js (tokens, tones)
│   └── index.css              DRL design-system tokens, light/dark, print
├── test_core.py               isolated core proof (59 checks)
├── plan.md                    phased plan + status
├── memory/PRD.md              build record and decisions
└── test_reports/              testing-agent iteration reports
```

---

## 4. Getting started

Both services run under supervisor and hot-reload.

```bash
sudo supervisorctl status                      # backend, frontend, mongodb
sudo supervisorctl restart backend             # after .env or dependency changes
tail -n 50 /var/log/supervisor/backend.err.log
```

Open the app at the preview URL. On first boot the backend seeds 20 demo scans
(~10 s) — `GET /api/health` reports `seed.status`.

Run a scan: **New scan** → pick a source → paste a public repo URL or choose files → tick the rights
acknowledgement → **Start scan**.

Useful endpoints:

```bash
curl $URL/api/health
curl $URL/api/scans
curl $URL/api/scans/{id}/results
curl -X POST \"$URL/api/admin/seed?force=true\"   # regenerate demo data
```

---

## 5. Tests

```bash
cd /app && python test_core.py     # 59/59 — real GitHub, Bitbucket, LLM and exports
```

Covers: real imports and every error code, `ceil(chars/4)`, all seven penalty caps, the weighted
score arithmetic, verdict bands, `PartialScan`, `InsufficientData`, determinism across runs, two real
`claude-opus-4-7` drafts, and all five exports including a redaction leak check.

Testing-agent iterations are recorded in `test_reports/`: backend + frontend (28/31), frontend
interactions (16/16), post-refactor regression, and the `.md` upload fix. Refactor equivalence was
proven by re-classifying all 6,691 stored file records with zero category mismatches.

---

## 6. Libraries

**Backend** — FastAPI, Uvicorn, Motor/PyMongo, Pydantic, httpx (streamed archive download with size
guards), ReportLab (PDF), python-multipart, python-dotenv, `emergentintegrations` (LLM).
Similarity uses only the standard library (`zlib.crc32` shingles) so results are deterministic.

**Frontend** — React 19, react-router-dom, Tailwind CSS, shadcn/ui + Radix, lucide-react, axios,
sonner (toasts). The verdict donut is a dependency-free inline SVG.

---

## 7. Keys and environment

Never edit `MONGO_URL` or `REACT_APP_BACKEND_URL`.

| Variable | Where | Purpose |
|---|---|---|
| `MONGO_URL` | `backend/.env` | Mongo connection (preconfigured) |
| `DB_NAME` | `backend/.env` | Database name |
| `CORS_ORIGINS` | `backend/.env` | Allowed origins |
| `EMERGENT_LLM_KEY` | `backend/.env` | Universal key for `claude-opus-4-7` drafts |
| `REACT_APP_BACKEND_URL` | `frontend/.env` | API base (preconfigured) |

Optional, entered in **Settings** and stored server-side (returned masked, never echoed): your own
Anthropic / Gemini / OpenAI key, and a GitHub or Bitbucket token for higher import rate limits.
If the universal key runs out of budget the API returns **HTTP 402** with a plain-language message
telling you to top up or add your own key — the rest of the scan is unaffected.

---

## 8. Assets

No stock photography. The visual identity is CSS only: DRL Purple `#5225B4` with a Navy→Purple
navbar gradient, a restrained hero wash under 20% of the viewport, Inter for text and Courier New for
code and file paths. Icons are `lucide-react`. Seeded demo repositories are generated as real files
on disk so their drafts can still be produced on demand.

---

## 9. Assumptions

**Scoring.** Similarity is Jaccard overlap of 5-word shingles on normalised text (case- and
whitespace-insensitive); files under 200 characters are excluded. Tier 2 scaling exists because the
specified caps alone cannot reach the `Wasteful` or `Critical` bands.

**Savings.** Each agent asset is assumed loaded **200 times per month**; waste is treated as 90%
input / 10% output tokens; the aggregate range is ±20%. Derived from the owner's pricing model:
**$4.00 per 1M input tokens** and **$20.00 per 1M output tokens**. Two credit units are shown and
labelled separately: *report credits* (1 = 100,000 tokens, from the spec) and *vendor billing
credits* (100 = $1.00). Every value is editable; **Refresh rates** returns a model-reported
*suggestion with provenance* that you must explicitly apply — nothing is auto-applied, and it is not
a live billing feed.

**Limits and retention.** 1,500 files, 250 MB compressed, 5 MB per-file parse cap; imported content
kept 7 days, reports 30 days, your 10 most recent real scans retained (seeded demo scans exempt).

**Spec reconciliations.** The seed counts in the spec were internally inconsistent (source types
summed to 24 and verdicts to 22 against a 20-scan total); resolved as 12 GitHub / 4 zip / 4 markdown
= 20, and 17 completed + 1 `InsufficientData` + 1 `ImportFailed` + 1 `ParseFailed`. History shows all
retained scans with a \"last 10 only\" toggle so the retention rule and the 20-scan demo view coexist.

**Out of scope** (per the spec): multi-user, RBAC, PR write-back, in-place editing, private-repo auth,
SSO, payments, fine-tuning, and security/secret/licence scanning.
"
Observation: Overwrite successful: /app/README.md
