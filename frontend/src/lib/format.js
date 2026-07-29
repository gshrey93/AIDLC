/* Tone class names come from the DRL design system tokens in index.css so that
   light mode and dark mode both stay WCAG AA compliant. */
export const VERDICT_TONE = {
  Lean: "tone-success",
  Watchlist: "tone-warning",
  Wasteful: "tone-error",
  Critical: "tone-critical",
};

export const STATUS_TONE = {
  completed: "tone-success",
  running: "tone-info",
  queued: "tone-neutral",
  ImportFailed: "tone-critical",
  ParseFailed: "tone-critical",
  InsufficientData: "tone-warning",
};

export const SEVERITY_TONE = {
  low: "tone-info",
  medium: "tone-warning",
  high: "tone-error",
  critical: "tone-critical",
};

export const SEVERITY_LABEL = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

export const PARSE_STATUS_TONE = {
  Scanned: "tone-success",
  SkippedUnsupported: "tone-neutral",
  SkippedOversized: "tone-warning",
  Binary: "tone-info",
  ParseError: "tone-error",
};

export const VERDICT_CHART_COLOR = {
  Lean: "var(--chart-3)",
  Watchlist: "var(--chart-4)",
  Wasteful: "var(--chart-5)",
  Critical: "var(--chart-2)",
};

export function scoreToneClass(score) {
  const n = Number(score || 0);
  if (n >= 80) return "score-good";
  if (n >= 60) return "score-warn";
  if (n >= 40) return "score-bad";
  return "score-critical";
}

export const CATEGORY_LABELS = {
  redundancy: "Redundancy",
  token_bloat: "Token bloat",
  review_overhead: "Review overhead",
  agent_sprawl: "Agent sprawl",
  architecture_inefficiency: "Architecture inefficiency",
};

export const SOURCE_LABELS = {
  github: "GitHub",
  bitbucket: "Bitbucket",
  zip: "Zip upload",
  md: "Markdown upload",
};

export function num(value, digits = 0) {
  const n = Number(value || 0);
  return n.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function money(value) {
  const n = Number(value || 0);
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function compact(value) {
  const n = Number(value || 0);
  if (Math.abs(n) >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return num(n);
}

export function bytes(value) {
  const n = Number(value || 0);
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${n} B`;
}

export function dateTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function dateOnly(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
}

export function relativeDays(iso) {
  if (!iso) return "";
  const days = Math.round((Date.now() - new Date(iso).getTime()) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}

export const GITHUB_RE = /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/;
export const BITBUCKET_RE = /^https:\/\/bitbucket\.org\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/;

export const ERROR_HELP = {
  GitHubRepoUnavailable:
    "GitHub could not find that public repository. Check the owner and repository name, or upload a zip instead.",
  GitHubRateLimited:
    "GitHub is rate limiting us. Please retry in 15 minutes, or add a GitHub personal access token in Settings.",
  GitHubAccessDenied:
    "GitHub refused access with HTTP 403. That is usually a private or blocked repository, or the unauthenticated limit of 60 requests per hour being used up. Add a personal access token in Settings, wait a few minutes, or upload the repository as a zip.",
  BitbucketAccessDenied:
    "Bitbucket refused access with HTTP 403. The repository is most likely private. Upload it as a zip instead, or add a Bitbucket token in Settings.",
  BitbucketRepoUnavailable:
    "Bitbucket could not find that public repository. Check the workspace and repository name, or upload a zip instead.",
  BitbucketRateLimited: "Bitbucket is rate limiting us. Please retry in 15 minutes.",
  RepoTooLarge: "That repository is bigger than the 250 MB limit. Try a smaller repository or a zip of just your agent files.",
  BranchNotFound: "That branch does not exist. Leave the branch blank to use the default branch.",
  ZipCorrupted: "The zip could not be read. Re-export it and upload again.",
  ZipTooLarge: "The zip is bigger than the 250 MB limit.",
  ImportFailed: "The import could not be completed. You can upload a zip instead.",
  ParseFailed: "We could not build a file tree from the import.",
  InsufficientData:
    "Fewer than 5 text files were parsed, so we cannot score this repository or estimate savings.",
};
