"""Central configuration, enums, limits, patterns and default assumptions.

Everything that drives the deterministic scoring lives here so the report can
show transparent formulas.
"""
from __future__ import annotations

# ---------------------------------------------------------------- limits
MAX_ARCHIVE_BYTES = 250 * 1024 * 1024          # 250 MB compressed
MAX_FILES = 1500                                # repository file cap
MAX_PARSE_FILE_BYTES = 5 * 1024 * 1024          # 5 MB single-file parse cap
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024  # zip-bomb guard
MIN_TEXT_FILES_FOR_VALID_SCAN = 5
PARTIAL_SCAN_SKIP_RATIO = 0.20

# ------------------------------------------------------------ extensions
SOURCE_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".java", ".rb", ".rs", ".cs"}
DIAGRAM_EXTENSIONS = {".mmd"}
DATA_EXTENSIONS = {".json", ".yaml", ".yml"}
DOC_EXTENSIONS = {".md", ".txt"}
SUPPORTED_EXTENSIONS = SOURCE_EXTENSIONS | DIAGRAM_EXTENSIONS | DATA_EXTENSIONS | DOC_EXTENSIONS

# Directories that are never meaningful for agentic-efficiency analysis.
IGNORED_DIR_PARTS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".next", ".nuxt", ".turbo", ".idea", ".vscode-test",
}
GENERATED_PATH_MARKERS = (
    "node_modules/", "/dist/", "/build/", "/vendor/", "/.min.", "/generated/",
    "__pycache__/", "/migrations/", "/coverage/", ".generated.", "/__generated__/",
)

# ------------------------------------------------- agent-related patterns
# Exact filenames that mark orchestration / instruction assets.
ORCHESTRATION_FILENAMES = {
    "instruction.md", "instructions.md", "orchestrator.md", "workflow.md",
    "prompt.md", "prompts.md", "orchestration.md", "workflows.md", "pipeline.md",
}
AGENT_FILENAMES = {"agent.md", "agents.md", "system.md", "claude.md", "agents.yaml", "agent.yaml"}
CONTEXT_FILENAMES = {"context.md", "memory.md", "contexts.md", "memories.md", "knowledge.md"}
SKILL_FILENAMES = {"skill.md", "skills.md"}

# Path fragments (spec list)
AGENT_DIR_PARTS = ("/agents/", "/agent/", "/subagents/")
SKILL_DIR_PARTS = ("/skills/", "/skill/")
CONTEXT_DIR_PARTS = ("/context/", "/memory/", "/contexts/", "/memories/")
ORCHESTRATION_DIR_PARTS = ("/prompts/", "/prompt/", "/orchestration/", "/workflows/", "/chatmodes/", "/instructions/")

# Suffix patterns
AGENT_SUFFIXES = (".agent.md", ".agent.yaml", ".agent.yml", ".chatmode.md", ".subagent.md")
SKILL_SUFFIXES = (".skill.md",)
CONTEXT_SUFFIXES = (".context.md", ".memory.md")
ORCHESTRATION_SUFFIXES = (".instructions.md", ".instruction.md", ".prompt.md", ".workflow.md", ".orchestrator.md")

CATEGORY_AGENT = "agent"
CATEGORY_SKILL = "skill"
CATEGORY_CONTEXT = "context_memory"
CATEGORY_ORCHESTRATION = "orchestration"
CATEGORY_SOURCE = "source"
CATEGORY_DIAGRAM = "diagram"
CATEGORY_OTHER = "other"

AGENT_LIKE_CATEGORIES = (CATEGORY_AGENT, CATEGORY_SKILL, CATEGORY_CONTEXT, CATEGORY_ORCHESTRATION)

INVENTORY_GROUPS = [
    "Agents", "Skills", "Context and memory", "Prompt and orchestration",
    "Source code", "Diagrams", "Docs", "Other text assets",
]

# ---------------------------------------------------- scoring parameters
CATEGORY_WEIGHTS = {
    "redundancy": 0.25,
    "token_bloat": 0.25,
    "review_overhead": 0.20,
    "agent_sprawl": 0.20,
    "architecture_inefficiency": 0.10,
}
CATEGORY_LABELS = {
    "redundancy": "Redundancy",
    "token_bloat": "Token bloat",
    "review_overhead": "Review overhead",
    "agent_sprawl": "Agent sprawl",
    "architecture_inefficiency": "Architecture inefficiency",
}

PENALTIES = {
    "near_duplicate": {"points": 5, "cap": 32, "category": "redundancy"},
    "repeated_block": {"points": 4, "cap": 20, "category": "redundancy"},
    "oversized_context": {"points": 6, "cap": 24, "category": "token_bloat"},
    "agent_sprawl": {"points": 2, "cap": 20, "category": "agent_sprawl"},
    "review_stages": {"points": 5, "cap": 15, "category": "review_overhead"},
    "microservice_mismatch": {"points": 12, "cap": 12, "category": "architecture_inefficiency"},
    "monolith_mismatch": {"points": 10, "cap": 10, "category": "architecture_inefficiency"},
}

SIMILARITY_DUPLICATE_THRESHOLD = 0.80
SIMILARITY_OVERLAP_THRESHOLD = 0.50
MIN_CHARS_FOR_SIMILARITY = 200
SHINGLE_SIZE = 5
SKETCH_SIZE = 256

REPEATED_BLOCK_MIN_CHARS = 150
REPEATED_BLOCK_MIN_FILES = 3

OVERSIZED_CONTEXT_TOKENS = 8000
AGENT_SPRAWL_THRESHOLD = 12
REVIEW_STAGE_THRESHOLD = 4
MICROSERVICE_DIR_THRESHOLD = 8
MICROSERVICE_SOURCE_FLOOR = 120
MONOLITH_AGENT_ROLE_THRESHOLD = 10

VERDICT_BANDS = [(80, 100, "Lean"), (60, 79, "Watchlist"), (40, 59, "Wasteful"), (0, 39, "Critical")]


def verdict_for_score(score: int) -> str:
    for low, high, name in VERDICT_BANDS:
        if low <= score <= high:
            return name
    return "Critical"


# -------------------------------------------- review / approval patterns
REVIEW_STAGE_PATTERNS = {
    "Self review": [r"self[\s\-]?review"],
    "Peer review": [r"peer[\s\-]?review"],
    "Code review": [r"code[\s\-]?review"],
    "QA review": [r"\bqa\s+(review|gate|stage|sign)", r"quality assurance"],
    "Security review": [r"security[\s\-]?review", r"security sign[\s\-]?off"],
    "Architecture review": [r"architect(?:ure|ural)[\s\-]?review", r"design[\s\-]?review"],
    "Product approval": [r"product\s+(?:owner\s+)?approval", r"\bpo\s+approval"],
    "Manager approval": [r"manager\s+approval", r"lead\s+approval", r"tech lead\s+approval"],
    "Final approval": [r"final\s+approval", r"final\s+sign[\s\-]?off"],
    "Sign-off": [r"sign[\s\-]?off"],
    "Validation gate": [r"validation\s+(?:gate|step|stage|phase)"],
    "Verification gate": [r"verification\s+(?:gate|step|stage|phase)"],
    "Human in the loop": [r"human[\s\-]?in[\s\-]?the[\s\-]?loop", r"\bhitl\b"],
    "Approval chain": [r"approval\s+(?:chain|workflow|pipeline)"],
    "Acceptance gate": [r"acceptance\s+(?:criteria\s+)?(?:gate|review|stage)"],
    "Escalation review": [r"escalat\w*\s+(?:review|approval|path)"],
}

SERVICE_PARENT_DIRS = {"services", "apps", "packages", "microservices", "cmd", "modules", "functions"}
SERVICE_MARKER_FILES = {
    "dockerfile", "package.json", "go.mod", "requirements.txt", "pyproject.toml",
    "pom.xml", "cargo.toml", "build.gradle", "composer.json", "gemfile",
}

# ---------------------------------------------------- savings assumptions
# Reporting ratio required by spec: 1 credit == 100,000 tokens.
# Billing model provided by the product owner:
#   $1.00 == 100 vendor credits
#   1 vendor credit == 2,500 input tokens  OR  500 output tokens (output costs 5x input)
# => input  $ / 1M tokens = 1_000_000 / (2500 * 100) = $4.00
# => output $ / 1M tokens = 1_000_000 / (500  * 100) = $20.00
DEFAULT_ASSUMPTIONS = {
    "tokens_per_report_credit": 100000,
    "vendor_credits_per_dollar": 100.0,
    "input_tokens_per_vendor_credit": 2500,
    "output_tokens_per_vendor_credit": 500,
    "agent_runs_per_month": 200,
    "output_token_share": 0.10,
    "variance_pct": 0.20,
    "rates_last_refreshed": None,
    "rates_source": "Product owner supplied defaults (not yet refreshed)",
}


def derived_rates(a: dict) -> dict:
    """Return $ per 1M input/output tokens derived from the billing assumptions."""
    vcpd = float(a.get("vendor_credits_per_dollar") or DEFAULT_ASSUMPTIONS["vendor_credits_per_dollar"])
    itc = float(a.get("input_tokens_per_vendor_credit") or DEFAULT_ASSUMPTIONS["input_tokens_per_vendor_credit"])
    otc = float(a.get("output_tokens_per_vendor_credit") or DEFAULT_ASSUMPTIONS["output_tokens_per_vendor_credit"])
    return {
        "input_dollars_per_million": round(1_000_000.0 / (itc * vcpd), 4),
        "output_dollars_per_million": round(1_000_000.0 / (otc * vcpd), 4),
    }


def merged_assumptions(overrides: dict | None = None) -> dict:
    merged = dict(DEFAULT_ASSUMPTIONS)
    if overrides:
        for k, v in overrides.items():
            if k in merged and v is not None:
                merged[k] = v
    merged.update(derived_rates(merged))
    return merged


TOKEN_FORMULA = "estimated_tokens = ceil(character_count / 4)"
SIMILARITY_FORMULA = (
    "similarity = Jaccard overlap of 5-word shingles on normalised text "
    "(lower-cased, whitespace collapsed, punctuation preserved)"
)
