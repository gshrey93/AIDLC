"""Repository import: GitHub, Bitbucket and local zip / markdown uploads.

All network calls are real and unauthenticated by default (public repos only).
An optional user supplied token can be passed for higher rate limits.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from typing import Optional

import httpx

from .config import MAX_ARCHIVE_BYTES, MAX_UNCOMPRESSED_BYTES

GITHUB_URL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?"
    r"(?:/(?:tree|blob)/(?P<branch>[^/?#]+))?/?(?:[?#].*)?$"
)
BITBUCKET_URL_RE = re.compile(
    r"^https?://(?:www\.)?bitbucket\.org/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?"
    r"(?:/(?:src|branch)/(?P<branch>[^/?#]+))?/?(?:[?#].*)?$"
)


class ImportError_(Exception):
    """Import failure carrying one of the spec error codes."""

    def __init__(self, code: str, message: str, retry_after_minutes: Optional[int] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after_minutes = retry_after_minutes


@dataclass
class ImportResult:
    root_dir: str
    source_type: str
    repo_name: str
    repo_owner: Optional[str] = None
    branch: Optional[str] = None
    archive_bytes: int = 0
    default_branch: Optional[str] = None
    warnings: list = field(default_factory=list)


# --------------------------------------------------------------- helpers
def parse_github_url(url: str):
    m = GITHUB_URL_RE.match((url or "").strip())
    if not m:
        return None
    return m.group("owner"), m.group("repo"), m.group("branch")


def parse_bitbucket_url(url: str):
    m = BITBUCKET_URL_RE.match((url or "").strip())
    if not m:
        return None
    return m.group("owner"), m.group("repo"), m.group("branch")


def _is_rate_limited(resp: httpx.Response) -> bool:
    if resp.status_code == 429:
        return True
    if resp.status_code == 403:
        remaining = resp.headers.get("x-ratelimit-remaining")
        if remaining == "0":
            return True
        body = ""
        try:
            body = resp.text.lower()
        except Exception:
            body = ""
        if "rate limit" in body or "api rate limit" in body:
            return True
    return False


def _download_archive(url: str, dest_path: str, headers: dict, too_large_code: str) -> int:
    total = 0
    try:
        with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=120.0) as resp:
            if resp.status_code == 404:
                raise ImportError_("ArchiveNotFound", f"Archive not found at {url}")
            if _is_rate_limited(resp):
                raise ImportError_("RateLimited", "Archive host rate limited the request", 15)
            if resp.status_code >= 400:
                raise ImportError_("ImportFailed", f"Archive download failed with HTTP {resp.status_code}")
            declared = resp.headers.get("content-length")
            if declared and int(declared) > MAX_ARCHIVE_BYTES:
                raise ImportError_(
                    too_large_code,
                    f"Archive is {int(declared) / 1048576:.1f} MB which exceeds the 250 MB limit",
                )
            with open(dest_path, "wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                    total += len(chunk)
                    if total > MAX_ARCHIVE_BYTES:
                        raise ImportError_(
                            too_large_code,
                            "Archive exceeded the 250 MB compressed limit while downloading",
                        )
                    fh.write(chunk)
    except httpx.HTTPError as exc:
        raise ImportError_("ImportFailed", f"Network error while downloading archive: {exc}") from exc
    return total


def extract_zip(zip_path: str, dest_dir: str) -> str:
    """Extract a zip safely, strip a single top level folder, return content root."""
    if os.path.getsize(zip_path) > MAX_ARCHIVE_BYTES:
        raise ImportError_("ZipTooLarge", "Zip archive is larger than 250 MB")
    try:
        with zipfile.ZipFile(zip_path) as zf:
            bad = zf.testzip()
            if bad is not None:
                raise ImportError_("ZipCorrupted", f"Corrupt entry inside archive: {bad}")
            total_unpacked = 0
            for info in zf.infolist():
                total_unpacked += info.file_size
                if total_unpacked > MAX_UNCOMPRESSED_BYTES:
                    raise ImportError_("ZipCorrupted", "Archive expands beyond the safe 2 GB limit")
                name = info.filename
                if name.startswith("/") or ".." in name.replace("\\", "/").split("/"):
                    continue
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    continue
                target = os.path.join(dest_dir, name)
                if not os.path.abspath(target).startswith(os.path.abspath(dest_dir)):
                    continue
                if info.is_dir():
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 128)
    except zipfile.BadZipFile as exc:
        raise ImportError_("ZipCorrupted", f"The uploaded file is not a readable zip archive ({exc})") from exc
    except ImportError_:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise ImportError_("ZipCorrupted", f"Archive extraction failed: {exc}") from exc

    entries = [e for e in os.listdir(dest_dir) if not e.startswith("__MACOSX")]
    if len(entries) == 1 and os.path.isdir(os.path.join(dest_dir, entries[0])):
        return os.path.join(dest_dir, entries[0])
    return dest_dir


# ---------------------------------------------------------------- GitHub
def import_github(url: str, branch: Optional[str], work_dir: str, token: Optional[str] = None) -> ImportResult:
    parsed = parse_github_url(url)
    if not parsed:
        raise ImportError_(
            "GitHubRepoUnavailable",
            "That does not look like a GitHub repository URL. Use https://github.com/{owner}/{repo}",
        )
    owner, repo, url_branch = parsed
    branch = (branch or url_branch or "").strip() or None

    headers = {"Accept": "application/vnd.github+json", "User-Agent": "BloatGuardian/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    default_branch: Optional[str] = None
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            meta = client.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers)
            if _is_rate_limited(meta):
                raise ImportError_(
                    "GitHubRateLimited",
                    "GitHub rate limited this request. Please retry in 15 minutes or add a personal access token in Settings.",
                    15,
                )
            if meta.status_code == 404:
                raise ImportError_(
                    "GitHubRepoUnavailable",
                    f"GitHub could not find a public repository at {owner}/{repo}.",
                )
            if meta.status_code >= 400:
                raise ImportError_(
                    "GitHubRepoUnavailable",
                    f"GitHub returned HTTP {meta.status_code} for {owner}/{repo}.",
                )
            info = meta.json()
            default_branch = info.get("default_branch") or "main"
            repo_kb = int(info.get("size") or 0)
            if repo_kb * 1024 > MAX_ARCHIVE_BYTES * 4:
                raise ImportError_(
                    "RepoTooLarge",
                    f"{owner}/{repo} is about {repo_kb / 1024:.0f} MB of source which exceeds our 250 MB limit.",
                )
            if branch:
                br = client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}", headers=headers
                )
                if br.status_code == 404:
                    raise ImportError_(
                        "BranchNotFound",
                        f"Branch '{branch}' does not exist in {owner}/{repo}.",
                    )
                if _is_rate_limited(br):
                    raise ImportError_("GitHubRateLimited", "GitHub rate limited the branch lookup. Retry in 15 minutes.", 15)
            else:
                branch = default_branch
    except ImportError_:
        raise
    except httpx.HTTPError as exc:
        raise ImportError_("GitHubRepoUnavailable", f"Could not reach GitHub: {exc}") from exc

    zip_path = os.path.join(work_dir, "archive.zip")
    archive_url = f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{branch}"
    size = 0
    try:
        size = _download_archive(archive_url, zip_path, headers, "RepoTooLarge")
    except ImportError_ as exc:
        if exc.code == "ArchiveNotFound":
            raise ImportError_("BranchNotFound", f"Branch '{branch}' does not exist in {owner}/{repo}.") from exc
        if exc.code == "RateLimited":
            raise ImportError_("GitHubRateLimited", "GitHub rate limited the archive download. Retry in 15 minutes.", 15) from exc
        raise

    extract_dir = os.path.join(work_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    root = extract_zip(zip_path, extract_dir)
    try:
        os.remove(zip_path)
    except OSError:
        pass
    return ImportResult(
        root_dir=root, source_type="github", repo_name=repo, repo_owner=owner,
        branch=branch, archive_bytes=size, default_branch=default_branch,
    )


# ------------------------------------------------------------- Bitbucket
def import_bitbucket(url: str, branch: Optional[str], work_dir: str, token: Optional[str] = None) -> ImportResult:
    parsed = parse_bitbucket_url(url)
    if not parsed:
        raise ImportError_(
            "BitbucketRepoUnavailable",
            "That does not look like a Bitbucket repository URL. Use https://bitbucket.org/{workspace}/{repo}",
        )
    owner, repo, url_branch = parsed
    branch = (branch or url_branch or "").strip() or None
    headers = {"User-Agent": "BloatGuardian/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    default_branch: Optional[str] = None
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            meta = client.get(f"https://api.bitbucket.org/2.0/repositories/{owner}/{repo}", headers=headers)
            if _is_rate_limited(meta):
                raise ImportError_(
                    "BitbucketRateLimited",
                    "Bitbucket rate limited this request. Please retry in 15 minutes.",
                    15,
                )
            if meta.status_code in (403, 404):
                raise ImportError_(
                    "BitbucketRepoUnavailable",
                    f"Bitbucket could not find a public repository at {owner}/{repo}.",
                )
            if meta.status_code >= 400:
                raise ImportError_(
                    "BitbucketRepoUnavailable",
                    f"Bitbucket returned HTTP {meta.status_code} for {owner}/{repo}.",
                )
            info = meta.json()
            default_branch = ((info.get("mainbranch") or {}).get("name")) or "main"
            size_bytes = int(info.get("size") or 0)
            if size_bytes > MAX_ARCHIVE_BYTES * 4:
                raise ImportError_(
                    "RepoTooLarge",
                    f"{owner}/{repo} is about {size_bytes / 1048576:.0f} MB which exceeds our 250 MB limit.",
                )
            if branch:
                br = client.get(
                    f"https://api.bitbucket.org/2.0/repositories/{owner}/{repo}/refs/branches/{branch}",
                    headers=headers,
                )
                if br.status_code == 404:
                    raise ImportError_("BranchNotFound", f"Branch '{branch}' does not exist in {owner}/{repo}.")
            else:
                branch = default_branch
    except ImportError_:
        raise
    except httpx.HTTPError as exc:
        raise ImportError_("BitbucketRepoUnavailable", f"Could not reach Bitbucket: {exc}") from exc

    zip_path = os.path.join(work_dir, "archive.zip")
    archive_url = f"https://bitbucket.org/{owner}/{repo}/get/{branch}.zip"
    size = 0
    try:
        size = _download_archive(archive_url, zip_path, headers, "RepoTooLarge")
    except ImportError_ as exc:
        if exc.code == "ArchiveNotFound":
            raise ImportError_("BranchNotFound", f"Branch '{branch}' does not exist in {owner}/{repo}.") from exc
        if exc.code == "RateLimited":
            raise ImportError_("BitbucketRateLimited", "Bitbucket rate limited the download. Retry in 15 minutes.", 15) from exc
        raise

    extract_dir = os.path.join(work_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    root = extract_zip(zip_path, extract_dir)
    try:
        os.remove(zip_path)
    except OSError:
        pass
    return ImportResult(
        root_dir=root, source_type="bitbucket", repo_name=repo, repo_owner=owner,
        branch=branch, archive_bytes=size, default_branch=default_branch,
    )


# ------------------------------------------------------------ zip upload
def import_zip(zip_path: str, work_dir: str, display_name: Optional[str] = None) -> ImportResult:
    size = os.path.getsize(zip_path)
    if size > MAX_ARCHIVE_BYTES:
        raise ImportError_("ZipTooLarge", f"Zip is {size / 1048576:.1f} MB which exceeds the 250 MB limit")
    extract_dir = os.path.join(work_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    root = extract_zip(zip_path, extract_dir)
    name = display_name or os.path.splitext(os.path.basename(zip_path))[0]
    return ImportResult(root_dir=root, source_type="zip", repo_name=name, archive_bytes=size)


# --------------------------------------------------- markdown file upload
def import_markdown_files(files: list, work_dir: str, display_name: Optional[str] = None) -> ImportResult:
    """files: list of (filename, bytes)."""
    if not files:
        raise ImportError_("ImportFailed", "No markdown files were uploaded")
    root = os.path.join(work_dir, "extracted")
    os.makedirs(root, exist_ok=True)
    total = 0
    for filename, blob in files:
        safe = os.path.basename(filename.replace("\\", "/"))
        if not safe:
            continue
        total += len(blob)
        with open(os.path.join(root, safe), "wb") as fh:
            fh.write(blob)
    name = display_name or "markdown-upload"
    return ImportResult(root_dir=root, source_type="md", repo_name=name, archive_bytes=total)


def make_work_dir(prefix: str = "bg-scan-") -> str:
    base = os.environ.get("BG_WORKSPACE", os.path.join(tempfile.gettempdir(), "bloatguardian"))
    os.makedirs(base, exist_ok=True)
    return tempfile.mkdtemp(prefix=prefix, dir=base)
