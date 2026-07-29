"""Verify series SER-C7EB608470FE has correct details."""
import requests
import sys

BACKEND_URL = "https://token-audit-7.preview.emergentagent.com"

print("=== VERIFYING SERIES SER-C7EB608470FE ===\n")

series_id = "SER-C7EB608470FE"
resp = requests.get(f"{BACKEND_URL}/api/series/{series_id}", timeout=10)

if resp.status_code != 200:
    print(f"❌ Failed to fetch series: {resp.status_code}")
    sys.exit(1)

series = resp.json()

# Expected values
expected = {
    "run_count": 2,
    "latest_score": 55,
    "latest_verdict": "Wasteful",
    "previous_score": 79,
    "score_delta": -24
}

passed = 0
failed = 0

for key, expected_value in expected.items():
    actual_value = series.get(key)
    if actual_value == expected_value:
        print(f"✅ {key}: {actual_value}")
        passed += 1
    else:
        print(f"❌ {key}: expected {expected_value}, got {actual_value}")
        failed += 1

# Check runs
runs = series.get("runs", [])
print(f"\n=== RUNS ===")

if len(runs) == 2:
    print(f"✅ run count: {len(runs)}")
    passed += 1
else:
    print(f"❌ run count: expected 2, got {len(runs)}")
    failed += 1

# Check run 1
run1 = next((r for r in runs if r.get("id") == "SCN-2026-07-29-0005"), None)
if run1:
    if run1.get("run_number") == 1 and run1.get("overall_score") == 79 and run1.get("score_delta") is None:
        print(f"✅ Run 1 (SCN-2026-07-29-0005): run_number=1, score=79, delta=null")
        passed += 1
    else:
        print(f"❌ Run 1 details incorrect: {run1}")
        failed += 1
else:
    print(f"❌ Run 1 (SCN-2026-07-29-0005) not found")
    failed += 1

# Check run 2
run2 = next((r for r in runs if r.get("id") == "SCN-2026-07-29-0006"), None)
if run2:
    if run2.get("run_number") == 2 and run2.get("overall_score") == 55 and run2.get("score_delta") == -24:
        print(f"✅ Run 2 (SCN-2026-07-29-0006): run_number=2, score=55, delta=-24")
        passed += 1
    else:
        print(f"❌ Run 2 details incorrect: {run2}")
        failed += 1
else:
    print(f"❌ Run 2 (SCN-2026-07-29-0006) not found")
    failed += 1

print(f"\n=== SUMMARY ===")
print(f"Passed: {passed}/8")
print(f"Failed: {failed}/8")

if failed > 0:
    sys.exit(1)
else:
    print("\n✅ Series SER-C7EB608470FE has correct details")
    sys.exit(0)
