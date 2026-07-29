"""
BLOAT GUARDIAN - ITERATION 3 REGRESSION TEST
Tests all refactored code paths to ensure no behavioral changes.
"""
import io
import json
import os
import sys
import zipfile
from datetime import datetime

import requests

# Backend URL from environment
BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://waste-finder-12.preview.emergentagent.com")
API_BASE = f"{BACKEND_URL}/api"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

class RegressionTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []
        self.warnings = []
        
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
    
    def assert_equal(self, actual, expected, message):
        """Assert values are equal."""
        if actual != expected:
            raise AssertionError(f"{message} Expected {expected}, got {actual}")
    
    def assert_true(self, condition, message):
        """Assert condition is true."""
        if not condition:
            raise AssertionError(message)
    
    # ============================================================
    # REGRESSION TEST 1: Classifier refactor - exact inventory counts
    # ============================================================
    
    def test_classifier_regression(self):
        """REGRESSION: classifier refactor must produce exact same inventory counts."""
        resp = requests.get(f"{API_BASE}/scans/SCN-2026-07-26-0001/results", timeout=30)
        self.assert_equal(resp.status_code, 200, "Get results failed")
        data = resp.json()
        
        inv_summary = data.get("inventory_summary", {})
        self.log(f"   Inventory summary keys: {list(inv_summary.keys())}")
        
        # EXACT counts from the review request (CORRECTED - iteration 3)
        expected = {
            "Agents": 86,
            "Skills": 20,
            "Context and memory": 10,
            "Prompt and orchestration": 24,
            "Source code": 61,
            "Diagrams": 1,
            "Docs": 362,
            "Other text assets": 216
        }
        
        for group, count in expected.items():
            group_data = inv_summary.get(group, {})
            # Handle both dict format and integer format
            if isinstance(group_data, dict):
                actual = group_data.get("count", 0)
            else:
                actual = group_data
            self.assert_equal(actual, count, f"Inventory group '{group}' count mismatch")
            self.log(f"   ✓ {group}: {actual}")
    
    # ============================================================
    # REGRESSION TEST 2: Scoring engine refactor - exact scores
    # ============================================================
    
    def test_scoring_regression(self):
        """REGRESSION: scoring engine refactor must produce exact same scores."""
        resp = requests.get(f"{API_BASE}/scans/SCN-2026-07-26-0001/results", timeout=30)
        self.assert_equal(resp.status_code, 200, "Get results failed")
        data = resp.json()
        
        scan = data["scan"]
        overall_score = scan.get("overall_score")
        verdict = scan.get("verdict")
        
        self.assert_equal(overall_score, 35, "Overall score mismatch")
        self.assert_equal(verdict, "Critical", "Verdict mismatch")
        self.log(f"   ✓ Overall score: {overall_score}")
        self.log(f"   ✓ Verdict: {verdict}")
        
        # EXACT category scores and penalties
        expected_cats = {
            "redundancy": (0, 108),
            "token_bloat": (16, 84),
            "review_overhead": (61, 39),
            "agent_sprawl": (53, 47),
            "architecture_inefficiency": (83, 17)
        }
        
        cats = {c["category"]: (c["score"], c["penalty_points"]) for c in data["category_scores"]}
        
        for cat, (exp_score, exp_penalty) in expected_cats.items():
            actual_score, actual_penalty = cats.get(cat, (None, None))
            self.assert_equal(actual_score, exp_score, f"Category '{cat}' score mismatch")
            self.assert_equal(actual_penalty, exp_penalty, f"Category '{cat}' penalty mismatch")
            self.log(f"   ✓ {cat}: score={actual_score}, penalty={actual_penalty}")
    
    # ============================================================
    # REGRESSION TEST 3: Weighted score formula
    # ============================================================
    
    def test_weighted_score_formula(self):
        """REGRESSION: verify overall_score formula for 5 different scans."""
        resp = requests.get(f"{API_BASE}/scans", timeout=10)
        self.assert_equal(resp.status_code, 200, "List scans failed")
        scans = resp.json()["scans"]
        
        completed = [s for s in scans if s.get("status") == "completed" and s.get("overall_score", 0) > 0]
        self.assert_true(len(completed) >= 5, f"Need at least 5 completed scans, got {len(completed)}")
        
        verified = 0
        for scan in completed[:5]:
            scan_id = scan["id"]
            resp2 = requests.get(f"{API_BASE}/scans/{scan_id}/results", timeout=30)
            if resp2.status_code != 200:
                continue
            
            data = resp2.json()
            overall = data["scan"].get("overall_score")
            cats = {c["category"]: c["score"] for c in data["category_scores"]}
            
            expected = round(
                0.25 * cats.get("redundancy", 0) +
                0.25 * cats.get("token_bloat", 0) +
                0.20 * cats.get("review_overhead", 0) +
                0.20 * cats.get("agent_sprawl", 0) +
                0.10 * cats.get("architecture_inefficiency", 0)
            )
            
            self.assert_equal(overall, expected, f"Scan {scan_id} weighted score mismatch")
            self.log(f"   ✓ {scan_id}: {overall} = 0.25*{cats['redundancy']} + 0.25*{cats['token_bloat']} + ...")
            verified += 1
        
        self.assert_true(verified >= 5, f"Only verified {verified} scans")
    
    # ============================================================
    # REGRESSION TEST 4: Penalty ledger integrity
    # ============================================================
    
    def test_penalty_ledger_regression(self):
        """REGRESSION: penalty_ledger must have 12 rows with correct tier distribution."""
        resp = requests.get(f"{API_BASE}/scans/SCN-2026-07-26-0001/results", timeout=30)
        self.assert_equal(resp.status_code, 200, "Get results failed")
        data = resp.json()
        
        ledger = data.get("penalty_ledger", [])
        self.assert_equal(len(ledger), 12, f"Expected 12 penalty ledger rows, got {len(ledger)}")
        
        specified = [r for r in ledger if r.get("tier") == "specified"]
        scaling = [r for r in ledger if r.get("tier") == "scaling"]
        
        self.assert_equal(len(specified), 7, f"Expected 7 'specified' tier rows, got {len(specified)}")
        self.assert_equal(len(scaling), 5, f"Expected 5 'scaling' tier rows, got {len(scaling)}")
        
        # Verify all penalties respect caps
        for row in ledger:
            applied = row.get("applied", 0)
            cap = row.get("cap", 0)
            self.assert_true(applied <= cap, 
                           f"Penalty '{row.get('rule', '')}' exceeds cap: {applied} > {cap}")
        
        self.log(f"   ✓ 12 rows: 7 specified, 5 scaling")
        self.log(f"   ✓ All penalties <= cap")
    
    # ============================================================
    # REGRESSION TEST 5: Duplicate detection refactor
    # ============================================================
    
    def test_duplicate_detection_regression(self):
        """REGRESSION: duplicate detection must produce exact same counts."""
        resp = requests.get(f"{API_BASE}/scans/SCN-2026-07-26-0001/results", timeout=30)
        self.assert_equal(resp.status_code, 200, "Get results failed")
        data = resp.json()
        
        detections = data.get("detections", {})
        
        expected = {
            "duplicate_clusters_found": 18,
            "repeated_block_groups": 4,
            "oversized_context_files": 8,
            "overlapping_agent_groups": 2,
            "review_stages_inferred": 9,
            "agent_like_files": 140
        }
        
        for key, exp_val in expected.items():
            actual = detections.get(key, 0)
            self.assert_equal(actual, exp_val, f"Detection '{key}' mismatch")
            self.log(f"   ✓ {key}: {actual}")
    
    # ============================================================
    # REGRESSION TEST 6: Assumptions and savings
    # ============================================================
    
    def test_assumptions_regression(self):
        """REGRESSION: assumptions must show correct rates and savings multipliers."""
        resp = requests.get(f"{API_BASE}/scans/SCN-2026-07-26-0001/results", timeout=30)
        self.assert_equal(resp.status_code, 200, "Get results failed")
        data = resp.json()
        
        assumptions = data.get("assumptions", {})
        scan = data["scan"]
        
        input_rate = assumptions.get("input_dollars_per_million")
        output_rate = assumptions.get("output_dollars_per_million")
        
        self.assert_equal(input_rate, 4.0, f"Input rate mismatch")
        self.assert_equal(output_rate, 20.0, f"Output rate mismatch")
        self.log(f"   ✓ Input rate: ${input_rate}/1M")
        self.log(f"   ✓ Output rate: ${output_rate}/1M")
        
        # Verify savings multipliers
        waste = scan.get("estimated_monthly_dollar_waste", 0)
        low = scan.get("estimated_savings_low", 0)
        high = scan.get("estimated_savings_high", 0)
        
        if waste > 0:
            expected_low = round(waste * 0.8, 2)
            expected_high = round(waste * 1.2, 2)
            
            self.assert_true(abs(low - expected_low) < 0.1, 
                           f"Savings low mismatch: expected {expected_low}, got {low}")
            self.assert_true(abs(high - expected_high) < 0.1,
                           f"Savings high mismatch: expected {expected_high}, got {high}")
            self.log(f"   ✓ Savings: ${low} (0.8x) - ${high} (1.2x) of ${waste}")
    
    # ============================================================
    # REGRESSION TEST 7: Seed integrity
    # ============================================================
    
    def test_seed_integrity(self):
        """REGRESSION: seed must have exactly 20 scans with all verdicts."""
        resp = requests.get(f"{API_BASE}/scans", timeout=10)
        self.assert_equal(resp.status_code, 200, "List scans failed")
        data = resp.json()
        
        scans = data["scans"]
        seed_scans = [s for s in scans if s.get("is_seed")]
        
        self.assert_equal(len(seed_scans), 20, f"Expected 20 seed scans, got {len(seed_scans)}")
        
        verdicts = set(s.get("verdict") for s in seed_scans if s.get("verdict"))
        expected_verdicts = {"Lean", "Watchlist", "Wasteful", "Critical"}
        self.assert_true(expected_verdicts.issubset(verdicts), 
                        f"Missing verdicts. Expected {expected_verdicts}, got {verdicts}")
        
        partial = [s for s in seed_scans if s.get("partial_scan")]
        self.assert_true(len(partial) >= 1, f"Expected at least 1 partial_scan, got {len(partial)}")
        
        insufficient = [s for s in seed_scans if s.get("status") == "InsufficientData"]
        self.assert_true(len(insufficient) >= 1, 
                        f"Expected at least 1 InsufficientData, got {len(insufficient)}")
        
        self.log(f"   ✓ 20 seed scans")
        self.log(f"   ✓ All 4 verdicts present: {verdicts}")
        self.log(f"   ✓ {len(partial)} partial scans")
        self.log(f"   ✓ {len(insufficient)} InsufficientData scans")
    
    # ============================================================
    # REGRESSION TEST 8: Exports still work
    # ============================================================
    
    def test_exports_regression(self):
        """REGRESSION: all export types must return 200 with valid content."""
        scan_id = "SCN-2026-07-26-0001"
        
        exports = [
            ("pdf_full", "application/pdf", b"%PDF"),
            ("pdf_redacted", "application/pdf", b"%PDF"),
            ("csv", "text/csv", None),
            ("draft_zip", "application/zip", None),
            ("handoff_zip", "application/zip", None),
        ]
        
        # Get issue count for CSV validation
        resp = requests.get(f"{API_BASE}/scans/{scan_id}/results", timeout=30)
        results = resp.json()
        issue_count = len(results["issues"])
        
        for export_type, content_type, magic in exports:
            resp = requests.get(
                f"{API_BASE}/scans/{scan_id}/export/{export_type}", 
                timeout=60
            )
            self.assert_equal(resp.status_code, 200, f"Export {export_type} failed")
            
            actual_type = resp.headers.get("Content-Type", "")
            self.assert_true(content_type in actual_type, 
                           f"Export {export_type} wrong content type: {actual_type}")
            
            size = len(resp.content)
            self.assert_true(size > 0, f"Export {export_type} returned empty content")
            
            if magic:
                self.assert_true(resp.content.startswith(magic), 
                               f"Export {export_type} invalid format")
            
            self.log(f"   ✓ {export_type}: {size:,} bytes")
        
        # Verify CSV row count
        csv_resp = requests.get(f"{API_BASE}/scans/{scan_id}/export/csv", timeout=30)
        csv_text = csv_resp.text
        csv_lines = [line for line in csv_text.split('\n') if line.strip()]
        data_rows = len(csv_lines) - 1  # Subtract header
        
        self.assert_equal(data_rows, issue_count, 
                         f"CSV row count mismatch: expected {issue_count}, got {data_rows}")
        self.log(f"   ✓ CSV has {data_rows} rows matching {issue_count} issues")
    
    # ============================================================
    # REGRESSION TEST 9: Print views
    # ============================================================
    
    def test_print_views_regression(self):
        """REGRESSION: print views must work and redacted must not leak paths."""
        scan_id = "SCN-2026-07-26-0001"
        
        # Get real file paths
        resp = requests.get(f"{API_BASE}/scans/{scan_id}/files", timeout=10)
        files_data = resp.json()
        real_paths = [f.get("path") for f in files_data["files"][:20] if f.get("path")]
        
        # Test normal print view
        resp1 = requests.get(f"{API_BASE}/scans/{scan_id}/print", timeout=30)
        self.assert_equal(resp1.status_code, 200, "Print view failed")
        html = resp1.text
        self.assert_true(html.startswith("<!doctype html") or html.startswith("<!DOCTYPE html"), 
                        "Print view not HTML")
        
        # Test redacted print view
        resp2 = requests.get(f"{API_BASE}/scans/{scan_id}/print?redacted=true", timeout=30)
        self.assert_equal(resp2.status_code, 200, "Redacted print view failed")
        redacted_html = resp2.text
        
        # Check that real paths are NOT in redacted HTML
        found_paths = []
        for path in real_paths:
            if path and len(path) > 5 and path in redacted_html:
                found_paths.append(path)
        
        self.assert_true(len(found_paths) == 0, 
                        f"Redacted view leaks real paths: {found_paths[:3]}")
        
        # Verify it still contains overall score
        resp3 = requests.get(f"{API_BASE}/scans/{scan_id}", timeout=10)
        scan = resp3.json()
        overall_score = scan.get("overall_score")
        parsed_files = scan.get("parsed_files")
        
        if overall_score:
            self.assert_true(str(overall_score) in redacted_html, 
                           "Redacted view missing overall_score")
        if parsed_files:
            self.assert_true(str(parsed_files) in redacted_html, 
                           "Redacted view missing parsed_files")
        
        self.log(f"   ✓ Print view: {len(html)} bytes")
        self.log(f"   ✓ Redacted view: {len(redacted_html)} bytes, no path leaks")
    
    # ============================================================
    # REGRESSION TEST 10: GitHub import failure
    # ============================================================
    
    def test_github_import_failure(self):
        """REGRESSION: GitHub import must fail gracefully with correct error code."""
        form_data = {
            "source_type": "github",
            "rights_ack": "true",
            "repo_url": "https://github.com/octocat/definitely-not-a-real-repo-9f2x"
        }
        resp = requests.post(f"{API_BASE}/scans", data=form_data, timeout=10)
        self.assert_equal(resp.status_code, 200, "Scan creation should succeed")
        
        scan = resp.json()
        scan_id = scan["id"]
        self.log(f"   Created scan: {scan_id}")
        
        # Wait for scan to complete (should fail quickly)
        import time
        for _ in range(15):
            time.sleep(2)
            resp2 = requests.get(f"{API_BASE}/scans/{scan_id}", timeout=10)
            scan = resp2.json()
            status = scan.get("status")
            if status in ("ImportFailed", "completed", "InsufficientData"):
                break
        
        self.assert_equal(status, "ImportFailed", f"Expected ImportFailed, got {status}")
        error_code = scan.get("error_code")
        self.assert_equal(error_code, "GitHubRepoUnavailable", 
                         f"Expected GitHubRepoUnavailable, got {error_code}")
        
        self.log(f"   ✓ Status: {status}")
        self.log(f"   ✓ Error code: {error_code}")
        
        # Clean up
        requests.delete(f"{API_BASE}/scans/{scan_id}", timeout=10)
    
    # ============================================================
    # REGRESSION TEST 11: Real zip scan
    # ============================================================
    
    def test_real_zip_scan(self):
        """REGRESSION: real zip scan must complete with all stages."""
        # Create a small test zip
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Two near-identical agent files
            agent1 = "# Agent 1\n\nThis is an agent that does task A. Follow the rules.\n" * 20
            agent2 = "# Agent 2\n\nThis is an agent that does task A. Follow the rules.\n" * 20
            zf.writestr("agents/agent1.agent.md", agent1)
            zf.writestr("agents/agent2.agent.md", agent2)
            
            # Instructions
            instructions = "# Instructions\n\nFollow these steps carefully.\n" * 10
            zf.writestr("instructions.md", instructions)
            
            # Orchestrator
            orchestrator = "# Orchestrator\n\nCoordinate the agents.\n" * 10
            zf.writestr("orchestrator.md", orchestrator)
            
            # Context
            context = "# Context\n\nThis is the working context.\n" * 10
            zf.writestr("context/context.md", context)
            
            # Additional files
            for i in range(5):
                zf.writestr(f"docs/doc{i}.md", f"# Document {i}\n\nContent here.\n" * 5)
        
        zip_buffer.seek(0)
        
        form_data = {
            "source_type": "zip",
            "rights_ack": "true"
        }
        files = {"zip_file": ("test-repo.zip", zip_buffer, "application/zip")}
        
        resp = requests.post(f"{API_BASE}/scans", data=form_data, files=files, timeout=10)
        self.assert_equal(resp.status_code, 200, "Scan creation failed")
        
        scan = resp.json()
        scan_id = scan["id"]
        self.log(f"   Created scan: {scan_id}")
        
        # Wait for scan to complete
        import time
        for _ in range(30):
            time.sleep(2)
            resp2 = requests.get(f"{API_BASE}/scans/{scan_id}", timeout=10)
            scan = resp2.json()
            status = scan.get("status")
            progress = scan.get("progress", {})
            percent = progress.get("percent", 0)
            
            if status in ("completed", "InsufficientData", "ImportFailed"):
                break
        
        self.assert_true(status in ("completed", "InsufficientData"), 
                        f"Expected completed or InsufficientData, got {status}")
        self.assert_equal(percent, 100, f"Expected progress 100%, got {percent}%")
        
        # Verify all 7 stages present
        stages = progress.get("stages", [])
        self.assert_equal(len(stages), 7, f"Expected 7 stages, got {len(stages)}")
        
        pending = [s for s in stages if s.get("status") == "pending"]
        self.assert_equal(len(pending), 0, f"Expected no pending stages, got {len(pending)}")
        
        self.log(f"   ✓ Status: {status}")
        self.log(f"   ✓ Progress: {percent}%")
        self.log(f"   ✓ All 7 stages completed")
        
        # Clean up
        requests.delete(f"{API_BASE}/scans/{scan_id}", timeout=10)
    
    # ============================================================
    # NEW BEHAVIOR TEST 12: LLM budget error handling (drafts)
    # ============================================================
    
    def test_llm_budget_drafts(self):
        """NEW: draft generation must return 402 with friendly message on budget error."""
        # Get a completed scan with draft candidates
        resp = requests.get(f"{API_BASE}/scans", timeout=10)
        scans = resp.json()["scans"]
        completed = [s for s in scans if s.get("status") == "completed" and s.get("draft_count", 0) == 0]
        
        if not completed:
            self.log("   ⚠ No completed scans without drafts, skipping")
            return
        
        scan_id = completed[0]["id"]
        
        # Get results to find a draft candidate
        resp2 = requests.get(f"{API_BASE}/scans/{scan_id}/results", timeout=30)
        if resp2.status_code != 200:
            self.log("   ⚠ Could not get results, skipping")
            return
        
        data = resp2.json()
        scan = data["scan"]
        candidates = scan.get("draft_candidates", [])
        
        if not candidates:
            self.log("   ⚠ No draft candidates, skipping")
            return
        
        source_path = candidates[0]
        
        # Try to generate draft (should fail with budget error)
        payload = {"source_path": source_path}
        resp3 = requests.post(f"{API_BASE}/scans/{scan_id}/drafts", json=payload, timeout=30)
        
        # Should return 402 (Payment Required)
        self.assert_equal(resp3.status_code, 402, 
                         f"Expected 402 for budget error, got {resp3.status_code}")
        
        error = resp3.json()
        detail = error.get("detail", "")
        
        # Verify friendly message
        self.assert_true("budget" in detail.lower() or "balance" in detail.lower(), 
                        f"Expected budget message, got: {detail}")
        self.assert_true("litellm" not in detail.lower(), 
                        f"Message should not contain 'litellm': {detail}")
        self.assert_true("chaterror" not in detail.lower(), 
                        f"Message should not contain 'ChatError': {detail}")
        self.assert_true("stack trace" not in detail.lower(), 
                        f"Message should not contain stack trace: {detail}")
        
        self.log(f"   ✓ Status: 402")
        self.log(f"   ✓ Friendly message: {detail[:100]}")
    
    # ============================================================
    # NEW BEHAVIOR TEST 13: LLM budget error handling (refresh-rates)
    # ============================================================
    
    def test_llm_budget_refresh_rates(self):
        """NEW: refresh-rates must return 402 with friendly message on budget error."""
        resp = requests.post(f"{API_BASE}/settings/refresh-rates", timeout=30)
        
        # Should return 402 (Payment Required) due to budget exhaustion
        self.assert_equal(resp.status_code, 402, 
                         f"Expected 402 for budget error, got {resp.status_code}")
        
        error = resp.json()
        detail = error.get("detail", "")
        
        # Verify friendly message
        self.assert_true("budget" in detail.lower() or "balance" in detail.lower(), 
                        f"Expected budget message, got: {detail}")
        self.assert_true("litellm" not in detail.lower(), 
                        f"Message should not contain 'litellm': {detail}")
        self.assert_true("chaterror" not in detail.lower(), 
                        f"Message should not contain 'ChatError': {detail}")
        
        self.log(f"   ✓ Status: 402")
        self.log(f"   ✓ Friendly message: {detail[:100]}")
    
    # ============================================================
    # REGRESSION TEST 14: Settings CRUD
    # ============================================================
    
    def test_settings_crud_regression(self):
        """REGRESSION: settings CRUD operations must work correctly."""
        # GET settings
        resp = requests.get(f"{API_BASE}/settings", timeout=10)
        self.assert_equal(resp.status_code, 200, "Get settings failed")
        settings = resp.json()
        
        assumptions = settings.get("assumptions", {})
        original_runs = assumptions.get("agent_runs_per_month")
        self.log(f"   Original agent_runs_per_month: {original_runs}")
        
        # PUT to change assumptions
        new_runs = original_runs + 50
        patch = {"assumptions": {"agent_runs_per_month": new_runs}}
        resp2 = requests.put(f"{API_BASE}/settings", json=patch, timeout=10)
        self.assert_equal(resp2.status_code, 200, "Update settings failed")
        updated = resp2.json()
        
        self.assert_equal(updated["assumptions"]["agent_runs_per_month"], new_runs,
                         "Settings not updated")
        self.log(f"   ✓ Updated to: {new_runs}")
        
        # PUT with out-of-range value
        bad_patch = {"assumptions": {"output_token_share": 5.0}}
        resp3 = requests.put(f"{API_BASE}/settings", json=bad_patch, timeout=10)
        self.assert_equal(resp3.status_code, 400, "Should reject out-of-range value")
        self.log(f"   ✓ Rejected out-of-range value")
        
        # Reset assumptions
        resp4 = requests.post(f"{API_BASE}/settings/assumptions/reset", timeout=10)
        self.assert_equal(resp4.status_code, 200, "Reset assumptions failed")
        reset = resp4.json()
        
        self.assert_equal(reset["assumptions"]["input_dollars_per_million"], 4.0,
                         "Reset should restore $4.00")
        self.assert_equal(reset["assumptions"]["output_dollars_per_million"], 20.0,
                         "Reset should restore $20.00")
        self.log(f"   ✓ Reset to defaults: $4.00/$20.00")
    
    # ============================================================
    # REGRESSION TEST 15: Delete scan
    # ============================================================
    
    def test_delete_scan_regression(self):
        """REGRESSION: DELETE scan must remove it from the list."""
        # Create a test scan
        form_data = {
            "source_type": "md",
            "rights_ack": "true"
        }
        files = [
            ("md_files", ("test1.md", b"# Test 1\nContent", "text/markdown")),
            ("md_files", ("test2.md", b"# Test 2\nContent", "text/markdown"))
        ]
        resp = requests.post(f"{API_BASE}/scans", data=form_data, files=files, timeout=10)
        self.assert_equal(resp.status_code, 200, "Create test scan failed")
        scan = resp.json()
        scan_id = scan["id"]
        
        self.log(f"   Created test scan: {scan_id}")
        
        # Wait a bit for scan to process
        import time
        time.sleep(2)
        
        # Delete it
        resp2 = requests.delete(f"{API_BASE}/scans/{scan_id}", timeout=10)
        self.assert_equal(resp2.status_code, 200, "Delete scan failed")
        
        # Verify it's gone
        resp3 = requests.get(f"{API_BASE}/scans/{scan_id}", timeout=10)
        self.assert_equal(resp3.status_code, 404, "Scan should be deleted")
        
        self.log(f"   ✓ Successfully deleted scan: {scan_id}")
    
    # ============================================================
    # SUMMARY
    # ============================================================
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*70)
        print("REGRESSION TEST SUMMARY")
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
    """Run all regression tests."""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BLUE}BLOAT GUARDIAN - ITERATION 3 REGRESSION TESTS{Colors.END}")
    print(f"{Colors.BLUE}Backend URL: {BACKEND_URL}{Colors.END}")
    print(f"{Colors.BLUE}{'='*70}{Colors.END}\n")
    
    tester = RegressionTester()
    
    # Core regression tests
    tester.test("REGRESSION 1: Classifier refactor - exact inventory counts", 
                tester.test_classifier_regression)
    tester.test("REGRESSION 2: Scoring engine refactor - exact scores", 
                tester.test_scoring_regression)
    tester.test("REGRESSION 3: Weighted score formula verification", 
                tester.test_weighted_score_formula)
    tester.test("REGRESSION 4: Penalty ledger integrity", 
                tester.test_penalty_ledger_regression)
    tester.test("REGRESSION 5: Duplicate detection refactor", 
                tester.test_duplicate_detection_regression)
    tester.test("REGRESSION 6: Assumptions and savings", 
                tester.test_assumptions_regression)
    tester.test("REGRESSION 7: Seed integrity", 
                tester.test_seed_integrity)
    tester.test("REGRESSION 8: Exports still work", 
                tester.test_exports_regression)
    tester.test("REGRESSION 9: Print views and redaction", 
                tester.test_print_views_regression)
    tester.test("REGRESSION 10: GitHub import failure handling", 
                tester.test_github_import_failure)
    tester.test("REGRESSION 11: Real zip scan completes", 
                tester.test_real_zip_scan)
    
    # New behavior tests
    tester.test("NEW BEHAVIOR 12: LLM budget error (drafts) returns 402", 
                tester.test_llm_budget_drafts)
    tester.test("NEW BEHAVIOR 13: LLM budget error (refresh-rates) returns 402", 
                tester.test_llm_budget_refresh_rates)
    
    # Additional regression tests
    tester.test("REGRESSION 14: Settings CRUD operations", 
                tester.test_settings_crud_regression)
    tester.test("REGRESSION 15: Delete scan", 
                tester.test_delete_scan_regression)
    
    # Print summary
    success = tester.print_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
