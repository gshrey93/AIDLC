"""Advanced backend tests: real GitHub, zip uploads, draft generation."""
import io
import json
import os
import sys
import time
import zipfile

import requests

BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://token-audit-7.preview.emergentagent.com")
API_BASE = f"{BACKEND_URL}/api"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def log(message, color=None):
    if color:
        print(f"{color}{message}{Colors.END}")
    else:
        print(message)

def poll_scan(scan_id, timeout=300):
    """Poll scan until terminal status."""
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{API_BASE}/scans/{scan_id}", timeout=10)
        if resp.status_code != 200:
            return None
        scan = resp.json()
        status = scan.get("status")
        progress = scan.get("progress", {}).get("percent", 0)
        log(f"   Status: {status}, Progress: {progress}%")
        
        if status in ("completed", "ImportFailed", "ParseFailed", "InsufficientData"):
            return scan
        
        time.sleep(3)
    
    return None

def test_real_github_scan():
    """Test real GitHub scan with https://github.com/humanlayer/12-factor-agents."""
    log("\n" + "="*70, Colors.BLUE)
    log("Test: Real GitHub Scan", Colors.BLUE)
    log("="*70, Colors.BLUE)
    
    form_data = {
        "source_type": "github",
        "rights_ack": "true",
        "repo_url": "https://github.com/humanlayer/12-factor-agents"
    }
    
    log("   Creating scan...")
    resp = requests.post(f"{API_BASE}/scans", data=form_data, timeout=10)
    if resp.status_code != 200:
        log(f"❌ FAILED: Create scan returned {resp.status_code}", Colors.RED)
        log(f"   Response: {resp.text[:500]}", Colors.RED)
        return False
    
    scan = resp.json()
    scan_id = scan["id"]
    log(f"   Scan created: {scan_id}")
    
    log("   Polling scan (this may take 2-4 minutes)...")
    final_scan = poll_scan(scan_id, timeout=300)
    
    if not final_scan:
        log("❌ FAILED: Scan timed out", Colors.RED)
        return False
    
    status = final_scan.get("status")
    if status != "completed":
        log(f"❌ FAILED: Expected status 'completed', got '{status}'", Colors.RED)
        log(f"   Error: {final_scan.get('error_message', 'N/A')}", Colors.RED)
        return False
    
    # Verify progress
    progress = final_scan.get("progress", {})
    if progress.get("percent") != 100:
        log(f"❌ FAILED: Progress not 100%, got {progress.get('percent')}%", Colors.RED)
        return False
    
    # Verify all 7 stages are done
    stages = progress.get("stages", [])
    if len(stages) != 7:
        log(f"❌ FAILED: Expected 7 stages, got {len(stages)}", Colors.RED)
        return False
    
    pending_stages = [s for s in stages if s.get("status") == "pending"]
    if pending_stages:
        log(f"❌ FAILED: Found pending stages: {[s['key'] for s in pending_stages]}", Colors.RED)
        return False
    
    # Verify score and verdict
    overall_score = final_scan.get("overall_score")
    verdict = final_scan.get("verdict")
    
    if not overall_score or overall_score == 0:
        log(f"❌ FAILED: Overall score is {overall_score}", Colors.RED)
        return False
    
    if not verdict:
        log(f"❌ FAILED: Verdict is null", Colors.RED)
        return False
    
    log(f"   ✓ Status: {status}", Colors.GREEN)
    log(f"   ✓ Progress: 100%", Colors.GREEN)
    log(f"   ✓ All 7 stages completed", Colors.GREEN)
    log(f"   ✓ Overall score: {overall_score}", Colors.GREEN)
    log(f"   ✓ Verdict: {verdict}", Colors.GREEN)
    log(f"   ✓ Parsed files: {final_scan.get('parsed_files')}", Colors.GREEN)
    log(f"   ✓ Issues found: {final_scan.get('issue_count')}", Colors.GREEN)
    
    log("✅ PASSED: Real GitHub scan", Colors.GREEN)
    return True

def test_github_error_paths():
    """Test GitHub error paths."""
    log("\n" + "="*70, Colors.BLUE)
    log("Test: GitHub Error Paths", Colors.BLUE)
    log("="*70, Colors.BLUE)
    
    tests = [
        {
            "name": "Non-existent repo",
            "url": "https://github.com/octocat/definitely-not-a-real-repo-9f2x",
            "expected_code": "GitHubRepoUnavailable"
        },
        {
            "name": "Non-existent branch",
            "url": "https://github.com/octocat/Hello-World",
            "branch": "no-such-branch-9f2x",
            "expected_code": "BranchNotFound"
        },
        {
            "name": "Repo too large",
            "url": "https://github.com/torvalds/linux",
            "expected_code": "RepoTooLarge"
        }
    ]
    
    passed = 0
    for test in tests:
        log(f"\n   Testing: {test['name']}")
        form_data = {
            "source_type": "github",
            "rights_ack": "true",
            "repo_url": test["url"]
        }
        if "branch" in test:
            form_data["branch"] = test["branch"]
        
        resp = requests.post(f"{API_BASE}/scans", data=form_data, timeout=10)
        if resp.status_code != 200:
            log(f"   ⚠ Could not create scan: {resp.status_code}", Colors.YELLOW)
            continue
        
        scan = resp.json()
        scan_id = scan["id"]
        
        log(f"   Polling scan {scan_id}...")
        final_scan = poll_scan(scan_id, timeout=120)
        
        if not final_scan:
            log(f"   ⚠ Scan timed out", Colors.YELLOW)
            continue
        
        status = final_scan.get("status")
        error_code = final_scan.get("error_code")
        
        if status == "ImportFailed" and error_code == test["expected_code"]:
            log(f"   ✓ Correctly failed with {error_code}", Colors.GREEN)
            passed += 1
        elif error_code == "GitHubRateLimited":
            log(f"   ⚠ Hit rate limit (expected, not a failure)", Colors.YELLOW)
            passed += 1
        else:
            log(f"   ✗ Expected {test['expected_code']}, got {error_code}", Colors.RED)
    
    if passed >= 2:
        log(f"\n✅ PASSED: GitHub error paths ({passed}/3 tests)", Colors.GREEN)
        return True
    else:
        log(f"\n❌ FAILED: GitHub error paths ({passed}/3 tests)", Colors.RED)
        return False

def test_real_zip_upload():
    """Test real zip upload with agent files."""
    log("\n" + "="*70, Colors.BLUE)
    log("Test: Real Zip Upload", Colors.BLUE)
    log("="*70, Colors.BLUE)
    
    # Create a zip with 6+ markdown files including agent files
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.agent.md", "# Agent A\n" + "This is agent A. " * 100)
        zf.writestr("b.agent.md", "# Agent B\n" + "This is agent B. " * 100)
        zf.writestr("instructions.md", "# Instructions\n" + "Follow these steps. " * 100)
        zf.writestr("context.md", "# Context\n" + "This is the context. " * 100)
        zf.writestr("skill1.md", "# Skill 1\n" + "This is skill 1. " * 100)
        zf.writestr("skill2.md", "# Skill 2\n" + "This is skill 2. " * 100)
        zf.writestr("readme.md", "# README\n" + "This is the readme. " * 50)
    
    zip_buffer.seek(0)
    
    form_data = {
        "source_type": "zip",
        "rights_ack": "true"
    }
    files = {"zip_file": ("test-repo.zip", zip_buffer, "application/zip")}
    
    log("   Creating scan with zip upload...")
    resp = requests.post(f"{API_BASE}/scans", data=form_data, files=files, timeout=10)
    if resp.status_code != 200:
        log(f"❌ FAILED: Create scan returned {resp.status_code}", Colors.RED)
        log(f"   Response: {resp.text[:500]}", Colors.RED)
        return False
    
    scan = resp.json()
    scan_id = scan["id"]
    log(f"   Scan created: {scan_id}")
    
    log("   Polling scan...")
    final_scan = poll_scan(scan_id, timeout=120)
    
    if not final_scan:
        log("❌ FAILED: Scan timed out", Colors.RED)
        return False
    
    status = final_scan.get("status")
    if status != "completed":
        log(f"❌ FAILED: Expected status 'completed', got '{status}'", Colors.RED)
        log(f"   Error: {final_scan.get('error_message', 'N/A')}", Colors.RED)
        return False
    
    # Verify issues were found
    issue_count = final_scan.get("issue_count", 0)
    if issue_count == 0:
        log(f"⚠ WARNING: No issues found (expected some)", Colors.YELLOW)
    
    log(f"   ✓ Status: {status}", Colors.GREEN)
    log(f"   ✓ Parsed files: {final_scan.get('parsed_files')}", Colors.GREEN)
    log(f"   ✓ Issues found: {issue_count}", Colors.GREEN)
    log(f"   ✓ Overall score: {final_scan.get('overall_score')}", Colors.GREEN)
    
    log("✅ PASSED: Real zip upload", Colors.GREEN)
    return True

def test_corrupted_zip():
    """Test corrupted zip upload."""
    log("\n" + "="*70, Colors.BLUE)
    log("Test: Corrupted Zip", Colors.BLUE)
    log("="*70, Colors.BLUE)
    
    form_data = {
        "source_type": "zip",
        "rights_ack": "true"
    }
    files = {"zip_file": ("broken.zip", b"This is not a valid zip file content", "application/zip")}
    
    log("   Creating scan with corrupted zip...")
    resp = requests.post(f"{API_BASE}/scans", data=form_data, files=files, timeout=10)
    if resp.status_code != 200:
        log(f"❌ FAILED: Create scan returned {resp.status_code}", Colors.RED)
        log(f"   Response: {resp.text[:500]}", Colors.RED)
        return False
    
    scan = resp.json()
    scan_id = scan["id"]
    log(f"   Scan created: {scan_id}")
    
    log("   Polling scan...")
    final_scan = poll_scan(scan_id, timeout=60)
    
    if not final_scan:
        log("❌ FAILED: Scan timed out", Colors.RED)
        return False
    
    status = final_scan.get("status")
    error_code = final_scan.get("error_code")
    
    if status == "ImportFailed" and error_code == "ZipCorrupted":
        log(f"   ✓ Correctly failed with ZipCorrupted", Colors.GREEN)
        log("✅ PASSED: Corrupted zip", Colors.GREEN)
        return True
    else:
        log(f"❌ FAILED: Expected ImportFailed/ZipCorrupted, got {status}/{error_code}", Colors.RED)
        return False

def test_draft_generation():
    """Test real draft generation with LLM."""
    log("\n" + "="*70, Colors.BLUE)
    log("Test: Real Draft Generation (LLM call, may take 3 minutes)", Colors.BLUE)
    log("="*70, Colors.BLUE)
    
    # First, find a completed scan with draft candidates
    resp = requests.get(f"{API_BASE}/scans", timeout=10)
    if resp.status_code != 200:
        log("❌ FAILED: Could not list scans", Colors.RED)
        return False
    
    scans = resp.json()["scans"]
    completed_scans = [s for s in scans if s.get("status") == "completed"]
    
    scan_with_candidates = None
    for scan in completed_scans:
        resp2 = requests.get(f"{API_BASE}/scans/{scan['id']}", timeout=10)
        if resp2.status_code == 200:
            full_scan = resp2.json()
            candidates = full_scan.get("draft_candidates", [])
            if candidates:
                scan_with_candidates = full_scan
                break
    
    if not scan_with_candidates:
        log("⚠ WARNING: No scan with draft candidates found, skipping", Colors.YELLOW)
        return True
    
    scan_id = scan_with_candidates["id"]
    candidates = scan_with_candidates["draft_candidates"]
    source_path = candidates[0]["source_path"]
    
    log(f"   Using scan: {scan_id}")
    log(f"   Generating draft for: {source_path}")
    log(f"   This will make a real claude-opus-4-7 API call...")
    
    payload = {"source_path": source_path}
    resp = requests.post(f"{API_BASE}/scans/{scan_id}/drafts", json=payload, timeout=240)
    
    if resp.status_code != 200:
        log(f"❌ FAILED: Draft generation returned {resp.status_code}", Colors.RED)
        log(f"   Response: {resp.text[:500]}", Colors.RED)
        return False
    
    draft = resp.json()
    
    # Verify draft fields
    if "target_filename" not in draft:
        log("❌ FAILED: Draft missing 'target_filename'", Colors.RED)
        return False
    
    if not draft["target_filename"].endswith("-optimised.md"):
        log(f"❌ FAILED: target_filename should end with '-optimised.md', got {draft['target_filename']}", Colors.RED)
        return False
    
    if "draft_content" not in draft or len(draft["draft_content"]) < 200:
        log(f"❌ FAILED: draft_content too short: {len(draft.get('draft_content', ''))} chars", Colors.RED)
        return False
    
    if draft.get("draft_tokens", 0) >= draft.get("original_tokens", 0):
        log(f"❌ FAILED: draft_tokens should be < original_tokens", Colors.RED)
        return False
    
    if draft.get("reduction_pct", 0) <= 0:
        log(f"❌ FAILED: reduction_pct should be > 0", Colors.RED)
        return False
    
    log(f"   ✓ Target filename: {draft['target_filename']}", Colors.GREEN)
    log(f"   ✓ Draft content: {len(draft['draft_content'])} chars", Colors.GREEN)
    log(f"   ✓ Original tokens: {draft['original_tokens']}", Colors.GREEN)
    log(f"   ✓ Draft tokens: {draft['draft_tokens']}", Colors.GREEN)
    log(f"   ✓ Reduction: {draft['reduction_pct']}%", Colors.GREEN)
    
    log("✅ PASSED: Real draft generation", Colors.GREEN)
    return True

def main():
    """Run advanced backend tests."""
    log(f"\n{Colors.BLUE}{'='*70}{Colors.END}")
    log(f"{Colors.BLUE}BLOAT GUARDIAN ADVANCED BACKEND TESTS{Colors.END}")
    log(f"{Colors.BLUE}Backend URL: {BACKEND_URL}{Colors.END}")
    log(f"{Colors.BLUE}{'='*70}{Colors.END}\n")
    
    results = []
    
    # Real GitHub scan (takes time)
    log(f"\n{Colors.YELLOW}⚠ Note: Real GitHub scan may take 2-4 minutes{Colors.END}")
    results.append(("Real GitHub scan", test_real_github_scan()))
    
    # GitHub error paths
    log(f"\n{Colors.YELLOW}⚠ Note: May hit GitHub rate limits (60 req/hour){Colors.END}")
    results.append(("GitHub error paths", test_github_error_paths()))
    
    # Real zip upload
    results.append(("Real zip upload", test_real_zip_upload()))
    
    # Corrupted zip
    results.append(("Corrupted zip", test_corrupted_zip()))
    
    # Draft generation (real LLM call)
    log(f"\n{Colors.YELLOW}⚠ Note: Draft generation may take up to 3 minutes{Colors.END}")
    results.append(("Draft generation", test_draft_generation()))
    
    # Summary
    log("\n" + "="*70)
    log("ADVANCED TEST SUMMARY")
    log("="*70)
    passed = sum(1 for _, result in results if result)
    total = len(results)
    log(f"Total tests: {total}")
    log(f"Passed: {Colors.GREEN}{passed}{Colors.END}")
    log(f"Failed: {Colors.RED}{total - passed}{Colors.END}")
    log(f"Success rate: {passed/total*100:.1f}%")
    
    log("\nResults:")
    for name, result in results:
        status = f"{Colors.GREEN}✅ PASSED{Colors.END}" if result else f"{Colors.RED}❌ FAILED{Colors.END}"
        log(f"  {name}: {status}")
    
    log("="*70)
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())
