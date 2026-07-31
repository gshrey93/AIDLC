{
  "product": {
    "name": "Bloat Guardian",
    "design_personality": [
      "credible and audit-friendly (numbers feel trustworthy)",
      "calm, analytical, not flashy",
      "plain-language first (grade-8 readability)",
      "high-density but breathable (progressive disclosure)",
      "single-user utility (no social/team cues)"
    ],
    "north_star": "Make it instantly obvious: how bad is the waste, what does it cost, why do we believe it, and what should we do next."
  },

  "brand_foundations": {
    "visual_style": {
      "layout_principles": [
        "Overview-first → drill-down via drawers/expanders (never cram)",
        "Numbers right-aligned; labels left-aligned",
        "Use calm neutrals for surfaces; reserve color for meaning (verdict/severity)",
        "Use subtle texture/noise only on large backgrounds (never on reading surfaces)",
        "Avoid centered marketing layouts; use editorial left alignment"
      ],
      "signature_motif": "‘Ledger’ aesthetic: thin dividers, subtle inset panels, and a ‘How calculated’ ledger block that looks like an audit trail.",
      "iconography": {
        "library": "lucide-react",
        "rules": [
          "Use 16–18px icons in dense UI; 20px in hero/KPI tiles",
          "Prefer outline icons; avoid filled icon sets",
          "Never use emoji icons"
        ]
      }
    },

    "typography": {
      "google_fonts": {
        "heading": {
          "family": "Space Grotesk",
          "weights": [500, 600, 700]
        },
        "body": {
          "family": "IBM Plex Sans",
          "weights": [400, 500, 600]
        },
        "mono": {
          "family": "IBM Plex Mono",
          "weights": [400, 500]
        }
      },
      "usage": {
        "headings": "Space Grotesk for all headings, KPI numbers, verdict labels.",
        "body": "IBM Plex Sans for paragraphs, table text, helper copy.",
        "code_and_paths": "IBM Plex Mono for file paths, formulas, token counts, evidence snippets."
      },
      "scale_tailwind": {
        "h1": "text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-tight",
        "h2": "text-base md:text-lg font-medium text-muted-foreground",
        "section_title": "text-lg font-semibold",
        "kpi_value": "text-2xl sm:text-3xl font-semibold tabular-nums",
        "table": "text-sm",
        "small": "text-xs text-muted-foreground"
      },
      "readability_rules": [
        "Default line-height: leading-6 for body; leading-5 for dense table cells",
        "Use tabular numbers for all numeric KPIs (tabular-nums)",
        "Plain-language summaries must avoid jargon; if a term is necessary, add a short tooltip definition"
      ]
    },

    "color_system": {
      "notes": [
        "No purple (explicit rule for AI apps).",
        "No dark/saturated gradients; gradients only as mild section accents and <20% viewport.",
        "All surfaces must have explicit backgrounds (no transparent-on-dark-text)."
      ],
      "palette_hex": {
        "graphite_950": "#0E1116",
        "graphite_900": "#141A22",
        "graphite_800": "#1F2937",
        "graphite_700": "#334155",
        "graphite_600": "#475569",
        "graphite_500": "#64748B",
        "sand_50": "#FBFAF7",
        "sand_100": "#F5F1E8",
        "sand_200": "#E9E2D3",
        "sand_300": "#D8CDB8",
        "teal_700": "#0F766E",
        "teal_600": "#0D9488",
        "teal_500": "#14B8A6",
        "teal_100": "#CCFBF1",
        "amber_600": "#D97706",
        "red_600": "#DC2626",
        "green_600": "#16A34A",
        "blue_600": "#2563EB"
      },
      "semantic_mapping": {
        "brand_accent": "teal_600",
        "background": "sand_50",
        "surface": "#FFFFFF",
        "surface_muted": "sand_100",
        "text": "graphite_950",
        "text_muted": "graphite_600",
        "border": "#E6E0D6",
        "focus_ring": "teal_500",
        "success": "green_600",
        "warning": "amber_600",
        "danger": "red_600",
        "info": "blue_600"
      },
      "verdict_colors": {
        "Lean": {"bg": "#ECFDF5", "fg": "#065F46", "border": "#A7F3D0"},
        "Watchlist": {"bg": "#FFFBEB", "fg": "#92400E", "border": "#FDE68A"},
        "Wasteful": {"bg": "#FFF7ED", "fg": "#9A3412", "border": "#FDBA74"},
        "Critical": {"bg": "#FEF2F2", "fg": "#991B1B", "border": "#FECACA"}
      },
      "severity_colors": {
        "Low": {"bg": "#EFF6FF", "fg": "#1D4ED8", "border": "#BFDBFE"},
        "Medium": {"bg": "#FFFBEB", "fg": "#92400E", "border": "#FDE68A"},
        "High": {"bg": "#FFF7ED", "fg": "#9A3412", "border": "#FDBA74"},
        "Critical": {"bg": "#FEF2F2", "fg": "#991B1B", "border": "#FECACA"}
      },
      "gradients_allowed": {
        "hero_only": {
          "css": "radial-gradient(1200px 600px at 20% 0%, rgba(20,184,166,0.14), transparent 55%), radial-gradient(900px 500px at 90% 10%, rgba(217,119,6,0.10), transparent 60%)",
          "rule": "Use only on landing hero background; keep content cards solid white."
        },
        "accent_divider": {
          "css": "linear-gradient(90deg, rgba(20,184,166,0.0), rgba(20,184,166,0.35), rgba(20,184,166,0.0))",
          "rule": "Use as a 1px decorative divider line under section headers."
        }
      },
      "noise_texture": {
        "approach": "CSS-only subtle noise overlay on page background (not on cards).",
        "css_snippet": ".bg-noise::before{content:'';position:fixed;inset:0;pointer-events:none;background-image:url('data:image/svg+xml;utf8,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"160\" height=\"160\"><filter id=\"n\"><feTurbulence type=\"fractalNoise\" baseFrequency=\"0.9\" numOctaves=\"3\" stitchTiles=\"stitch\"/></filter><rect width=\"160\" height=\"160\" filter=\"url(%23n)\" opacity=\"0.06\"/></svg>');mix-blend-mode:multiply;opacity:.35;}",
        "rule": "Only apply to body wrapper; never to tables/cards to preserve crispness."
      }
    },

    "design_tokens_css": {
      "where": "/app/frontend/src/index.css (override :root HSL tokens)",
      "tokens": {
        "--background": "40 33% 97%",
        "--foreground": "222 47% 7%",
        "--card": "0 0% 100%",
        "--card-foreground": "222 47% 7%",
        "--popover": "0 0% 100%",
        "--popover-foreground": "222 47% 7%",
        "--primary": "173 80% 32%",
        "--primary-foreground": "0 0% 100%",
        "--secondary": "40 33% 92%",
        "--secondary-foreground": "222 47% 12%",
        "--muted": "40 33% 92%",
        "--muted-foreground": "215 16% 35%",
        "--accent": "173 55% 92%",
        "--accent-foreground": "173 80% 18%",
        "--destructive": "0 72% 51%",
        "--destructive-foreground": "0 0% 100%",
        "--border": "38 24% 86%",
        "--input": "38 24% 86%",
        "--ring": "173 80% 40%",
        "--radius": "0.75rem"
      },
      "extra_css_vars": {
        "--shadow-sm": "0 1px 2px rgba(14,17,22,0.06)",
        "--shadow-md": "0 10px 30px rgba(14,17,22,0.10)",
        "--shadow-inset": "inset 0 1px 0 rgba(255,255,255,0.7)",
        "--grid-max": "1120px",
        "--content-max": "1280px"
      }
    }
  },

  "layout_and_grid": {
    "app_shell": {
      "pattern": "Top nav + content container; optional secondary subnav on results pages.",
      "container": "mx-auto w-full max-w-[var(--content-max)] px-4 sm:px-6 lg:px-8",
      "page_spacing": "py-6 sm:py-8",
      "section_spacing": "space-y-6 sm:space-y-8",
      "dense_panels": "Use Card with tighter padding: p-4 sm:p-5; tables inside use p-0 with header padding."
    },
    "results_dashboard_grid": {
      "top": "KPI strip: grid grid-cols-2 lg:grid-cols-6 gap-3",
      "middle": "Two-column: left (issues + drivers) / right (scores + detections) using lg:grid-cols-12 with gaps",
      "bottom": "Full-width tables and drafts with sticky subheaders"
    },
    "responsive_rules": [
      "Mobile-first: collapse KPI strip to 2 columns; tables become horizontally scrollable with ScrollArea",
      "Use Drawer/Sheet for filters on mobile; inline filter bar on desktop",
      "Avoid multi-column text on mobile; keep summaries single column"
    ]
  },

  "components": {
    "component_path": {
      "shadcn_primary": [
        "/app/frontend/src/components/ui/button.jsx",
        "/app/frontend/src/components/ui/card.jsx",
        "/app/frontend/src/components/ui/badge.jsx",
        "/app/frontend/src/components/ui/tabs.jsx",
        "/app/frontend/src/components/ui/table.jsx",
        "/app/frontend/src/components/ui/scroll-area.jsx",
        "/app/frontend/src/components/ui/dialog.jsx",
        "/app/frontend/src/components/ui/drawer.jsx",
        "/app/frontend/src/components/ui/sheet.jsx",
        "/app/frontend/src/components/ui/tooltip.jsx",
        "/app/frontend/src/components/ui/popover.jsx",
        "/app/frontend/src/components/ui/progress.jsx",
        "/app/frontend/src/components/ui/separator.jsx",
        "/app/frontend/src/components/ui/skeleton.jsx",
        "/app/frontend/src/components/ui/checkbox.jsx",
        "/app/frontend/src/components/ui/input.jsx",
        "/app/frontend/src/components/ui/textarea.jsx",
        "/app/frontend/src/components/ui/select.jsx",
        "/app/frontend/src/components/ui/sonner.jsx",
        "/app/frontend/src/components/ui/accordion.jsx",
        "/app/frontend/src/components/ui/collapsible.jsx",
        "/app/frontend/src/components/ui/resizable.jsx"
      ]
    },

    "button_system": {
      "style": "Professional / Corporate with slight softness",
      "radius": "rounded-xl",
      "variants": {
        "primary": {
          "tailwind": "bg-primary text-primary-foreground shadow-[var(--shadow-sm)] hover:bg-primary/90 focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))]",
          "use": "Primary CTAs: Start scan, Download, Apply filters"
        },
        "secondary": {
          "tailwind": "bg-secondary text-secondary-foreground hover:bg-secondary/80 border border-border",
          "use": "Secondary actions: Upload zip instead, View ledger"
        },
        "ghost": {
          "tailwind": "hover:bg-accent hover:text-accent-foreground",
          "use": "Row actions, icon buttons"
        },
        "danger": {
          "tailwind": "bg-destructive text-destructive-foreground hover:bg-destructive/90",
          "use": "Delete scan, destructive confirmations"
        }
      },
      "micro_interactions": {
        "press": "active:scale-[0.98]",
        "hover": "hover:shadow-[var(--shadow-sm)]",
        "transition": "transition-colors duration-150"
      }
    },

    "kpi_tile": {
      "name": "KpiTile",
      "structure": "Card → label + value + helper (delta or subtitle)",
      "tailwind": "rounded-xl border border-border bg-card shadow-[var(--shadow-sm)]",
      "value": "font-heading tabular-nums",
      "states": {
        "loading": "Skeleton lines",
        "clickable": "hover:bg-secondary/40 cursor-pointer"
      },
      "data_testids": [
        "kpi-overall-score",
        "kpi-estimated-monthly-dollar-waste",
        "kpi-files-scanned",
        "kpi-files-skipped"
      ]
    },

    "verdict_badge": {
      "name": "VerdictBadge",
      "use": "Always next to Overall Efficiency Score",
      "rules": [
        "If partial_scan true OR skipped_files/total_files > 0.2, append PartialScan badge",
        "Badge must be readable and not rely on color alone (include label text)"
      ],
      "implementation": "Use <Badge> with inline style mapping from verdict_colors",
      "data_testid": "verdict-badge"
    },

    "category_score_card": {
      "name": "CategoryScoreCard",
      "contents": [
        "Category label",
        "Score/100",
        "Weight %",
        "Penalty points",
        "1–2 sentence plain-language summary",
        "‘View ledger’ link opens Drawer to penalty_ledger filtered by category"
      ],
      "layout": "Card with header row + Progress bar",
      "progress": "Use shadcn Progress; color via CSS var on wrapper",
      "data_testid": "category-score-card"
    },

    "stage_stepper": {
      "name": "ScanStageStepper",
      "stages": [
        "Importing",
        "Extracting file tree",
        "Classifying files",
        "Estimating tokens or credits",
        "Running adversary scan",
        "Drafting recommendations",
        "Building reports"
      ],
      "pattern": "Horizontal on desktop; vertical list on mobile",
      "tailwind": {
        "container": "rounded-xl border border-border bg-card p-4",
        "step": "flex items-center gap-3",
        "dot": "h-2.5 w-2.5 rounded-full",
        "active": "bg-primary",
        "done": "bg-teal-600",
        "pending": "bg-muted",
        "failed": "bg-destructive"
      },
      "data_testid": "scan-stage-stepper"
    },

    "warning_banner": {
      "name": "PartialScanBanner",
      "use": "Show when skipped_files > 0",
      "copy": "Plain language: ‘Some files were skipped. Your score may be incomplete.’",
      "tailwind": "rounded-xl border border-amber-200 bg-amber-50 text-amber-900 p-4",
      "data_testid": "partial-scan-warning"
    },

    "issue_table": {
      "name": "IssuesTable",
      "performance": [
        "Up to ~900 rows: use pagination + filtering; avoid rendering huge markdown in cells",
        "Evidence shown via expandable row OR right-side Drawer (preferred)"
      ],
      "pattern": {
        "header": "Sticky header inside ScrollArea",
        "columns": [
          "Severity chip",
          "Category",
          "Title",
          "Impacted files",
          "Token waste",
          "Credit waste",
          "$ waste",
          "Actions (View evidence, Copy recommendation)"
        ],
        "row_expand": "Use Collapsible for inline 2–4 lines; full evidence in Drawer",
        "sorting": "Clickable header buttons with aria-sort",
        "filtering": "Desktop: inline filter bar; Mobile: Sheet filter panel"
      },
      "chips": {
        "severity": "Badge variant with severity_colors mapping",
        "impact_effort": "Two small badges: Impact (Low/Med/High) + Effort (Small/Med/Large)"
      },
      "data_testids": {
        "table": "issues-table",
        "filter": "issues-filter",
        "sort": "issues-sort",
        "row": "issues-row",
        "evidence_button": "issues-row-view-evidence-button"
      }
    },

    "evidence_drawer": {
      "name": "EvidenceDrawer",
      "component": "shadcn Drawer or Sheet (right side)",
      "contents": [
        "Issue title + severity",
        "Plain-language description",
        "Evidence (monospace block, copy button)",
        "Impacted files list (ScrollArea)",
        "Formula (monospace)"
      ],
      "data_testid": "evidence-drawer"
    },

    "file_inventory": {
      "name": "FileInventory",
      "pattern": "Tabs for 8 groups + Largest files table",
      "groups": [
        "Agents",
        "Skills",
        "Context and memory",
        "Prompt and orchestration",
        "Source code",
        "Diagrams",
        "Other text assets",
        "Docs"
      ],
      "table": "Use Table + ScrollArea; show parse_status and skip_reason",
      "data_testid": "file-inventory"
    },

    "savings_assumptions_panel": {
      "name": "SavingsAssumptionsPanel",
      "must_show": [
        "Token estimation formula: ceil(character_count / 4)",
        "Variance: ±20% range",
        "Editable rates + last refreshed timestamp + provenance"
      ],
      "pattern": "Card with editable Input fields; derived values in muted inset panel",
      "data_testid": "savings-assumptions"
    },

    "draft_preview": {
      "name": "DraftReplacementPreview",
      "pattern": "Resizable split view: Original vs Optimised",
      "components": ["Resizable", "Tabs", "ScrollArea"],
      "token_delta": "Show original_tokens, draft_tokens, reduction_pct as a small KPI strip",
      "actions": [
        "Copy draft",
        "Download drafts zip"
      ],
      "data_testid": "draft-preview"
    },

    "export_drawer": {
      "name": "ExportDrawer",
      "actions": [
        "Download full PDF",
        "Download redacted PDF",
        "Download CSV",
        "Download draft files zip"
      ],
      "fallbacks": [
        "If PDF fails: show HTML print view button",
        "If CSV fails: show copy-to-clipboard"
      ],
      "data_testid": "export-drawer"
    },

    "empty_states": {
      "rules": [
        "Always explain what happened and what to do next",
        "Use one primary CTA and one secondary CTA",
        "Never blame the user; keep copy calm"
      ],
      "examples": {
        "zero_issues": "‘No major waste detected. Keep your repo lean by consolidating instructions quarterly.’",
        "empty_history": "‘No scans yet. Run your first scan from GitHub or upload a zip.’"
      }
    }
  },

  "page_blueprints": {
    "routes": {
      "/": {
        "layout": [
          "Top nav (logo left, Settings + History right)",
          "Hero: H1 + H2 + 2 CTAs (Scan GitHub, Upload Zip)",
          "Example metrics row (4 KPI tiles)",
          "How it works (3 steps) + privacy note",
          "Footer (minimal)"
        ],
        "cta_testids": {
          "github": "landing-scan-github-button",
          "zip": "landing-upload-zip-button"
        }
      },
      "/scan/new": {
        "layout": [
          "Page header: New scan",
          "Tabs: GitHub | Bitbucket | Zip upload | .md upload",
          "Inputs with live validation + helper text",
          "Rights checkbox (required)",
          "Start scan button (disabled until valid)",
          "Failure fallback card: ‘Upload a zip instead’ (preserve settings)"
        ],
        "testids": {
          "source_tabs": "scan-source-tabs",
          "repo_url": "scan-repo-url-input",
          "branch": "scan-branch-input",
          "zip_picker": "scan-zip-picker",
          "md_picker": "scan-md-picker",
          "rights_checkbox": "scan-rights-checkbox",
          "start": "scan-start-button"
        }
      },
      "/scan/:id/progress": {
        "layout": [
          "Header: Repo name + branch + status chip",
          "Stage stepper (7 stages)",
          "Live KPI strip (files discovered/parsed/skipped, agent-like files, tokens analyzed)",
          "Log panel (monospace) for errors and retries",
          "Terminal states: ImportFailed / ParseFailed / InsufficientData with recovery CTAs"
        ],
        "testids": {
          "kpis": "scan-progress-kpis",
          "error_state": "scan-progress-error-state",
          "fallback_zip": "scan-progress-upload-zip-fallback"
        }
      },
      "/scan/:id": {
        "layout": [
          "Sticky top summary bar: Overall score + VerdictBadge + PartialScan badge + Export button",
          "KPI strip (6 tiles)",
          "Category score cards (5) in a 2-column grid",
          "Top 5 waste drivers (ranked list)",
          "IssuesTable with filters + EvidenceDrawer",
          "FileInventory tabs + Largest files",
          "Skipped files panel + reasons",
          "Savings assumptions (editable) + ledger",
          "Recommended actions ranked",
          "Draft preview split view"
        ],
        "testids": {
          "export": "results-export-button",
          "ledger": "results-score-ledger",
          "drivers": "results-top-drivers",
          "recommended_actions": "results-recommended-actions",
          "drafts": "results-draft-previews"
        }
      },
      "/scan/:id/exports": {
        "layout": [
          "Export actions card (4 buttons)",
          "Preview panel: included sections + redaction rules",
          "Failure fallback actions"
        ],
        "testids": {
          "download_full_pdf": "export-download-full-pdf",
          "download_redacted_pdf": "export-download-redacted-pdf",
          "download_csv": "export-download-csv",
          "download_drafts_zip": "export-download-drafts-zip",
          "print_fallback": "export-print-fallback"
        }
      },
      "/history": {
        "layout": [
          "Header + verdict distribution mini chart",
          "History table (20 seeded demo scans + real)",
          "Row actions: Open, Download report, Delete (confirm dialog)"
        ],
        "chart": {
          "library": "recharts",
          "component": "small stacked bar or donut",
          "data_testid": "history-verdict-distribution"
        },
        "testids": {
          "history_table": "history-table",
          "delete": "history-delete-scan-button"
        }
      },
      "/scan/:id/handoff": {
        "layout": [
          "Card: What this is",
          "Copy summary prompt (Textarea + Copy button)",
          "Download handoff package",
          "Open locally in VS Code (vscode://) + manual instructions fallback"
        ],
        "testids": {
          "copy_prompt": "handoff-copy-prompt-button",
          "download": "handoff-download-package-button",
          "open_vscode": "handoff-open-vscode-button"
        }
      },
      "/settings": {
        "layout": [
          "Provider/model selector",
          "API key inputs (Anthropic/Gemini) with show/hide",
          "GitHub PAT input",
          "Savings assumptions editor + Refresh rates button + provenance"
        ],
        "testids": {
          "provider_select": "settings-provider-select",
          "model_select": "settings-model-select",
          "api_key": "settings-api-key-input",
          "github_pat": "settings-github-pat-input",
          "refresh_rates": "settings-refresh-rates-button"
        }
      }
    }
  },

  "motion_and_microinteractions": {
    "principles": [
      "Motion should clarify state changes (filters applied, drawer opened, scan stage advanced)",
      "Keep durations short: 120–180ms for UI, 220–280ms for drawers",
      "Respect prefers-reduced-motion"
    ],
    "allowed_transitions": [
      "transition-colors",
      "transition-shadow",
      "transition-opacity"
    ],
    "patterns": {
      "drawer": "ease-out duration-250",
      "table_row_hover": "bg-secondary/40",
      "kpi_tile_hover": "shadow increases slightly; no transform on large grids",
      "copy_action": "Use sonner toast: ‘Copied to clipboard’"
    }
  },

  "accessibility": {
    "requirements": [
      "WCAG AA contrast for all text",
      "Keyboard navigable tabs, tables, drawers",
      "Visible focus ring on all interactive elements",
      "Do not rely on color alone for verdict/severity (always include text label)",
      "Use aria-label for icon-only buttons"
    ],
    "table_a11y": [
      "Use <button> for sortable headers",
      "Use aria-sort on active sort column",
      "Ensure expandable rows are reachable and togglable via keyboard"
    ]
  },

  "libraries": {
    "recommended": [
      {
        "name": "recharts",
        "why": "Verdict distribution on History + small category radar/stacked bars if needed",
        "install": "npm i recharts",
        "usage_note": "Keep charts minimal; always pair with a plain-language caption."
      },
      {
        "name": "framer-motion",
        "why": "Optional: animate stepper stage changes and drawer entrance (respect reduced motion)",
        "install": "npm i framer-motion",
        "usage_note": "Use only for 2–3 key interactions; avoid animating large tables."
      }
    ]
  },

  "image_urls": {
    "policy": "Prefer no stock photos for credibility; use subtle abstract textures only (CSS noise).",
    "landing": [
      {
        "category": "hero",
        "description": "No photo. Use mild radial gradient + noise overlay behind hero only.",
        "url": null
      }
    ]
  },

  "instructions_to_main_agent": [
    "Remove CRA default App.css centering/dark header styles; rely on Tailwind + tokens.",
    "Override :root tokens in index.css to match the sand/graphite/teal system.",
    "Implement all pages in .js (not .tsx).",
    "Every interactive element and key informational element must include data-testid in kebab-case.",
    "Use shadcn/ui components from /src/components/ui; do not use raw HTML dropdowns/calendars/toasts.",
    "Use Drawer/Sheet for evidence and filters; keep main dashboard readable.",
    "Show formulas and assumptions in a dedicated ‘ledger’ panel; keep summaries grade-8 plain language.",
    "Do not use universal transitions (no transition-all)."
  ]
}

<General UI UX Design Guidelines>  
    - You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms
    - You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text
   - NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json

 **GRADIENT RESTRICTION RULE**
NEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc
NEVER use dark gradients for logo, testimonial, footer etc
NEVER let gradients cover more than 20% of the viewport.
NEVER apply gradients to text-heavy content or reading areas.
NEVER use gradients on small UI elements (<100px width).
NEVER stack multiple gradient layers in the same viewport.

**ENFORCEMENT RULE:**
    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors

**How and where to use:**
   • Section backgrounds (not content backgrounds)
   • Hero section header content. Eg: dark to light to dark color
   • Decorative overlays and accent elements only
   • Hero section with 2-3 mild color
   • Gradients creation can be done for any angle say horizontal, vertical or diagonal

- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc**

</Font Guidelines>

- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead. 
   
- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.

- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.
   
- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly
    Eg: - if it implies playful/energetic, choose a colorful scheme
           - if it implies monochrome/minimal, choose a black–white/neutral scheme

**Component Reuse:**
	- Prioritize using pre-existing components from src/components/ui when applicable
	- Create new components that match the style and conventions of existing components when needed
	- Examine existing components to understand the project's component patterns before creating new ones

**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `/app/frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component

**Best Practices:**
	- Use Shadcn/UI as the primary component library for consistency and accessibility
	- Import path: ./components/[component-name]

**Export Conventions:**
	- Components MUST use named exports (export const ComponentName = ...)
	- Pages MUST use default exports (export default function PageName() {...})

**Toasts:**
  - Use `sonner` for toasts"
  - Sonner component are located in `/app/src/components/ui/sonner.tsx`

Use 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals.
</General UI UX Design Guidelines>
