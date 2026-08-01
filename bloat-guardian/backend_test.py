"""Comprehensive backend API tests for Bloat Guardian."""
import csv
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

class BackendTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []
        self.warnings = []
        self.completed_scan_id = None
        self.insufficient_scan_id = None
        
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
    # BASIC ENDPOINT TESTS
    # ============================================================
    
    def test_health(self):
        """Test GET /api/health returns 200 with sane payload."""
        resp = requests.get(f"{API_BASE}/health", timeout=10)
        self.assert_status(resp, 200, "Health check failed")
        data = resp.json()
        self.assert_in("status", data, "Health response missing 'status'")
        self.assert_equal(data["status"], "ok", "Health status not 'ok'")
        self.log(f"   Health: {data}")
    
    def test_config(self):
        """Test GET /api/config returns 200 with sane payload."""
        resp = requests.get(f"{API_BASE}/config", timeout=10)
        self.assert_status(resp, 200, "Config failed")
        data = resp.json()
        required = ["max_archive_mb", "max_files", "github_url_pattern", "inventory_groups", "retention"]
        for key in required:
            self.assert_in(key, data, f"Config missing '{key}'")
        self.log(f"   Max archive: {data['max_archive_mb']} MB")
        self.log(f"   Max files: {data['max_files']}")
    
    def test_me(self):
        """Test GET /api/me returns 200."""
        resp = requests.get(f"{API_BASE}/me", timeout=10)
        self.assert_status(resp, 200, "Me endpoint failed")
        data = resp.json()
        self.assert_in("id", data, "Me response missing 'id'")
        self.log(f"   User: {data.get('display_name', 'N/A')}")
    
    def test_stats_overview(self):
        """Test GET /api/stats/overview returns 200 with sane payload."""
        resp = requests.get(f"{API_BASE}/stats/overview", timeout=10)
        self.assert_status(resp, 200, "Stats overview failed")
        data = resp.json()
        required = ["scans_completed", "duplicate_clusters_found", "estimated_monthly_token_waste",
                   "estimated_monthly_credit_waste", "estimated_monthly_dollar_waste", 
                   "files_recommended_to_consolidate", "verdict_distribution"]
        for key in required:
            self.assert_in(key, data, f"Stats missing '{key}'")
        self.log(f"   Scans completed: {data['scans_completed']}")
        self.log(f"   Token waste: {data['estimated_monthly_token_waste']:,}")
        self.log(f"   Verdict distribution: {data['verdict_distribution']}")
    
    # ============================================================
    # SCAN LIST TESTS
    # ============================================================
    
    def test_list_scans(self):
        """Test GET /api/scans returns 21+ scans with proper seed data."""
        resp = requests.get(f"{API_BASE}/scans", timeout=10)
        self.assert_status(resp, 200, "List scans failed")
        data = resp.json()
        
        self.assert_in("scans", data, "Response missing 'scans'")
        scans = data["scans"]
        self.assert_true(len(scans) >= 21, f"Expected 21+ scans, got {len(scans)}")
        
        # Check seed count
        seed_scans = [s for s in scans if s.get("is_seed")]
        self.assert_equal(len(seed_scans), 20, f"Expected exactly 20 seed scans, got {len(seed_scans)}")
        
        # Check statuses
        statuses = [s.get("status") for s in scans]
        completed = statuses.count("completed")
        import_failed = statuses.count("ImportFailed")
        parse_failed = statuses.count("ParseFailed")
        insufficient = statuses.count("InsufficientData")
        
        self.log(f"   Total scans: {len(scans)}")
        self.log(f"   Seed scans: {len(seed_scans)}")
        self.log(f"   Completed: {completed}")
        self.log(f"   ImportFailed: {import_failed}")
        self.log(f"   ParseFailed: {parse_failed}")
        self.log(f"   InsufficientData: {insufficient}")
        
        self.assert_true(completed >= 17, f"Expected at least 17 completed scans, got {completed}")
        self.assert_true(import_failed >= 1, f"Expected at least 1 ImportFailed scan, got {import_failed}")
        self.assert_true(parse_failed >= 1, f"Expected at least 1 ParseFailed scan, got {parse_failed}")
        self.assert_true(insufficient >= 1, f"Expected at least 1 InsufficientData scan, got {insufficient}")
        
        # Check verdicts
        verdicts = [s.get("verdict") for s in scans if s.get("verdict")]
        verdict_set = set(verdicts)
        self.log(f"   Verdicts found: {verdict_set}")
        
        expected_verdicts = {"Lean", "Watchlist", "Wasteful", "Critical"}
        self.assert_true(expected_verdicts.issubset(verdict_set), 
                        f"Expected all 4 verdicts, got {verdict_set}")
        
        # Check partial_scan
        partial_scans = [s for s in scans if s.get("partial_scan")]
        self.assert_true(len(partial_scans) >= 1, f"Expected at least 1 partial_scan, got {len(partial_scans)}")
        
        # Store a completed scan ID for later tests
        completed_scans = [s for s in scans if s.get("status") == "completed"]
        if completed_scans:
            self.completed_scan_id = completed_scans[0]["id"]
            self.log(f"   Using completed scan: {self.completed_scan_id}")
        
        # Store an InsufficientData scan ID
        insufficient_scans = [s for s in scans if s.get("status") == "InsufficientData"]
        if insufficient_scans:
            self.insufficient_scan_id = insufficient_scans[0]["id"]
            self.log(f"   Using InsufficientData scan: {self.insufficient_scan_id}")
    
    # ============================================================
    # SCAN RESULTS TESTS
    # ============================================================
    
    def test_scan_results(self):
        """Test GET /api/scans/{id}/results for a completed scan."""
        if not self.completed_scan_id:
            raise AssertionError("No completed scan ID available")
        
        resp = requests.get(f"{API_BASE}/scans/{self.completed_scan_id}/results", timeout=10)
        self.assert_status(resp, 200, "Get results failed")
        data = resp.json()
        
        # Check required fields
        required = ["scan", "category_scores", "penalty_ledger", "top_drivers", 
                   "recommended_actions", "assumptions", "detections", "inventory_summary",
                   "files", "issues", "drafts"]
        for key in required:
            self.assert_in(key, data, f"Results missing '{key}'")
        
        # Check category scores
        cats = data["category_scores"]
        self.assert_equal(len(cats), 5, f"Expected 5 category scores, got {len(cats)}")
        
        expected_cats = ["redundancy", "token_bloat", "review_overhead", "agent_sprawl", 
                        "architecture_inefficiency"]
        for cat in cats:
            self.assert_in("category", cat, "Category score missing 'category'")
            self.assert_in("score", cat, "Category score missing 'score'")
            score = cat["score"]
            self.assert_true(0 <= score <= 100, f"Category score {score} out of range 0-100")
        
        cat_names = [c["category"] for c in cats]
        for expected in expected_cats:
            self.assert_in(expected, cat_names, f"Missing category '{expected}'")
        
        # Check top drivers (max 5)
        drivers = data["top_drivers"]
        self.assert_true(len(drivers) <= 5, f"Expected max 5 top drivers, got {len(drivers)}")
        
        self.log(f"   Category scores: {len(cats)}")
        self.log(f"   Issues: {len(data['issues'])}")
        self.log(f"   Drafts: {len(data['drafts'])}")
        self.log(f"   Top drivers: {len(drivers)}")
    
    def test_weighted_score_math(self):
        """Test weighted score calculation matches formula."""
        if not self.completed_scan_id:
            raise AssertionError("No completed scan ID available")
        
        resp = requests.get(f"{API_BASE}/scans/{self.completed_scan_id}/results", timeout=10)
        self.assert_status(resp, 200, "Get results failed")
        data = resp.json()
        
        scan = data["scan"]
        overall = scan.get("overall_score")
        verdict = scan.get("verdict")
        
        if overall is None or overall == 0:
            self.log(f"   Skipping: overall_score is {overall}")
            return
        
        cats = {c["category"]: c["score"] for c in data["category_scores"]}
        
        # Calculate expected score
        expected = round(
            0.25 * cats.get("redundancy", 0) +
            0.25 * cats.get("token_bloat", 0) +
            0.20 * cats.get("review_overhead", 0) +
            0.20 * cats.get("agent_sprawl", 0) +
            0.10 * cats.get("architecture_inefficiency", 0)
        )
        
        self.assert_equal(overall, expected, 
                         f"Overall score mismatch. Categories: {cats}")
        
        # Check verdict band
        if 80 <= overall <= 100:
            expected_verdict = "Lean"
        elif 60 <= overall <= 79:
            expected_verdict = "Watchlist"
        elif 40 <= overall <= 59:
            expected_verdict = "Wasteful"
        else:
            expected_verdict = "Critical"
        
        self.assert_equal(verdict, expected_verdict, 
                         f"Verdict mismatch for score {overall}")
        
        self.log(f"   Overall score: {overall}")
        self.log(f"   Verdict: {verdict}")
        self.log(f"   Math verified ✓")
    
    def test_assumptions_and_savings(self):
        """Test assumptions show correct default rates and savings calculations."""
        if not self.completed_scan_id:
            raise AssertionError("No completed scan ID available")
        
        resp = requests.get(f"{API_BASE}/scans/{self.completed_scan_id}/results", timeout=10)
        self.assert_status(resp, 200, "Get results failed")
        data = resp.json()
        
        assumptions = data["assumptions"]
        scan = data["scan"]
        
        # Check default rates
        input_rate = assumptions.get("input_dollars_per_million")
        output_rate = assumptions.get("output_dollars_per_million")
        
        self.assert_equal(input_rate, 4.0, f"Expected input rate 4.0, got {input_rate}")
        self.assert_equal(output_rate, 20.0, f"Expected output rate 20.0, got {output_rate}")
        
        # Check savings variance
        waste = scan.get("estimated_monthly_dollar_waste", 0)
        low = scan.get("estimated_savings_low", 0)
        high = scan.get("estimated_savings_high", 0)
        
        if waste > 0:
            expected_low = round(waste * 0.8, 2)
            expected_high = round(waste * 1.2, 2)
            
            # Allow small rounding differences
            self.assert_true(abs(low - expected_low) < 0.1, 
                           f"Savings low mismatch: expected {expected_low}, got {low}")
            self.assert_true(abs(high - expected_high) < 0.1,
                           f"Savings high mismatch: expected {expected_high}, got {high}")
        
        self.log(f"   Input rate: ${input_rate}/1M tokens")
        self.log(f"   Output rate: ${output_rate}/1M tokens")
        self.log(f"   Monthly waste: ${waste}")
        self.log(f"   Savings range: ${low} - ${high}")
    
    def test_insufficient_data_scan(self):
        """Test InsufficientData scan has zero savings and null verdict."""
        if not self.insufficient_scan_id:
            self.log("   No InsufficientData scan found, skipping")
            return
        
        resp = requests.get(f"{API_BASE}/scans/{self.insufficient_scan_id}", timeout=10)
        self.assert_status(resp, 200, "Get scan failed")
        scan = resp.json()
        
        self.assert_equal(scan.get("status"), "InsufficientData", "Status not InsufficientData")
        self.assert_equal(scan.get("verdict"), None, "Verdict should be null")
        self.assert_equal(scan.get("estimated_monthly_token_waste"), 0, "Token waste should be 0")
        self.assert_equal(scan.get("estimated_monthly_credit_waste"), 0, "Credit waste should be 0")
        self.assert_equal(scan.get("estimated_monthly_dollar_waste"), 0, "Dollar waste should be 0")
        self.assert_equal(scan.get("estimated_savings_low"), 0, "Savings low should be 0")
        self.assert_equal(scan.get("estimated_savings_high"), 0, "Savings high should be 0")
        
        self.log(f"   InsufficientData scan verified: {self.insufficient_scan_id}")
    
    # ============================================================
    # FILES ENDPOINT TESTS
    # ============================================================
    
    def test_files_endpoint(self):
        """Test GET /api/scans/{id}/files with and without filters."""
        if not self.completed_scan_id:
            raise AssertionError("No completed scan ID available")
        
        # Test without filter
        resp = requests.get(f"{API_BASE}/scans/{self.completed_scan_id}/files", timeout=10)
        self.assert_status(resp, 200, "Get files failed")
        data = resp.json()
        
        self.assert_in("files", data, "Response missing 'files'")
        self.assert_in("summary", data, "Response missing 'summary'")
        
        total_files = len(data["files"])
        self.log(f"   Total files: {total_files}")
        
        # Test with group filter
        resp2 = requests.get(f"{API_BASE}/scans/{self.completed_scan_id}/files?group=Agents", timeout=10)
        self.assert_status(resp2, 200, "Get files with group filter failed")
        data2 = resp2.json()
        
        self.log(f"   Files in 'Agents' group: {len(data2['files'])}")
        
        # Verify summary has inventory groups
        summary = data["summary"]
        self.assert_true(isinstance(summary, dict), "Summary should be a dict")
    
    # ============================================================
    # EXPORT TESTS
    # ============================================================
    
    def test_exports(self):
        """Test all export endpoints return 200 with correct content types."""
        if not self.completed_scan_id:
            raise AssertionError("No completed scan ID available")
        
        exports = [
            ("pdf_full", "application/pdf"),
            ("pdf_redacted", "application/pdf"),
            ("csv", "text/csv"),
            ("draft_zip", "application/zip"),
            ("handoff_zip", "application/zip"),
        ]
        
        for export_type, content_type in exports:
            resp = requests.get(
                f"{API_BASE}/scans/{self.completed_scan_id}/export/{export_type}", 
                timeout=60
            )
            self.assert_status(resp, 200, f"Export {export_type} failed")
            
            actual_type = resp.headers.get("Content-Type", "")
            self.assert_true(content_type in actual_type, 
                           f"Export {export_type} wrong content type: {actual_type}")
            
            size = len(resp.content)
            self.assert_true(size > 0, f"Export {export_type} returned empty content")
            
            self.log(f"   {export_type}: {size:,} bytes, {actual_type}")
        
        # Verify CSV row count matches issue count
        resp = requests.get(f"{API_BASE}/scans/{self.completed_scan_id}/results", timeout=10)
        results = resp.json()
        issue_count = len(results["issues"])
        
        csv_resp = requests.get(f"{API_BASE}/scans/{self.completed_scan_id}/export/csv", timeout=30)
        csv_text = csv_resp.text
        # Parse properly: evidence and description fields legitimately contain quoted newlines,
        # so counting raw lines over-reports the number of records.
        data_rows = len(list(csv.DictReader(io.StringIO(csv_text))))
        
        self.assert_equal(data_rows, issue_count, 
                         f"CSV row count mismatch: expected {issue_count}, got {data_rows}")
        
        # Verify handoff zip contains required files
        handoff_resp = requests.get(
            f"{API_BASE}/scans/{self.completed_scan_id}/export/handoff_zip", 
            timeout=60
        )
        zip_data = io.BytesIO(handoff_resp.content)
        with zipfile.ZipFile(zip_data, 'r') as zf:
            names = zf.namelist()
            required = ["efficiency-summary.md", "recommended-instruction.md", 
                       "recommended-orchestrator.md", "recommended-context.md", "findings.csv"]
            for req in required:
                self.assert_true(any(req in n for n in names), 
                               f"Handoff zip missing {req}")
            self.log(f"   Handoff zip files: {len(names)}")
    
    def test_redaction(self):
        """Test redacted print view contains no real file paths."""
        if not self.completed_scan_id:
            raise AssertionError("No completed scan ID available")
        
        # Get real file paths
        resp = requests.get(f"{API_BASE}/scans/{self.completed_scan_id}/files", timeout=10)
        files_data = resp.json()
        real_paths = [f.get("path") for f in files_data["files"][:10] if f.get("path")]
        
        # Get redacted print view
        resp2 = requests.get(
            f"{API_BASE}/scans/{self.completed_scan_id}/print?redacted=true", 
            timeout=30
        )
        self.assert_status(resp2, 200, "Redacted print view failed")
        html = resp2.text
        
        # Check that real paths are NOT in the HTML
        found_paths = []
        for path in real_paths:
            if path and len(path) > 5 and path in html:
                found_paths.append(path)
        
        self.assert_true(len(found_paths) == 0, 
                        f"Redacted view contains real paths: {found_paths[:3]}")
        
        # Verify it still contains overall score and file counts
        resp3 = requests.get(f"{API_BASE}/scans/{self.completed_scan_id}", timeout=10)
        scan = resp3.json()
        
        overall_score = scan.get("overall_score")
        parsed_files = scan.get("parsed_files")
        
        if overall_score:
            self.assert_true(str(overall_score) in html, "Redacted view missing overall_score")
        if parsed_files:
            self.assert_true(str(parsed_files) in html, "Redacted view missing parsed_files")
        
        self.log(f"   Redaction verified: no real paths found")
    
    def test_export_preview(self):
        """Test GET /api/scans/{id}/export-preview."""
        if not self.completed_scan_id:
            raise AssertionError("No completed scan ID available")
        
        resp = requests.get(f"{API_BASE}/scans/{self.completed_scan_id}/export-preview", timeout=10)
        self.assert_status(resp, 200, "Export preview failed")
        data = resp.json()
        
        required = ["included_sections", "redaction_rules", "page_limits", "csv_columns"]
        for key in required:
            self.assert_in(key, data, f"Export preview missing '{key}'")
        
        self.log(f"   Sections: {len(data['included_sections'])}")
        self.log(f"   Redaction rules: {len(data['redaction_rules'])}")
        self.log(f"   Page limits: {data['page_limits']}")
    
    def test_handoff_endpoint(self):
        """Test GET /api/scans/{id}/handoff."""
        if not self.completed_scan_id:
            raise AssertionError("No completed scan ID available")
        
        resp = requests.get(f"{API_BASE}/scans/{self.completed_scan_id}/handoff", timeout=10)
        self.assert_status(resp, 200, "Handoff endpoint failed")
        data = resp.json()
        
        required = ["prompt", "summary_markdown", "package_files", "manual_instructions"]
        for key in required:
            self.assert_in(key, data, f"Handoff missing '{key}'")
        
        package_files = data["package_files"]
        self.assert_true(len(package_files) >= 5, 
                        f"Expected at least 5 package files, got {len(package_files)}")
        
        self.log(f"   Package files: {len(package_files)}")
        self.log(f"   Manual instructions: {len(data['manual_instructions'])}")
    
    # ============================================================
    # VALIDATION TESTS
    # ============================================================
    
    def test_validation_rights_ack(self):
        """Test POST /api/scans with rights_ack=false returns 400."""
        form_data = {
            "source_type": "github",
            "rights_ack": "false",
            "repo_url": "https://github.com/octocat/Hello-World"
        }
        resp = requests.post(f"{API_BASE}/scans", data=form_data, timeout=10)
        self.assert_status(resp, 400, "Should reject rights_ack=false")
        self.log(f"   Correctly rejected: {resp.json().get('detail', '')[:100]}")
    
    def test_validation_github_url(self):
        """Test POST /api/scans with non-GitHub URL for github source returns 400."""
        form_data = {
            "source_type": "github",
            "rights_ack": "true",
            "repo_url": "https://bitbucket.org/owner/repo"
        }
        resp = requests.post(f"{API_BASE}/scans", data=form_data, timeout=10)
        self.assert_status(resp, 400, "Should reject non-GitHub URL for github source")
        self.log(f"   Correctly rejected: {resp.json().get('detail', '')[:100]}")
    
    def test_validation_zip_extension(self):
        """Test POST /api/scans with .txt file for zip source returns 400."""
        form_data = {
            "source_type": "zip",
            "rights_ack": "true"
        }
        files = {"zip_file": ("test.txt", b"not a zip", "text/plain")}
        resp = requests.post(f"{API_BASE}/scans", data=form_data, files=files, timeout=10)
        self.assert_status(resp, 400, "Should reject .txt file for zip source")
        self.log(f"   Correctly rejected: {resp.json().get('detail', '')[:100]}")
    
    def test_validation_md_extension(self):
        """Test POST /api/scans with .txt file for md source returns 400."""
        form_data = {
            "source_type": "md",
            "rights_ack": "true"
        }
        files = {"md_files": ("test.txt", b"content", "text/plain")}
        resp = requests.post(f"{API_BASE}/scans", data=form_data, files=files, timeout=10)
        self.assert_status(resp, 400, "Should reject .txt file for md source")
        self.log(f"   Correctly rejected: {resp.json().get('detail', '')[:100]}")
    
    # ============================================================
    # SETTINGS TESTS
    # ============================================================
    
    def test_settings_crud(self):
        """Test GET/PUT /api/settings and reset."""
        # GET settings
        resp = requests.get(f"{API_BASE}/settings", timeout=10)
        self.assert_status(resp, 200, "Get settings failed")
        settings = resp.json()
        
        required = ["provider_models", "keys", "assumptions"]
        for key in required:
            self.assert_in(key, settings, f"Settings missing '{key}'")
        
        # Check assumptions bounds
        assumptions = settings["assumptions"]
        self.assert_in("agent_runs_per_month", assumptions, "Missing agent_runs_per_month")
        
        original_runs = assumptions["agent_runs_per_month"]
        self.log(f"   Original agent_runs_per_month: {original_runs}")
        
        # PUT to change assumptions
        new_runs = original_runs + 50
        patch = {"assumptions": {"agent_runs_per_month": new_runs}}
        resp2 = requests.put(f"{API_BASE}/settings", json=patch, timeout=10)
        self.assert_status(resp2, 200, "Update settings failed")
        updated = resp2.json()
        
        self.assert_equal(updated["assumptions"]["agent_runs_per_month"], new_runs,
                         "Settings not updated")
        self.log(f"   Updated agent_runs_per_month: {new_runs}")
        
        # PUT with out-of-range value
        bad_patch = {"assumptions": {"output_token_share": 5.0}}
        resp3 = requests.put(f"{API_BASE}/settings", json=bad_patch, timeout=10)
        self.assert_status(resp3, 400, "Should reject out-of-range value")
        self.log(f"   Correctly rejected out-of-range value")
        
        # Reset assumptions
        resp4 = requests.post(f"{API_BASE}/settings/assumptions/reset", timeout=10)
        self.assert_status(resp4, 200, "Reset assumptions failed")
        reset = resp4.json()
        
        self.assert_equal(reset["assumptions"]["agent_runs_per_month"], 200,
                         "Reset should restore default 200")
        self.log(f"   Reset to default: 200")
    
    # ============================================================
    # BUG FIX 1: DUPLICATE DRAFT IDS
    # ============================================================
    
    def test_duplicate_draft_ids_fixed(self):
        """Test that duplicate draft IDs bug is fixed on SCN-2026-07-29-0006."""
        scan_id = "SCN-2026-07-29-0006"
        
        # (a) Verify all draft ids are unique
        resp = requests.get(f"{API_BASE}/scans/{scan_id}/results", timeout=10)
        self.assert_status(resp, 200, f"Get results for {scan_id} failed")
        data = resp.json()
        
        drafts = data.get("drafts", [])
        self.assert_true(len(drafts) > 0, f"Expected drafts on {scan_id}, got none")
        
        draft_ids = [d["id"] for d in drafts]
        unique_ids = set(draft_ids)
        self.assert_equal(len(draft_ids), len(unique_ids), 
                         f"Found duplicate draft IDs: {draft_ids}")
        self.log(f"   ✓ All {len(draft_ids)} draft IDs are unique")
        
        # (b) Generate a NEW draft for an eligible path that doesn't have one yet
        candidates = data["scan"].get("draft_candidates", [])
        existing_paths = {d["source_path"] for d in drafts}
        available = [c for c in candidates if c["source_path"] not in existing_paths]
        
        if available:
            new_path = available[0]["source_path"]
            self.log(f"   Testing new draft generation for: {new_path}")
            
            resp2 = requests.post(
                f"{API_BASE}/scans/{scan_id}/drafts",
                json={"source_path": new_path},
                timeout=70
            )
            self.assert_status(resp2, 200, f"New draft generation failed for {new_path}")
            new_draft = resp2.json()
            new_id = new_draft["id"]
            
            # Verify no collision
            self.assert_true(new_id not in draft_ids, 
                           f"New draft ID {new_id} collides with existing IDs")
            self.log(f"   ✓ New draft ID {new_id} does not collide")
            
            # (c) REGENERATE the same draft (should replace, not duplicate)
            self.log(f"   Testing draft regeneration for: {new_path}")
            resp3 = requests.post(
                f"{API_BASE}/scans/{scan_id}/drafts",
                json={"source_path": new_path},
                timeout=70
            )
            self.assert_status(resp3, 200, f"Draft regeneration failed for {new_path}")
            regen_draft = resp3.json()
            
            # Verify still only one draft for this path
            resp4 = requests.get(f"{API_BASE}/scans/{scan_id}/results", timeout=10)
            self.assert_status(resp4, 200, "Get results after regen failed")
            updated_drafts = resp4.json().get("drafts", [])
            
            path_drafts = [d for d in updated_drafts if d["source_path"] == new_path]
            self.assert_equal(len(path_drafts), 1, 
                            f"Expected exactly 1 draft for {new_path}, got {len(path_drafts)}")
            
            # Verify no duplicate IDs in the full list
            all_ids = [d["id"] for d in updated_drafts]
            unique_all = set(all_ids)
            self.assert_equal(len(all_ids), len(unique_all), 
                            f"Found duplicate IDs after regeneration: {all_ids}")
            self.log(f"   ✓ Regeneration replaced draft without creating duplicates")
        else:
            self.log(f"   ⚠ No available paths for new draft test (all {len(candidates)} already have drafts)")
    
    # ============================================================
    # BUG FIX 2: MARKDOWN SERIES NAMING
    # ============================================================
    
    def test_markdown_series_naming(self):
        """Test that markdown uploads get unique series names based on file set."""
        # Create 6 tiny .md files
        files_set1 = [
            ("md_files", ("agent1.md", b"# Agent 1\nTest content", "text/markdown")),
            ("md_files", ("agent2.md", b"# Agent 2\nTest content", "text/markdown")),
            ("md_files", ("agent3.md", b"# Agent 3\nTest content", "text/markdown")),
        ]
        
        files_set2 = [
            ("md_files", ("agent1.md", b"# Agent 1\nTest content", "text/markdown")),
            ("md_files", ("agent2.md", b"# Agent 2\nTest content", "text/markdown")),
        ]
        
        form_data = {"source_type": "md", "rights_ack": "true"}
        
        # Upload set1 first time
        self.log("   Uploading file set 1 (first time)...")
        resp1 = requests.post(f"{API_BASE}/scans", data=form_data, files=files_set1, timeout=10)
        self.assert_status(resp1, 200, "First upload failed")
        scan1 = resp1.json()
        time.sleep(3)  # Wait for scan to complete
        
        # Get series_id
        resp1b = requests.get(f"{API_BASE}/scans/{scan1['id']}", timeout=10)
        self.assert_status(resp1b, 200, "Get scan1 failed")
        series1 = resp1b.json().get("series_id")
        self.assert_true(series1, "Scan1 should have a series_id")
        self.log(f"   First upload series: {series1}")
        
        # Upload set1 second time (SAME files)
        self.log("   Uploading file set 1 (second time - same files)...")
        resp2 = requests.post(f"{API_BASE}/scans", data=form_data, files=files_set1, timeout=10)
        self.assert_status(resp2, 200, "Second upload failed")
        scan2 = resp2.json()
        time.sleep(3)
        
        resp2b = requests.get(f"{API_BASE}/scans/{scan2['id']}", timeout=10)
        self.assert_status(resp2b, 200, "Get scan2 failed")
        series2 = resp2b.json().get("series_id")
        self.assert_true(series2, "Scan2 should have a series_id")
        self.log(f"   Second upload series: {series2}")
        
        # Verify SAME series
        self.assert_equal(series1, series2, 
                         "Same file set should produce same series_id")
        self.log(f"   ✓ Same files → same series")
        
        # Check run_number
        resp_series = requests.get(f"{API_BASE}/series/{series1}", timeout=10)
        self.assert_status(resp_series, 200, "Get series failed")
        series_data = resp_series.json()
        self.assert_equal(series_data.get("run_count"), 2, 
                         "Series should have 2 runs")
        
        runs = series_data.get("runs", [])
        run_numbers = [r.get("run_number") for r in runs]
        self.assert_true(1 in run_numbers and 2 in run_numbers, 
                        f"Expected run_numbers 1 and 2, got {run_numbers}")
        self.log(f"   ✓ Series has 2 runs with run_numbers 1 and 2")
        
        # Upload set2 (DIFFERENT files)
        self.log("   Uploading file set 2 (different files)...")
        resp3 = requests.post(f"{API_BASE}/scans", data=form_data, files=files_set2, timeout=10)
        self.assert_status(resp3, 200, "Third upload failed")
        scan3 = resp3.json()
        time.sleep(3)
        
        resp3b = requests.get(f"{API_BASE}/scans/{scan3['id']}", timeout=10)
        self.assert_status(resp3b, 200, "Get scan3 failed")
        series3 = resp3b.json().get("series_id")
        self.assert_true(series3, "Scan3 should have a series_id")
        self.log(f"   Third upload series: {series3}")
        
        # Verify DIFFERENT series
        self.assert_true(series3 != series1, 
                        "Different file set should produce different series_id")
        self.log(f"   ✓ Different files → different series")
        
        # Clean up: delete the test series
        self.log(f"   Cleaning up test series...")
        for sid in [series1, series3]:
            resp_del = requests.delete(f"{API_BASE}/series/{sid}", timeout=10)
            if resp_del.status_code == 200:
                self.log(f"   Deleted series {sid}")
            else:
                self.warnings.append(f"Could not delete test series {sid}")
    
    # ============================================================
    # REGRESSION: SERIES MODEL
    # ============================================================
    
    def test_series_model(self):
        """Test series model counts and SER-C7EB608470FE details."""
        # Check counts
        resp = requests.get(f"{API_BASE}/series?include_archived=true", timeout=10)
        self.assert_status(resp, 200, "List series failed")
        data = resp.json()
        
        counts = data.get("counts", {})
        self.assert_equal(counts.get("total"), 25, 
                         f"Expected 25 total series, got {counts.get('total')}")
        self.assert_equal(counts.get("active"), 5, 
                         f"Expected 5 active series, got {counts.get('active')}")
        self.assert_equal(counts.get("archived"), 20, 
                         f"Expected 20 archived series, got {counts.get('archived')}")
        self.assert_equal(counts.get("runs"), 26, 
                         f"Expected 26 total runs, got {counts.get('runs')}")
        self.log(f"   ✓ Series counts: {counts}")
        
        # Check SER-C7EB608470FE
        series_id = "SER-C7EB608470FE"
        resp2 = requests.get(f"{API_BASE}/series/{series_id}", timeout=10)
        self.assert_status(resp2, 200, f"Get series {series_id} failed")
        series = resp2.json()
        
        self.assert_equal(series.get("run_count"), 2, 
                         f"Expected run_count 2, got {series.get('run_count')}")
        self.assert_equal(series.get("latest_score"), 55, 
                         f"Expected latest_score 55, got {series.get('latest_score')}")
        self.assert_equal(series.get("latest_verdict"), "Wasteful", 
                         f"Expected verdict Wasteful, got {series.get('latest_verdict')}")
        self.assert_equal(series.get("previous_score"), 79, 
                         f"Expected previous_score 79, got {series.get('previous_score')}")
        self.assert_equal(series.get("score_delta"), -24, 
                         f"Expected score_delta -24, got {series.get('score_delta')}")
        
        self.log(f"   ✓ Series {series_id}: run_count=2, latest_score=55, verdict=Wasteful, delta=-24")
        
        # Check runs
        runs = series.get("runs", [])
        self.assert_equal(len(runs), 2, f"Expected 2 runs, got {len(runs)}")
        
        run1 = next((r for r in runs if r.get("id") == "SCN-2026-07-29-0005"), None)
        run2 = next((r for r in runs if r.get("id") == "SCN-2026-07-29-0006"), None)
        
        self.assert_true(run1 is not None, "Run SCN-2026-07-29-0005 not found")
        self.assert_true(run2 is not None, "Run SCN-2026-07-29-0006 not found")
        
        self.assert_equal(run1.get("run_number"), 1, "Run 1 should have run_number 1")
        self.assert_equal(run1.get("overall_score"), 79, "Run 1 should have score 79")
        self.assert_true(run1.get("score_delta") is None, "Run 1 should have null delta")
        
        self.assert_equal(run2.get("run_number"), 2, "Run 2 should have run_number 2")
        self.assert_equal(run2.get("overall_score"), 55, "Run 2 should have score 55")
        self.assert_equal(run2.get("score_delta"), -24, "Run 2 should have delta -24")
        
        self.log(f"   ✓ Run 1: score=79, delta=null")
        self.log(f"   ✓ Run 2: score=55, delta=-24")
    
    # ============================================================
    # REGRESSION: SERIES ARCHIVE TOGGLE
    # ============================================================
    
    def test_series_archive_toggle(self):
        """Test PATCH /api/series/{id}/archive toggles archived status."""
        # Use SER-C7EB608470FE (should be active initially)
        series_id = "SER-C7EB608470FE"
        
        # Get initial state
        resp = requests.get(f"{API_BASE}/series/{series_id}", timeout=10)
        self.assert_status(resp, 200, f"Get series {series_id} failed")
        initial_archived = resp.json().get("archived", False)
        self.log(f"   Initial archived state: {initial_archived}")
        
        # Toggle to opposite
        new_state = not initial_archived
        resp2 = requests.patch(
            f"{API_BASE}/series/{series_id}/archive",
            json={"archived": new_state},
            timeout=10
        )
        self.assert_status(resp2, 200, "Archive toggle failed")
        updated = resp2.json()
        self.assert_equal(updated.get("archived"), new_state, 
                         f"Expected archived={new_state}, got {updated.get('archived')}")
        self.log(f"   ✓ Toggled to archived={new_state}")
        
        # Verify counts updated
        resp3 = requests.get(f"{API_BASE}/series?include_archived=true", timeout=10)
        self.assert_status(resp3, 200, "List series failed")
        counts = resp3.json().get("counts", {})
        self.log(f"   Updated counts: active={counts.get('active')}, archived={counts.get('archived')}")
        
        # Restore original state
        resp4 = requests.patch(
            f"{API_BASE}/series/{series_id}/archive",
            json={"archived": initial_archived},
            timeout=10
        )
        self.assert_status(resp4, 200, "Restore archive state failed")
        restored = resp4.json()
        self.assert_equal(restored.get("archived"), initial_archived, 
                         "Failed to restore original state")
        self.log(f"   ✓ Restored to archived={initial_archived}")
    
    # ============================================================
    # REGRESSION: CSV PARSING
    # ============================================================
    
    def test_csv_parsing(self):
        """Test CSV export is well-formed and parses correctly with csv.DictReader."""
        scan_id = "SCN-2026-07-29-0006"
        
        # Get issue count from results
        resp = requests.get(f"{API_BASE}/scans/{scan_id}/results", timeout=10)
        self.assert_status(resp, 200, "Get results failed")
        data = resp.json()
        expected_count = len(data.get("issues", []))
        self.log(f"   Expected issue count from /results: {expected_count}")
        
        # Get CSV export
        resp2 = requests.get(f"{API_BASE}/scans/{scan_id}/export/csv", timeout=10)
        self.assert_status(resp2, 200, "CSV export failed")
        csv_text = resp2.text
        
        # Parse with csv.DictReader
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        actual_count = len(rows)
        
        self.assert_equal(actual_count, expected_count, 
                         f"CSV row count mismatch. Expected {expected_count}, got {actual_count}")
        self.log(f"   ✓ CSV parsed correctly: {actual_count} rows")
        
        # Verify required columns
        if rows:
            required_cols = ["category", "severity", "title", "description", "evidence"]
            for col in required_cols:
                self.assert_in(col, rows[0], f"CSV missing column '{col}'")
            self.log(f"   ✓ CSV has all required columns")
    
    # ============================================================
    # REGRESSION: SERIES ARCHIVE EXPORT
    # ============================================================
    
    def test_series_archive_export(self):
        """Test GET /api/series/export/archive returns a valid zip."""
        resp = requests.get(f"{API_BASE}/series/export/archive", timeout=30)
        self.assert_status(resp, 200, "Archive export failed")
        
        # Verify it's a zip
        self.assert_true(resp.headers.get("Content-Type") == "application/zip", 
                        "Archive export should be application/zip")
        
        # Parse zip
        zip_data = io.BytesIO(resp.content)
        with zipfile.ZipFile(zip_data, 'r') as zf:
            files = zf.namelist()
            self.assert_in("manifest.csv", files, "Archive missing manifest.csv")
            self.assert_in("README.txt", files, "Archive missing README.txt")
            
            # Check for reports
            pdf_files = [f for f in files if f.startswith("reports/") and f.endswith(".pdf")]
            self.assert_true(len(pdf_files) > 0, "Archive should contain PDF reports")
            
            self.log(f"   ✓ Archive contains {len(files)} files")
            self.log(f"   ✓ Found {len(pdf_files)} PDF reports")
    
    # ============================================================
    # DELETE SCAN TEST
    # ============================================================
    
    def test_delete_scan(self):
        """Test DELETE /api/scans/{id} removes the scan."""
        # Create a test scan first (using md upload with insufficient files)
        form_data = {
            "source_type": "md",
            "rights_ack": "true"
        }
        files = [
            ("md_files", ("test1.md", b"# Test 1\nContent", "text/markdown")),
            ("md_files", ("test2.md", b"# Test 2\nContent", "text/markdown"))
        ]
        resp = requests.post(f"{API_BASE}/scans", data=form_data, files=files, timeout=10)
        self.assert_status(resp, 200, "Create test scan failed")
        scan = resp.json()
        scan_id = scan["id"]
        
        self.log(f"   Created test scan: {scan_id}")
        
        # Wait a bit for scan to process
        time.sleep(2)
        
        # Delete it
        resp2 = requests.delete(f"{API_BASE}/scans/{scan_id}", timeout=10)
        self.assert_status(resp2, 200, "Delete scan failed")
        
        # Verify it's gone
        resp3 = requests.get(f"{API_BASE}/scans/{scan_id}", timeout=10)
        self.assert_status(resp3, 404, "Scan should be deleted")
        
        self.log(f"   Successfully deleted scan: {scan_id}")
    
    # ============================================================
    # SUMMARY
    # ============================================================
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*70)
        print("BACKEND TEST SUMMARY")
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
    """Run all backend tests."""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BLUE}BLOAT GUARDIAN BACKEND API TESTS - ITERATION 8{Colors.END}")
    print(f"{Colors.BLUE}Backend URL: {BACKEND_URL}{Colors.END}")
    print(f"{Colors.BLUE}{'='*70}{Colors.END}\n")
    
    tester = BackendTester()
    
    # Basic endpoints
    tester.test("Health endpoint", tester.test_health)
    tester.test("Config endpoint", tester.test_config)
    tester.test("Me endpoint", tester.test_me)
    tester.test("Stats overview endpoint", tester.test_stats_overview)
    
    # Scan list and results
    tester.test("List scans with seed data", tester.test_list_scans)
    tester.test("Get scan results", tester.test_scan_results)
    tester.test("Weighted score math", tester.test_weighted_score_math)
    tester.test("Assumptions and savings", tester.test_assumptions_and_savings)
    tester.test("InsufficientData scan", tester.test_insufficient_data_scan)
    
    # Files endpoint
    tester.test("Files endpoint with filters", tester.test_files_endpoint)
    
    # Exports
    tester.test("Export endpoints", tester.test_exports)
    tester.test("Redaction verification", tester.test_redaction)
    tester.test("Export preview", tester.test_export_preview)
    tester.test("Handoff endpoint", tester.test_handoff_endpoint)
    
    # Validation
    tester.test("Validation: rights_ack", tester.test_validation_rights_ack)
    tester.test("Validation: GitHub URL", tester.test_validation_github_url)
    tester.test("Validation: zip extension", tester.test_validation_zip_extension)
    tester.test("Validation: md extension", tester.test_validation_md_extension)
    
    # Settings
    tester.test("Settings CRUD", tester.test_settings_crud)
    
    # === BUG FIX VERIFICATION (Iteration 8) ===
    print(f"\n{Colors.YELLOW}{'='*70}{Colors.END}")
    print(f"{Colors.YELLOW}BUG FIX VERIFICATION TESTS{Colors.END}")
    print(f"{Colors.YELLOW}{'='*70}{Colors.END}")
    
    tester.test("BUG FIX 1: Duplicate draft IDs fixed", tester.test_duplicate_draft_ids_fixed)
    tester.test("BUG FIX 2: Markdown series naming", tester.test_markdown_series_naming)
    
    # === REGRESSION TESTS ===
    print(f"\n{Colors.YELLOW}{'='*70}{Colors.END}")
    print(f"{Colors.YELLOW}REGRESSION TESTS{Colors.END}")
    print(f"{Colors.YELLOW}{'='*70}{Colors.END}")
    
    tester.test("REGRESSION: Series model", tester.test_series_model)
    tester.test("REGRESSION: Series archive toggle", tester.test_series_archive_toggle)
    tester.test("REGRESSION: CSV parsing", tester.test_csv_parsing)
    tester.test("REGRESSION: Series archive export", tester.test_series_archive_export)
    
    # Delete
    tester.test("Delete scan", tester.test_delete_scan)
    
    # Print summary
    success = tester.print_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
