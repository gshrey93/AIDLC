"""
Test the DRAFT QUALITY FIX feature.
This tests that draft generation with >= 400 token files produces quality output.
"""
import json
import os
import sys
import time
import requests

BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://waste-finder-12.preview.emergentagent.com")
API_BASE = f"{BACKEND_URL}/api"

def test_draft_quality_fix():
    """Test draft quality fix with a >= 400 token file."""
    print("\n" + "="*70)
    print("DRAFT QUALITY FIX TEST")
    print("="*70)
    
    # Get scan with draft candidates
    print("\n1. Getting scan SCN-2026-07-26-0001...")
    resp = requests.get(f"{API_BASE}/scans/SCN-2026-07-26-0001/results", timeout=30)
    if resp.status_code != 200:
        print(f"❌ Failed to get scan results: {resp.status_code}")
        return False
    
    data = resp.json()
    scan = data["scan"]
    candidates = scan.get("draft_candidates", [])
    
    print(f"   Found {len(candidates)} draft candidates")
    
    # Find a candidate with >= 400 tokens
    suitable = [c for c in candidates if c.get("source_tokens", 0) >= 400]
    if not suitable:
        print("❌ No candidates with >= 400 tokens found")
        return False
    
    # Pick the smallest one to save time
    candidate = min(suitable, key=lambda c: c.get("source_tokens", 0))
    source_path = candidate["source_path"]
    source_tokens = candidate["source_tokens"]
    
    print(f"\n2. Selected candidate:")
    print(f"   Path: {source_path}")
    print(f"   Tokens: {source_tokens}")
    
    # Generate draft
    print(f"\n3. Generating draft (this may take up to 4 minutes)...")
    payload = {"source_path": source_path}
    
    start_time = time.time()
    resp2 = requests.post(f"{API_BASE}/scans/SCN-2026-07-26-0001/drafts", 
                         json=payload, timeout=240)
    elapsed = time.time() - start_time
    
    print(f"   Request completed in {elapsed:.1f} seconds")
    print(f"   Status code: {resp2.status_code}")
    
    if resp2.status_code != 200:
        print(f"❌ Draft generation failed: {resp2.status_code}")
        error = resp2.json()
        print(f"   Error: {error}")
        
        # Check for raw provider errors
        error_str = json.dumps(error).lower()
        if "litellm" in error_str or "chaterror" in error_str or "traceback" in error_str:
            print("❌ CRITICAL: Raw provider error exposed to client!")
            return False
        
        return False
    
    draft = resp2.json()
    
    # Verify draft quality
    print(f"\n4. Verifying draft quality...")
    
    target_filename = draft.get("target_filename", "")
    draft_content = draft.get("draft_content", "")
    draft_tokens = draft.get("draft_tokens", 0)
    reduction_pct = draft.get("reduction_pct", 0)
    quality_warning = draft.get("quality_warning")
    
    print(f"   Target filename: {target_filename}")
    print(f"   Draft content length: {len(draft_content)} chars")
    print(f"   Draft tokens: {draft_tokens}")
    print(f"   Reduction: {reduction_pct}%")
    if quality_warning:
        print(f"   Quality warning: {quality_warning}")
    
    # Assertions from review request
    errors = []
    
    if not target_filename.endswith("-optimised.md"):
        errors.append(f"Target filename should end with '-optimised.md', got: {target_filename}")
    
    if len(draft_content) <= 220:
        errors.append(f"Draft content should be > 220 chars, got: {len(draft_content)}")
    
    if draft_tokens >= source_tokens:
        errors.append(f"Draft tokens ({draft_tokens}) should be < source tokens ({source_tokens})")
    
    if reduction_pct <= 0:
        errors.append(f"Reduction % should be > 0, got: {reduction_pct}")
    
    if errors:
        print("\n❌ DRAFT QUALITY ISSUES:")
        for err in errors:
            print(f"   - {err}")
        return False
    
    print("\n✅ DRAFT QUALITY FIX WORKING:")
    print(f"   ✓ Target filename ends with '-optimised.md'")
    print(f"   ✓ Draft content > 220 characters ({len(draft_content)} chars)")
    print(f"   ✓ Draft tokens < source tokens ({draft_tokens} < {source_tokens})")
    print(f"   ✓ Reduction % > 0 ({reduction_pct}%)")
    
    return True


def test_error_mapping():
    """Test that no raw provider errors are exposed."""
    print("\n" + "="*70)
    print("ERROR MAPPING TEST")
    print("="*70)
    
    # Test various endpoints that might fail
    test_cases = [
        ("Invalid scan ID", "GET", f"{API_BASE}/scans/INVALID-SCAN-ID"),
        ("Invalid draft request", "POST", f"{API_BASE}/scans/SCN-2026-07-26-0001/drafts", 
         {"source_path": "nonexistent.md"}),
    ]
    
    all_clean = True
    
    for name, method, url, *args in test_cases:
        print(f"\n{name}:")
        try:
            if method == "GET":
                resp = requests.get(url, timeout=10)
            elif method == "POST":
                payload = args[0] if args else {}
                resp = requests.post(url, json=payload, timeout=10)
            
            print(f"   Status: {resp.status_code}")
            
            if resp.status_code >= 400:
                error = resp.json()
                error_str = json.dumps(error).lower()
                
                # Check for raw provider errors
                bad_strings = ["litellm", "chaterror", "traceback"]
                found = [s for s in bad_strings if s in error_str]
                
                if found:
                    print(f"   ❌ Raw provider error found: {found}")
                    print(f"   Error: {error}")
                    all_clean = False
                else:
                    print(f"   ✓ Clean error message")
        except Exception as e:
            print(f"   Exception: {e}")
    
    if all_clean:
        print("\n✅ ERROR MAPPING WORKING: No raw provider errors exposed")
    else:
        print("\n❌ ERROR MAPPING FAILED: Raw provider errors found")
    
    return all_clean


def main():
    print("\n" + "="*70)
    print("BLOAT GUARDIAN - DRAFT QUALITY & ERROR MAPPING TESTS")
    print(f"Backend URL: {BACKEND_URL}")
    print("="*70)
    
    results = []
    
    # Test draft quality fix
    results.append(("Draft Quality Fix", test_draft_quality_fix()))
    
    # Test error mapping
    results.append(("Error Mapping", test_error_mapping()))
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {name}")
    
    all_passed = all(r[1] for r in results)
    print(f"\nOverall: {'✅ ALL PASSED' if all_passed else '❌ SOME FAILED'}")
    print("="*70)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
