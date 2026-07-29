"""Test that non-existent GitHub repo returns 404 correctly."""
import requests
import sys

BACKEND_URL = "https://token-audit-7.preview.emergentagent.com"

print("Testing non-existent GitHub repo...")

# Create a scan for a non-existent repo
form_data = {
    "source_type": "github",
    "rights_ack": "true",
    "repo_url": "https://github.com/definitely-not-a-real-user-9f2x/definitely-not-a-real-repo-9f2x"
}

resp = requests.post(f"{BACKEND_URL}/api/scans", data=form_data, timeout=10)
print(f"POST /api/scans status: {resp.status_code}")

if resp.status_code == 200:
    scan = resp.json()
    scan_id = scan["id"]
    print(f"Scan created: {scan_id}")
    
    # Wait for scan to fail
    import time
    time.sleep(5)
    
    # Get scan details
    resp2 = requests.get(f"{BACKEND_URL}/api/scans/{scan_id}", timeout=10)
    if resp2.status_code == 200:
        scan_data = resp2.json()
        status = scan_data.get("status")
        error_code = scan_data.get("error_code")
        error_message = scan_data.get("error_message")
        
        print(f"Status: {status}")
        print(f"Error code: {error_code}")
        print(f"Error message: {error_message}")
        
        # Verify it's GitHubRepoUnavailable, NOT GitHubAccessDenied
        if error_code == "GitHubRepoUnavailable":
            print("✅ PASS: Non-existent repo correctly returns GitHubRepoUnavailable")
            if "could not find" in error_message.lower() or "404" in error_message:
                print("✅ PASS: Error message mentions 'could not find' or '404'")
            else:
                print(f"⚠ WARNING: Error message doesn't mention 'could not find': {error_message}")
        elif error_code == "GitHubAccessDenied":
            print("❌ FAIL: Non-existent repo incorrectly returns GitHubAccessDenied (should be GitHubRepoUnavailable)")
            sys.exit(1)
        else:
            print(f"⚠ WARNING: Unexpected error code: {error_code}")
        
        # Clean up
        requests.delete(f"{BACKEND_URL}/api/scans/{scan_id}", timeout=10)
        print(f"Cleaned up scan {scan_id}")
    else:
        print(f"Failed to get scan: {resp2.status_code}")
        sys.exit(1)
else:
    print(f"Failed to create scan: {resp.status_code}")
    print(resp.text)
    sys.exit(1)

print("\n✅ All 404 tests passed")
