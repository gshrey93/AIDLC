"""Verify seeded demo scans maintain their scores."""
import requests
import sys

BACKEND_URL = "https://token-audit-7.preview.emergentagent.com"

print("=== VERIFYING SEEDED DEMO SCANS ===\n")

# Test specific scans mentioned in the requirements
test_cases = [
    {
        "id": "SCN-2026-07-26-0001",
        "expected_score": 35,
        "expected_verdict": "Critical"
    },
    {
        "id": "SCN-2026-06-30-0001",
        "expected_score": 80,
        "expected_verdict": "Lean"
    },
    {
        "id": "SCN-2026-07-29-0005",
        "expected_score": 79,
        "expected_verdict": "Watchlist"
    },
    {
        "id": "SCN-2026-07-29-0006",
        "expected_score": 55,
        "expected_verdict": "Wasteful"
    }
]

passed = 0
failed = 0

for test in test_cases:
    scan_id = test["id"]
    expected_score = test["expected_score"]
    expected_verdict = test["expected_verdict"]
    
    resp = requests.get(f"{BACKEND_URL}/api/scans/{scan_id}", timeout=10)
    
    if resp.status_code == 200:
        scan = resp.json()
        actual_score = scan.get("overall_score")
        actual_verdict = scan.get("verdict")
        
        score_match = actual_score == expected_score
        verdict_match = actual_verdict == expected_verdict
        
        if score_match and verdict_match:
            print(f"✅ {scan_id}: score={actual_score}, verdict={actual_verdict}")
            passed += 1
        else:
            print(f"❌ {scan_id}: MISMATCH")
            print(f"   Expected: score={expected_score}, verdict={expected_verdict}")
            print(f"   Actual:   score={actual_score}, verdict={actual_verdict}")
            failed += 1
    else:
        print(f"❌ {scan_id}: Failed to fetch (status {resp.status_code})")
        failed += 1

print(f"\n=== SUMMARY ===")
print(f"Passed: {passed}/{len(test_cases)}")
print(f"Failed: {failed}/{len(test_cases)}")

if failed > 0:
    sys.exit(1)
else:
    print("\n✅ All seeded scans maintain correct scores")
    sys.exit(0)
