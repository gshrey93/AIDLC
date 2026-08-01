"""Backend API tests for RepoSeries functionality (Iteration 7)."""
import io
import json
import os
import sys
import time
import zipfile
from datetime import datetime

import requests

# Get backend URL from environment
BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://token-audit-7.preview.emergentagent.com")
API_BASE = f"{BACKEND_URL}/api"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

class SeriesTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []
        self.warnings = []
        self.test_series_id = None
        self.test_scan_id = None
        
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
    
    def assert_in(self, item, container, message):
        """Assert item is in container."""
        if item not in container:
            raise AssertionError(message)
    
    def assert_equal(self, actual, expected, message):
        """Assert values are equal."""
        if actual != expected:
            raise AssertionError(f"{message} Expected {expected}, got {actual}")
    
    # ============================================================
    # SERIES ENDPOINT TESTS
    # ============================================================
    
    def test_list_series(self):
        """Test GET /api/series returns proper structure with 25 series for 26 runs."""
        resp = requests.get(f"{API_BASE}/series?include_archived=true", timeout=10)
        self.assert_status(resp, 200, "List series failed")
        data = resp.json()
        
        self.assert_in("series", data, "Response missing 'series'")
        self.assert_in("counts", data, "Response missing 'counts'")
        
        series = data["series"]
        counts = data["counts"]
        
        # Should have 25 series for 26 runs (myday-2.0 has 2 runs)
        self.assert_equal(counts["total"], 25, f"Expected 25 total series, got {counts['total']}")
        self.assert_equal(counts["runs"], 26, f"Expected 26 total runs, got {counts['runs']}")
        
        # 20 seeded demo series should be archived, 5 real ones should be active
        self.assert_equal(counts["archived"], 20, f"Expected 20 archived series, got {counts['archived']}")
        self.assert_equal(counts["active"], 5, f"Expected 5 active series, got {counts['active']}")
        
        self.log(f"   Total series: {counts['total']}")
        self.log(f"   Total runs: {counts['runs']}")
        self.log(f"   Active: {counts['active']}, Archived: {counts['archived']}")
        
        # Verify each series has runs nested
        for s in series:
            self.assert_in("id", s, "Series missing 'id'")
            self.assert_in("runs", s, "Series missing 'runs' array")
            self.assert_in("run_count", s, "Series missing 'run_count'")
            self.assert_in("archived", s, "Series missing 'archived'")
            
            # Verify run_count matches actual runs
            actual_runs = len(s["runs"])
            expected_runs = s["run_count"]
            self.assert_equal(actual_runs, expected_runs, 
                            f"Series {s['id']} run_count mismatch: {actual_runs} vs {expected_runs}")
        
        # Store a test series ID for later tests
        active_series = [s for s in series if not s.get("archived")]
        if active_series:
            self.test_series_id = active_series[0]["id"]
            self.log(f"   Using test series: {self.test_series_id}")
    
    def test_branch_awareness(self):
        """Test that different branches create separate series."""
        resp = requests.get(f"{API_BASE}/series?include_archived=true", timeout=10)
        self.assert_status(resp, 200, "List series failed")
        data = resp.json()
        series = data["series"]
        
        # Look for northwind-labs/proposal-writer on 'develop'
        proposal_writer_develop = None
        for s in series:
            if (s.get("repo_owner") == "northwind-labs" and 
                s.get("repo_name") == "proposal-writer" and 
                s.get("branch") == "develop"):
                proposal_writer_develop = s
                break
        
        self.assert_true(proposal_writer_develop is not None, 
                        "Could not find northwind-labs/proposal-writer@develop series")
        
        # Look for northwind-labs/agentic-crm on 'main'
        agentic_crm_main = None
        for s in series:
            if (s.get("repo_owner") == "northwind-labs" and 
                s.get("repo_name") == "agentic-crm" and 
                s.get("branch") == "main"):
                agentic_crm_main = s
                break
        
        self.assert_true(agentic_crm_main is not None,
                        "Could not find northwind-labs/agentic-crm@main series")
        
        # Verify they are separate series
        self.assert_true(proposal_writer_develop["id"] != agentic_crm_main["id"],
                        "Different repos should have different series IDs")
        
        self.log(f"   Found proposal-writer@develop: {proposal_writer_develop['id']}")
        self.log(f"   Found agentic-crm@main: {agentic_crm_main['id']}")
        self.log(f"   Branch awareness verified ✓")
    
    def test_myday_series(self):
        """Test myday-2.0 series has 2 runs with correct scores and deltas."""
        resp = requests.get(f"{API_BASE}/series?include_archived=true", timeout=10)
        self.assert_status(resp, 200, "List series failed")
        data = resp.json()
        series = data["series"]
        
        # Find myday-2.0 series (SER-C7EB608470FE)
        myday_series = None
        for s in series:
            if s.get("id") == "SER-C7EB608470FE" or s.get("display_name") == "myday-2.0":
                myday_series = s
                break
        
        self.assert_true(myday_series is not None, "Could not find myday-2.0 series")
        
        # Verify series properties
        self.assert_equal(myday_series["run_count"], 2, 
                         f"Expected 2 runs, got {myday_series['run_count']}")
        self.assert_equal(myday_series["latest_score"], 55,
                         f"Expected latest_score 55, got {myday_series['latest_score']}")
        self.assert_equal(myday_series["latest_verdict"], "Wasteful",
                         f"Expected verdict 'Wasteful', got {myday_series['latest_verdict']}")
        self.assert_equal(myday_series["previous_score"], 79,
                         f"Expected previous_score 79, got {myday_series['previous_score']}")
        self.assert_equal(myday_series["score_delta"], -24,
                         f"Expected score_delta -24, got {myday_series['score_delta']}")
        
        # Verify runs
        runs = myday_series["runs"]
        self.assert_equal(len(runs), 2, f"Expected 2 runs, got {len(runs)}")
        
        # Sort runs by run_number
        runs_sorted = sorted(runs, key=lambda r: r.get("run_number", 0))
        
        # Run 1: SCN-2026-07-29-0005, score 79, delta null
        run1 = runs_sorted[0]
        self.assert_equal(run1["id"], "SCN-2026-07-29-0005",
                         f"Expected run 1 ID SCN-2026-07-29-0005, got {run1['id']}")
        self.assert_equal(run1["run_number"], 1,
                         f"Expected run_number 1, got {run1['run_number']}")
        self.assert_equal(run1["overall_score"], 79,
                         f"Expected score 79, got {run1['overall_score']}")
        self.assert_true(run1.get("score_delta") is None,
                        f"Expected score_delta null for first run, got {run1.get('score_delta')}")
        
        # Run 2: SCN-2026-07-29-0006, score 55, delta -24
        run2 = runs_sorted[1]
        self.assert_equal(run2["id"], "SCN-2026-07-29-0006",
                         f"Expected run 2 ID SCN-2026-07-29-0006, got {run2['id']}")
        self.assert_equal(run2["run_number"], 2,
                         f"Expected run_number 2, got {run2['run_number']}")
        self.assert_equal(run2["overall_score"], 55,
                         f"Expected score 55, got {run2['overall_score']}")
        self.assert_equal(run2["score_delta"], -24,
                         f"Expected score_delta -24, got {run2['score_delta']}")
        
        self.log(f"   Series ID: {myday_series['id']}")
        self.log(f"   Run 1: {run1['id']}, score={run1['overall_score']}, delta={run1.get('score_delta')}")
        self.log(f"   Run 2: {run2['id']}, score={run2['overall_score']}, delta={run2.get('score_delta')}")
        self.log(f"   myday-2.0 series verified ✓")
    
    def test_get_scan_with_series(self):
        """Test GET /api/scans/{id} returns series_id, run_number, score_delta and embedded series."""
        # Use a seeded scan ID
        scan_id = "SCN-2026-07-26-0001"
        
        resp = requests.get(f"{API_BASE}/scans/{scan_id}", timeout=10)
        self.assert_status(resp, 200, f"Get scan {scan_id} failed")
        data = resp.json()
        
        # Verify new fields
        self.assert_in("series_id", data, "Scan missing 'series_id'")
        self.assert_in("run_number", data, "Scan missing 'run_number'")
        self.assert_in("score_delta", data, "Scan missing 'score_delta'")
        self.assert_in("series", data, "Scan missing embedded 'series' object")
        
        series = data["series"]
        self.assert_in("id", series, "Embedded series missing 'id'")
        self.assert_equal(series["id"], data["series_id"],
                         "Embedded series ID should match series_id")
        
        self.log(f"   Scan ID: {scan_id}")
        self.log(f"   Series ID: {data['series_id']}")
        self.log(f"   Run number: {data['run_number']}")
        self.log(f"   Score delta: {data.get('score_delta')}")
        self.log(f"   Embedded series verified ✓")
    
    def test_export_links(self):
        """Test all 5 export links plus print and export-preview work on a seeded scan."""
        scan_id = "SCN-2026-07-26-0001"
        
        exports = [
            ("pdf_full", "application/pdf"),
            ("pdf_redacted", "application/pdf"),
            ("csv", "text/csv"),
            ("draft_zip", "application/zip"),
            ("handoff_zip", "application/zip"),
        ]
        
        for export_type, content_type in exports:
            resp = requests.get(
                f"{API_BASE}/scans/{scan_id}/export/{export_type}", 
                timeout=60
            )
            self.assert_status(resp, 200, f"Export {export_type} failed")
            
            actual_type = resp.headers.get("Content-Type", "")
            self.assert_true(content_type in actual_type, 
                           f"Export {export_type} wrong content type: {actual_type}")
            
            size = len(resp.content)
            self.assert_true(size > 0, f"Export {export_type} returned empty content")
            
            self.log(f"   {export_type}: {size:,} bytes")
        
        # Test print view
        resp = requests.get(f"{API_BASE}/scans/{scan_id}/print", timeout=30)
        self.assert_status(resp, 200, "Print view failed")
        self.log(f"   print view: {len(resp.text):,} chars")
        
        # Test export-preview
        resp = requests.get(f"{API_BASE}/scans/{scan_id}/export-preview", timeout=10)
        self.assert_status(resp, 200, "Export preview failed")
        self.log(f"   export-preview: OK")
        
        self.log(f"   All export links verified ✓")
    
    def test_archive_toggle(self):
        """Test PATCH /api/series/{id}/archive toggles archived status."""
        if not self.test_series_id:
            raise AssertionError("No test series ID available")
        
        # Get current state
        resp = requests.get(f"{API_BASE}/series/{self.test_series_id}", timeout=10)
        self.assert_status(resp, 200, "Get series failed")
        original = resp.json()
        original_archived = original.get("archived", False)
        
        self.log(f"   Original archived state: {original_archived}")
        
        # Toggle to archived
        resp2 = requests.patch(
            f"{API_BASE}/series/{self.test_series_id}/archive",
            json={"archived": True},
            timeout=10
        )
        self.assert_status(resp2, 200, "Archive series failed")
        archived = resp2.json()
        self.assert_equal(archived["archived"], True, "Series should be archived")
        
        # Verify counts updated
        resp3 = requests.get(f"{API_BASE}/series?include_archived=true", timeout=10)
        data3 = resp3.json()
        counts_after_archive = data3["counts"]
        self.log(f"   After archive - Active: {counts_after_archive['active']}, Archived: {counts_after_archive['archived']}")
        
        # Toggle back to active
        resp4 = requests.patch(
            f"{API_BASE}/series/{self.test_series_id}/archive",
            json={"archived": False},
            timeout=10
        )
        self.assert_status(resp4, 200, "Unarchive series failed")
        unarchived = resp4.json()
        self.assert_equal(unarchived["archived"], False, "Series should be unarchived")
        
        # Verify counts updated again
        resp5 = requests.get(f"{API_BASE}/series?include_archived=true", timeout=10)
        data5 = resp5.json()
        counts_after_unarchive = data5["counts"]
        self.log(f"   After unarchive - Active: {counts_after_unarchive['active']}, Archived: {counts_after_unarchive['archived']}")
        
        # Restore original state
        if original_archived != unarchived["archived"]:
            requests.patch(
                f"{API_BASE}/series/{self.test_series_id}/archive",
                json={"archived": original_archived},
                timeout=10
            )
            self.log(f"   Restored to original state: archived={original_archived}")
        
        self.log(f"   Archive toggle verified ✓")
    
    def test_archive_bundle_export(self):
        """Test GET /api/series/export/archive returns a zip with manifest.csv."""
        resp = requests.get(f"{API_BASE}/series/export/archive", timeout=60)
        self.assert_status(resp, 200, "Archive bundle export failed")
        
        content_type = resp.headers.get("Content-Type", "")
        self.assert_true("application/zip" in content_type,
                        f"Expected application/zip, got {content_type}")
        
        # Verify it's a valid zip
        zip_data = io.BytesIO(resp.content)
        with zipfile.ZipFile(zip_data, 'r') as zf:
            names = zf.namelist()
            
            # Check for required files
            self.assert_true(any("manifest.csv" in n for n in names),
                           "Archive bundle missing manifest.csv")
            self.assert_true(any("README.txt" in n for n in names),
                           "Archive bundle missing README.txt")
            self.assert_true(any("generated-at.txt" in n for n in names),
                           "Archive bundle missing generated-at.txt")
            
            # Check for reports and findings
            pdf_files = [n for n in names if n.endswith(".pdf")]
            csv_files = [n for n in names if n.endswith(".csv") and "manifest" not in n]
            
            self.assert_true(len(pdf_files) > 0, "Archive bundle has no PDF reports")
            self.assert_true(len(csv_files) > 0, "Archive bundle has no findings CSV files")
            
            # Read and verify manifest.csv
            manifest_file = [n for n in names if "manifest.csv" in n][0]
            with zf.open(manifest_file) as f:
                manifest_text = f.read().decode('utf-8')
                lines = manifest_text.strip().split('\n')
                
                # Should have header + data rows
                self.assert_true(len(lines) > 1, "Manifest CSV has no data rows")
                
                # Check header has required columns
                header = lines[0].lower()
                required_cols = ["series_id", "display_name", "latest_score", "latest_verdict", 
                               "score_delta", "run_count"]
                for col in required_cols:
                    self.assert_true(col in header,
                                   f"Manifest CSV missing column '{col}'")
                
                self.log(f"   Archive bundle: {len(resp.content):,} bytes")
                self.log(f"   Files in bundle: {len(names)}")
                self.log(f"   PDF reports: {len(pdf_files)}")
                self.log(f"   CSV findings: {len(csv_files)}")
                self.log(f"   Manifest rows: {len(lines) - 1}")
    
    def test_backfill_idempotent(self):
        """Test POST /api/series/backfill is idempotent."""
        # First call
        resp1 = requests.post(f"{API_BASE}/series/backfill", timeout=30)
        self.assert_status(resp1, 200, "Backfill failed")
        data1 = resp1.json()
        
        self.assert_in("scans_attached", data1, "Response missing 'scans_attached'")
        self.assert_in("series_total", data1, "Response missing 'series_total'")
        
        scans_attached_1 = data1["scans_attached"]
        series_total_1 = data1["series_total"]
        
        self.log(f"   First call - Scans attached: {scans_attached_1}, Series total: {series_total_1}")
        
        # Second call should attach 0 scans
        resp2 = requests.post(f"{API_BASE}/series/backfill", timeout=30)
        self.assert_status(resp2, 200, "Second backfill failed")
        data2 = resp2.json()
        
        scans_attached_2 = data2["scans_attached"]
        series_total_2 = data2["series_total"]
        
        self.assert_equal(scans_attached_2, 0,
                         f"Second backfill should attach 0 scans, got {scans_attached_2}")
        self.assert_equal(series_total_2, series_total_1,
                         f"Series total should not change: {series_total_1} vs {series_total_2}")
        
        self.log(f"   Second call - Scans attached: {scans_attached_2}, Series total: {series_total_2}")
        self.log(f"   Idempotency verified ✓")
    
    def test_retention_rule_removed(self):
        """Test POST /api/admin/retention does NOT delete real scans."""
        # Get scan count before
        resp1 = requests.get(f"{API_BASE}/scans", timeout=10)
        data1 = resp1.json()
        scan_count_before = len(data1["scans"])
        
        # Call retention
        resp2 = requests.post(f"{API_BASE}/admin/retention", timeout=30)
        self.assert_status(resp2, 200, "Retention call failed")
        
        # Get scan count after
        resp3 = requests.get(f"{API_BASE}/scans", timeout=10)
        data3 = resp3.json()
        scan_count_after = len(data3["scans"])
        
        self.assert_equal(scan_count_after, scan_count_before,
                         f"Retention should not delete scans: {scan_count_before} vs {scan_count_after}")
        
        # Verify config shows retention settings
        resp4 = requests.get(f"{API_BASE}/config", timeout=10)
        config = resp4.json()
        retention = config.get("retention", {})
        
        self.assert_true(retention.get("keep_recent_scans") is None,
                        f"keep_recent_scans should be null, got {retention.get('keep_recent_scans')}")
        self.assert_equal(retention.get("prune_old_scans"), False,
                         f"prune_old_scans should be false, got {retention.get('prune_old_scans')}")
        
        self.log(f"   Scan count before: {scan_count_before}")
        self.log(f"   Scan count after: {scan_count_after}")
        self.log(f"   Retention config: {retention}")
        self.log(f"   Retention rule verified ✓")
    
    # ============================================================
    # SUMMARY
    # ============================================================
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*70)
        print("SERIES API TEST SUMMARY")
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
        
        if self.warnings:
            print(f"\n{Colors.YELLOW}Warnings:{Colors.END}")
            for w in self.warnings:
                print(f"  - {w}")
        
        print("="*70)
        
        return self.tests_failed == 0


def main():
    """Run all series tests."""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BLUE}BLOAT GUARDIAN SERIES API TESTS (Iteration 7){Colors.END}")
    print(f"{Colors.BLUE}Backend URL: {BACKEND_URL}{Colors.END}")
    print(f"{Colors.BLUE}{'='*70}{Colors.END}\n")
    
    tester = SeriesTester()
    
    # Series endpoint tests
    tester.test("GET /api/series returns 25 series for 26 runs", tester.test_list_series)
    tester.test("Branch awareness: separate series for different branches", tester.test_branch_awareness)
    tester.test("myday-2.0 series has 2 runs with correct scores", tester.test_myday_series)
    tester.test("GET /api/scans/{id} includes series data", tester.test_get_scan_with_series)
    tester.test("All export links work on seeded scan", tester.test_export_links)
    tester.test("PATCH /api/series/{id}/archive toggles archived", tester.test_archive_toggle)
    tester.test("GET /api/series/export/archive returns valid zip", tester.test_archive_bundle_export)
    tester.test("POST /api/series/backfill is idempotent", tester.test_backfill_idempotent)
    tester.test("Retention rule removed: no scan deletion", tester.test_retention_rule_removed)
    
    # Print summary
    success = tester.print_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
