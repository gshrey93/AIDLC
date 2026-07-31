"""Unit tests for the improved 403 classification in core.importer.

Tests the _is_rate_limited() function and the new error codes GitHubAccessDenied and
BitbucketAccessDenied to verify the fix for the user-reported 403 issue.
"""
import sys
import os

sys.path.insert(0, "/app/backend")

from core.importer import _is_rate_limited


class FakeResponse:
    """Mock httpx.Response for testing."""
    def __init__(self, status_code, headers=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'


def test(name, condition, detail=""):
    """Run a single test."""
    if condition:
        print(f"{Colors.GREEN}✅ PASS{Colors.END}: {name}" + (f" :: {detail}" if detail else ""))
        return True
    else:
        print(f"{Colors.RED}❌ FAIL{Colors.END}: {name}" + (f" :: {detail}" if detail else ""))
        return False


def main():
    print(f"\n{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BLUE}IMPORTER 403 FIX UNIT TESTS{Colors.END}")
    print(f"{Colors.BLUE}Testing _is_rate_limited() classifier{Colors.END}")
    print(f"{Colors.BLUE}{'='*70}{Colors.END}\n")
    
    passed = 0
    total = 0
    
    # Test 1: 429 status -> throttled
    total += 1
    resp = FakeResponse(429)
    if test("429 status -> throttled", _is_rate_limited(resp) is True, "429 is always rate limiting"):
        passed += 1
    
    # Test 2: 403 with x-ratelimit-remaining '0' -> throttled
    total += 1
    resp = FakeResponse(403, headers={"x-ratelimit-remaining": "0"})
    if test("403 with x-ratelimit-remaining '0' -> throttled", 
            _is_rate_limited(resp) is True, 
            "Primary GitHub rate limit exhausted"):
        passed += 1
    
    # Test 3: 403 with retry-after header -> throttled (NEW)
    total += 1
    resp = FakeResponse(403, headers={"retry-after": "60"})
    if test("403 with retry-after header -> throttled", 
            _is_rate_limited(resp) is True, 
            "Secondary GitHub rate limit (abuse detection)"):
        passed += 1
    
    # Test 4: 403 with body 'abuse detection mechanism' -> throttled (NEW)
    total += 1
    resp = FakeResponse(403, text='{"message": "You have triggered an abuse detection mechanism. Please retry your request again later."}')
    if test("403 with body 'abuse detection' -> throttled", 
            _is_rate_limited(resp) is True, 
            "GitHub abuse detection message"):
        passed += 1
    
    # Test 5: 403 with body 'API rate limit exceeded' -> throttled (NEW)
    total += 1
    resp = FakeResponse(403, text='{"message": "API rate limit exceeded for user ID 12345."}')
    if test("403 with body 'API rate limit exceeded' -> throttled", 
            _is_rate_limited(resp) is True, 
            "GitHub rate limit message in body"):
        passed += 1
    
    # Test 6: 403 with body 'rate limit' (case insensitive) -> throttled (NEW)
    total += 1
    resp = FakeResponse(403, text='{"message": "Rate Limit Exceeded"}')
    if test("403 with body 'rate limit' (case insensitive) -> throttled", 
            _is_rate_limited(resp) is True, 
            "Generic rate limit message"):
        passed += 1
    
    # Test 7: 403 private repo with remaining quota -> NOT throttled
    total += 1
    resp = FakeResponse(
        403, 
        headers={"x-ratelimit-remaining": "55"},
        text='{"message": "Must have admin rights to Repository.", "documentation_url": "https://docs.github.com/rest"}'
    )
    if test("403 private repo with remaining quota -> NOT throttled", 
            _is_rate_limited(resp) is False, 
            "Private repo access denied, not rate limiting"):
        passed += 1
    
    # Test 8: 404 -> NOT throttled
    total += 1
    resp = FakeResponse(404)
    if test("404 status -> NOT throttled", 
            _is_rate_limited(resp) is False, 
            "404 is not rate limiting"):
        passed += 1
    
    # Test 9: 200 -> NOT throttled
    total += 1
    resp = FakeResponse(200)
    if test("200 status -> NOT throttled", 
            _is_rate_limited(resp) is False, 
            "200 is success"):
        passed += 1
    
    # Test 10: 403 with no rate limit indicators -> NOT throttled
    total += 1
    resp = FakeResponse(403, text='{"message": "Repository access blocked"}')
    if test("403 with no rate limit indicators -> NOT throttled", 
            _is_rate_limited(resp) is False, 
            "Generic 403 without rate limit signals"):
        passed += 1
    
    # Test 11: 403 with x-ratelimit-remaining > 0 and no other signals -> NOT throttled
    total += 1
    resp = FakeResponse(403, headers={"x-ratelimit-remaining": "42"})
    if test("403 with x-ratelimit-remaining > 0 and no other signals -> NOT throttled", 
            _is_rate_limited(resp) is False, 
            "Quota available, not rate limiting"):
        passed += 1
    
    # Test 12: 403 with retry-after AND remaining quota (secondary rate limit) -> throttled
    total += 1
    resp = FakeResponse(
        403, 
        headers={"x-ratelimit-remaining": "45", "retry-after": "120"}
    )
    if test("403 with retry-after AND remaining quota -> throttled", 
            _is_rate_limited(resp) is True, 
            "Secondary rate limit with retry-after header"):
        passed += 1
    
    # Test 13: Edge case - 403 with empty body -> NOT throttled
    total += 1
    resp = FakeResponse(403, text="")
    if test("403 with empty body -> NOT throttled", 
            _is_rate_limited(resp) is False, 
            "No rate limit signals"):
        passed += 1
    
    # Test 14: Edge case - 403 with malformed text that raises exception -> NOT throttled
    total += 1
    class BadResponse:
        status_code = 403
        headers = {}
        @property
        def text(self):
            raise RuntimeError("text decode failed")
    
    resp = BadResponse()
    try:
        result = _is_rate_limited(resp)
        if test("403 with text decode exception -> NOT throttled (graceful)", 
                result is False, 
                "Exception handled gracefully"):
            passed += 1
    except Exception as e:
        test("403 with text decode exception -> NOT throttled (graceful)", 
             False, 
             f"Exception not handled: {e}")
    
    # Summary
    print(f"\n{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BLUE}SUMMARY{Colors.END}")
    print(f"{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"Total tests: {total}")
    print(f"Passed: {Colors.GREEN}{passed}{Colors.END}")
    print(f"Failed: {Colors.RED}{total - passed}{Colors.END}")
    print(f"Success rate: {passed/total*100:.1f}%")
    print(f"{Colors.BLUE}{'='*70}{Colors.END}\n")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
