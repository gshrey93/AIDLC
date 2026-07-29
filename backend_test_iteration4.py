"""Iteration 4 - Bug fix verification for .md multi-file upload endpoint."""
import io
import os
import sys
import time
import zipfile

import requests

# Get backend URL from environment
BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://waste-finder-12.preview.emergentagent.com")
API_BASE = f"{BACKEND_URL}/api"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

class BugFixTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []
        self.created_scan_ids = []
        
    def log(self, message, color=None):
        if color:
            print(f"{color}{message}{Colors.END}")
        else:
            print(message)
    
    def test(self, name, func):
        """Run a single test function."""
        self.tests_run += 1
        self.log(f"\n{'='*70}", Colors.BLUE)
        self.log(f"Test {self.tests_run}: {name}", Colors.BLUE)
        self.log('='*70, Colors.BLUE)
        try:
            func()
            self.tests_passed += 1
            self.log(f"✅ PASSED: {name}", Colors.GREEN)
            return True
        except AssertionError as e:
            self.tests_failed += 1
            self.failed_tests.append({"test": name, "error": str(e)})
            self.log(f"❌ FAILED: {name}", Colors.RED)
            self.log(f"   Error: {str(e)}", Colors.RED)
            return False
        except Exception as e:
            self.tests_failed += 1
            self.failed_tests.append({"test": name, "error": f"Exception: {str(e)}"})
            self.log(f"❌ EXCEPTION: {name}", Colors.RED)
            self.log(f"   Error: {str(e)}", Colors.RED)
            return False
    
    def assert_status(self, response, expected, message=""):
        """Assert response status code."""
        if response.status_code != expected:
            raise AssertionError(
                f"{message} Expected status {expected}, got {response.status_code}. "
                f"Response: {response.text[:500]}"
            )
    
    def assert_true(self, condition, message):
        """Assert condition is true."""
        if not condition:
            raise AssertionError(message)
    
    def assert_equal(self, actual, expected, message):
        """Assert values are equal."""
        if actual != expected:
            raise AssertionError(f"{message} Expected {expected}, got {actual}")
    
    def assert_in(self, item, container, message):
        """Assert item is in container."""
        if item not in container:
            raise AssertionError(message)
    
    def create_md_content(self, file_num):
        """Create markdown content with heading and shared instruction paragraph."""
        return f"""# Agent File {file_num}

This is a comprehensive instruction paragraph that contains detailed guidance for the agent system. It includes information about review gates, quality checks, validation steps, and operational procedures that must be followed. This paragraph is intentionally over 150 characters long to meet the test requirements and ensure proper parsing.

## Review Gates
- Gate 1: Initial validation
- Gate 2: Quality check
- Gate 3: Final approval

## Additional Content
More content to make this a substantial file for testing purposes.
"""
    
    def poll_scan_until_terminal(self, scan_id, max_wait=240):
        """Poll scan until it reaches a terminal status."""
        start = time.time()
        terminal_statuses = ["completed", "ImportFailed", "ParseFailed", "InsufficientData"]
        
        while time.time() - start < max_wait:
            resp = requests.get(f"{API_BASE}/scans/{scan_id}", timeout=10)
            if resp.status_code != 200:
                raise AssertionError(f"Failed to get scan {scan_id}: {resp.status_code}")
            
            scan = resp.json()
            status = scan.get("status")
            self.log(f"   Scan {scan_id} status: {status}")
            
            if status in terminal_statuses:
                return scan
            
            time.sleep(5)
        
        raise AssertionError(f"Scan {scan_id} did not reach terminal status in {max_wait}s")
    
    # ============================================================
    # BUG FIX VERIFICATION
    # ============================================================
    
    def test_md_upload_six_files(self):
        """BUG FIX: POST /api/scans with 6 .md files should return 200, not 422."""
        form_data = {
            "source_type": "md",
            "rights_ack": "true"
        }
        
        # Create 6 .md files
        files = []
        for i in range(1, 7):
            content = self.create_md_content(i)
            files.append(("md_files", (f"agent_{i}.md", content.encode(), "text/markdown")))
        
        self.log(f"   Uploading 6 .md files...")
        resp = requests.post(f"{API_BASE}/scans", data=form_data, files=files, timeout=10)
        
        # CRITICAL: Should return 200, NOT 422
        self.assert_status(resp, 200, "MD upload with 6 files should return 200")
        
        scan = resp.json()
        scan_id = scan.get("id")
        self.assert_true(scan_id is not None, "Response should contain scan id")
        
        self.created_scan_ids.append(scan_id)
        self.log(f"   ✓ Created scan: {scan_id}")
        self.log(f"   ✓ Got HTTP 200 (NOT 422) - BUG FIX VERIFIED")
        
        return scan_id
    
    def test_md_scan_completion(self):
        """Poll scan until completed with parsed_files == 6."""
        # Create scan first
        scan_id = self.test_md_upload_six_files()
        
        self.log(f"   Polling scan {scan_id} until terminal...")
        scan = self.poll_scan_until_terminal(scan_id, max_wait=240)
        
        status = scan.get("status")
        parsed_files = scan.get("parsed_files")
        overall_score = scan.get("overall_score")
        verdict = scan.get("verdict")
        
        self.assert_equal(status, "completed", f"Scan should be completed, got {status}")
        self.assert_equal(parsed_files, 6, f"Should have 6 parsed files, got {parsed_files}")
        self.assert_true(overall_score > 0, f"Should have non-zero overall_score, got {overall_score}")
        self.assert_true(verdict is not None, f"Should have non-null verdict, got {verdict}")
        
        # Check progress stages
        progress = scan.get("progress", {})
        stages = progress.get("stages", [])
        self.assert_equal(len(stages), 7, f"Should have 7 progress stages, got {len(stages)}")
        
        pending_stages = [s for s in stages if s.get("status") == "pending"]
        self.assert_equal(len(pending_stages), 0, f"No stages should be pending, found {len(pending_stages)}")
        
        self.log(f"   ✓ Status: {status}")
        self.log(f"   ✓ Parsed files: {parsed_files}")
        self.log(f"   ✓ Overall score: {overall_score}")
        self.log(f"   ✓ Verdict: {verdict}")
        self.log(f"   ✓ All 7 stages completed")
        
        return scan_id
    
    def test_md_scan_results(self):
        """GET /api/scans/{id}/results returns proper data."""
        # Create and wait for scan
        scan_id = self.test_md_upload_six_files()
        self.poll_scan_until_terminal(scan_id, max_wait=240)
        
        # Get results
        resp = requests.get(f"{API_BASE}/scans/{scan_id}/results", timeout=10)
        self.assert_status(resp, 200, "Get results should return 200")
        
        data = resp.json()
        
        # Check required fields
        self.assert_in("category_scores", data, "Results missing category_scores")
        self.assert_in("penalty_ledger", data, "Results missing penalty_ledger")
        self.assert_in("inventory_summary", data, "Results missing inventory_summary")
        
        # Check category scores
        cats = data["category_scores"]
        self.assert_equal(len(cats), 5, f"Should have 5 category scores, got {len(cats)}")
        
        # Check inventory summary
        inventory = data["inventory_summary"]
        self.assert_true(isinstance(inventory, dict), "inventory_summary should be a dict")
        
        # Check that files are grouped under 'Agents'
        groups = inventory.get("groups", {})
        self.assert_in("Agents", groups, "inventory_summary should have 'Agents' group")
        
        agents_group = groups["Agents"]
        agents_count = agents_group.get("count", 0)
        self.assert_equal(agents_count, 6, f"Agents group should have 6 files, got {agents_count}")
        
        self.log(f"   ✓ 5 category scores present")
        self.log(f"   ✓ Penalty ledger present")
        self.log(f"   ✓ Inventory summary present")
        self.log(f"   ✓ 6 files grouped under 'Agents'")
    
    # ============================================================
    # REGRESSION TESTS
    # ============================================================
    
    def test_regression_non_md_file(self):
        """REGRESSION: POST with single non-.md file should return 400 (not 422)."""
        form_data = {
            "source_type": "md",
            "rights_ack": "true"
        }
        files = [("md_files", ("test.txt", b"content", "text/plain"))]
        
        resp = requests.post(f"{API_BASE}/scans", data=form_data, files=files, timeout=10)
        
        # Should return 400, NOT 422
        self.assert_status(resp, 400, "Non-.md file should return 400")
        
        detail = resp.json().get("detail", "")
        self.assert_true("only .md files" in detail.lower(), 
                        f"Error message should mention .md files only, got: {detail}")
        
        self.log(f"   ✓ Got HTTP 400 (not 422)")
        self.log(f"   ✓ Error message: {detail[:100]}")
    
    def test_regression_rights_ack_false(self):
        """REGRESSION: POST with rights_ack=false should return 400."""
        form_data = {
            "source_type": "md",
            "rights_ack": "false"
        }
        files = [("md_files", ("test.md", b"# Test", "text/markdown"))]
        
        resp = requests.post(f"{API_BASE}/scans", data=form_data, files=files, timeout=10)
        
        self.assert_status(resp, 400, "rights_ack=false should return 400")
        
        detail = resp.json().get("detail", "")
        self.assert_true("right to analyze" in detail.lower(), 
                        f"Error message should mention rights, got: {detail}")
        
        self.log(f"   ✓ Got HTTP 400")
        self.log(f"   ✓ Error message: {detail[:100]}")
    
    def test_regression_no_md_files(self):
        """REGRESSION: POST with NO md_files should return 400 (not 422 or 500)."""
        form_data = {
            "source_type": "md",
            "rights_ack": "true"
        }
        # No files attached
        
        resp = requests.post(f"{API_BASE}/scans", data=form_data, timeout=10)
        
        self.assert_status(resp, 400, "No md_files should return 400")
        
        detail = resp.json().get("detail", "")
        self.assert_true("at least one .md file" in detail.lower(), 
                        f"Error message should mention at least one .md file, got: {detail}")
        
        self.log(f"   ✓ Got HTTP 400 (not 422 or 500)")
        self.log(f"   ✓ Error message: {detail[:100]}")
    
    def test_regression_insufficient_data(self):
        """REGRESSION: POST with only 3 .md files should end as InsufficientData."""
        form_data = {
            "source_type": "md",
            "rights_ack": "true"
        }
        
        # Create only 3 .md files
        files = []
        for i in range(1, 4):
            content = self.create_md_content(i)
            files.append(("md_files", (f"agent_{i}.md", content.encode(), "text/markdown")))
        
        self.log(f"   Uploading 3 .md files...")
        resp = requests.post(f"{API_BASE}/scans", data=form_data, files=files, timeout=10)
        self.assert_status(resp, 200, "Should accept 3 .md files")
        
        scan = resp.json()
        scan_id = scan.get("id")
        self.created_scan_ids.append(scan_id)
        
        self.log(f"   Polling scan {scan_id} until terminal...")
        scan = self.poll_scan_until_terminal(scan_id, max_wait=120)
        
        status = scan.get("status")
        error_code = scan.get("error_code")
        verdict = scan.get("verdict")
        
        self.assert_equal(status, "InsufficientData", f"Status should be InsufficientData, got {status}")
        self.assert_equal(error_code, "InsufficientData", f"error_code should be InsufficientData, got {error_code}")
        self.assert_equal(verdict, None, f"verdict should be null, got {verdict}")
        
        # Check all savings fields are 0
        self.assert_equal(scan.get("estimated_monthly_token_waste"), 0, "Token waste should be 0")
        self.assert_equal(scan.get("estimated_monthly_dollar_waste"), 0, "Dollar waste should be 0")
        self.assert_equal(scan.get("estimated_savings_low"), 0, "Savings low should be 0")
        self.assert_equal(scan.get("estimated_savings_high"), 0, "Savings high should be 0")
        
        self.log(f"   ✓ Status: InsufficientData")
        self.log(f"   ✓ error_code: InsufficientData")
        self.log(f"   ✓ verdict: null")
        self.log(f"   ✓ All savings fields: 0")
    
    def test_regression_delete_scan(self):
        """REGRESSION: DELETE /api/scans/{id} should return 200."""
        # Create a test scan
        form_data = {
            "source_type": "md",
            "rights_ack": "true"
        }
        files = [("md_files", ("test.md", b"# Test\nContent", "text/markdown"))]
        
        resp = requests.post(f"{API_BASE}/scans", data=form_data, files=files, timeout=10)
        self.assert_status(resp, 200, "Create scan failed")
        
        scan_id = resp.json().get("id")
        self.log(f"   Created scan: {scan_id}")
        
        # Delete it
        resp2 = requests.delete(f"{API_BASE}/scans/{scan_id}", timeout=10)
        self.assert_status(resp2, 200, "Delete should return 200")
        
        # Verify it's gone
        resp3 = requests.get(f"{API_BASE}/scans/{scan_id}", timeout=10)
        self.assert_status(resp3, 404, "Scan should be deleted")
        
        self.log(f"   ✓ Deleted scan: {scan_id}")
        self.log(f"   ✓ Scan no longer appears in GET")
    
    def test_regression_zip_upload(self):
        """REGRESSION: zip upload with 6 markdown files should still work."""
        # Create a zip with 6 markdown files
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i in range(1, 7):
                content = self.create_md_content(i)
                zf.writestr(f"agent_{i}.md", content)
        
        zip_buffer.seek(0)
        
        form_data = {
            "source_type": "zip",
            "rights_ack": "true"
        }
        files = {"zip_file": ("test.zip", zip_buffer.getvalue(), "application/zip")}
        
        self.log(f"   Uploading zip with 6 .md files...")
        resp = requests.post(f"{API_BASE}/scans", data=form_data, files=files, timeout=10)
        self.assert_status(resp, 200, "Zip upload should return 200")
        
        scan = resp.json()
        scan_id = scan.get("id")
        self.created_scan_ids.append(scan_id)
        
        self.log(f"   Polling scan {scan_id} until terminal...")
        scan = self.poll_scan_until_terminal(scan_id, max_wait=240)
        
        status = scan.get("status")
        self.assert_equal(status, "completed", f"Zip scan should complete, got {status}")
        
        self.log(f"   ✓ Zip upload works correctly")
        self.log(f"   ✓ Scan completed: {scan_id}")
    
    def test_regression_github_import(self):
        """REGRESSION: GitHub import with fake repo should fail correctly."""
        form_data = {
            "source_type": "github",
            "rights_ack": "true",
            "repo_url": "https://github.com/octocat/definitely-not-a-real-repo-9f2x"
        }
        
        self.log(f"   Testing GitHub import with fake repo...")
        resp = requests.post(f"{API_BASE}/scans", data=form_data, timeout=10)
        self.assert_status(resp, 200, "Should accept GitHub scan request")
        
        scan = resp.json()
        scan_id = scan.get("id")
        self.created_scan_ids.append(scan_id)
        
        self.log(f"   Polling scan {scan_id} until terminal...")
        scan = self.poll_scan_until_terminal(scan_id, max_wait=60)
        
        status = scan.get("status")
        error_code = scan.get("error_code")
        
        self.assert_equal(status, "ImportFailed", f"Status should be ImportFailed, got {status}")
        
        # Should be GitHubRepoUnavailable or GitHubRateLimited
        valid_codes = ["GitHubRepoUnavailable", "GitHubRateLimited"]
        self.assert_in(error_code, valid_codes, 
                      f"error_code should be one of {valid_codes}, got {error_code}")
        
        self.log(f"   ✓ Status: ImportFailed")
        self.log(f"   ✓ error_code: {error_code}")
    
    def test_seed_scans_count(self):
        """Verify exactly 20 seed scans remain after cleanup."""
        resp = requests.get(f"{API_BASE}/scans", timeout=10)
        self.assert_status(resp, 200, "List scans failed")
        
        data = resp.json()
        scans = data.get("scans", [])
        seed_scans = [s for s in scans if s.get("is_seed")]
        
        self.assert_equal(len(seed_scans), 20, 
                         f"Should have exactly 20 seed scans, got {len(seed_scans)}")
        
        self.log(f"   ✓ Exactly 20 seed scans present")
    
    # ============================================================
    # CLEANUP
    # ============================================================
    
    def cleanup_test_scans(self):
        """Delete all test scans created during this run."""
        self.log(f"\n{'='*70}", Colors.YELLOW)
        self.log(f"Cleaning up {len(self.created_scan_ids)} test scans...", Colors.YELLOW)
        self.log('='*70, Colors.YELLOW)
        
        for scan_id in self.created_scan_ids:
            try:
                resp = requests.delete(f"{API_BASE}/scans/{scan_id}", timeout=10)
                if resp.status_code == 200:
                    self.log(f"   ✓ Deleted: {scan_id}")
                else:
                    self.log(f"   ⚠ Failed to delete: {scan_id} (status {resp.status_code})")
            except Exception as e:
                self.log(f"   ⚠ Error deleting {scan_id}: {e}")
    
    # ============================================================
    # SUMMARY
    # ============================================================
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*70)
        print("ITERATION 4 BUG FIX TEST SUMMARY")
        print("="*70)
        print(f"Total tests: {self.tests_run}")
        print(f"Passed: {Colors.GREEN}{self.tests_passed}{Colors.END}")
        print(f"Failed: {Colors.RED}{self.tests_failed}{Colors.END}")
        print(f"Success rate: {self.tests_passed/self.tests_run*100:.1f}%")
        
        if self.failed_tests:
            print(f"\n{Colors.RED}Failed tests:{Colors.END}")
            for ft in self.failed_tests:
                print(f"  - {ft['test']}")
                print(f"    {ft['error'][:200]}")
        
        print("="*70)
        
        return self.tests_failed == 0


def main():
    """Run all bug fix verification tests."""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BLUE}ITERATION 4 - MD UPLOAD BUG FIX VERIFICATION{Colors.END}")
    print(f"{Colors.BLUE}Backend URL: {BACKEND_URL}{Colors.END}")
    print(f"{Colors.BLUE}{'='*70}{Colors.END}\n")
    
    tester = BugFixTester()
    
    # Bug fix verification
    tester.test("BUG FIX: 6 .md files upload returns 200 (not 422)", 
                tester.test_md_upload_six_files)
    tester.test("BUG FIX: Scan completes with 6 parsed files", 
                tester.test_md_scan_completion)
    tester.test("BUG FIX: Results endpoint returns proper data", 
                tester.test_md_scan_results)
    
    # Regression tests
    tester.test("REGRESSION: Non-.md file returns 400 (not 422)", 
                tester.test_regression_non_md_file)
    tester.test("REGRESSION: rights_ack=false returns 400", 
                tester.test_regression_rights_ack_false)
    tester.test("REGRESSION: No md_files returns 400 (not 422 or 500)", 
                tester.test_regression_no_md_files)
    tester.test("REGRESSION: 3 .md files ends as InsufficientData", 
                tester.test_regression_insufficient_data)
    tester.test("REGRESSION: DELETE scan returns 200", 
                tester.test_regression_delete_scan)
    tester.test("REGRESSION: Zip upload still works", 
                tester.test_regression_zip_upload)
    tester.test("REGRESSION: GitHub import fails correctly", 
                tester.test_regression_github_import)
    tester.test("REGRESSION: 20 seed scans remain", 
                tester.test_seed_scans_count)
    
    # Cleanup
    tester.cleanup_test_scans()
    
    # Print summary
    success = tester.print_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
