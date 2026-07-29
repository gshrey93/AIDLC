#!/bin/bash
set -e

BASE_URL="https://token-audit-7.preview.emergentagent.com/api"
GITHUB_URL="https://github.com/humanlayer/12-factor-agents"

echo "=== Testing GitHub scan (investigating 403 issue) ==="
echo "URL: $GITHUB_URL"
echo ""

# Create scan
echo "Creating scan..."
RESPONSE=$(curl -s -X POST "$BASE_URL/scans" \
  -F "source_type=github" \
  -F "repo_url=$GITHUB_URL" \
  -F "rights_ack=true")

SCAN_ID=$(echo "$RESPONSE" | jq -r '.id')
echo "Scan ID: $SCAN_ID"
echo "Status: $(echo "$RESPONSE" | jq -r '.status')"
echo ""

# Poll for completion (max 2 minutes)
echo "Polling for completion..."
for i in {1..24}; do
  sleep 5
  STATUS_RESPONSE=$(curl -s "$BASE_URL/scans/$SCAN_ID")
  STATUS=$(echo "$STATUS_RESPONSE" | jq -r '.status')
  ERROR_CODE=$(echo "$STATUS_RESPONSE" | jq -r '.error_code')
  ERROR_MSG=$(echo "$STATUS_RESPONSE" | jq -r '.error_message')
  
  echo "[$i] Status: $STATUS"
  
  if [ "$STATUS" = "completed" ]; then
    echo ""
    echo "✓ Scan completed successfully"
    echo "Score: $(echo "$STATUS_RESPONSE" | jq -r '.overall_score')"
    echo "Verdict: $(echo "$STATUS_RESPONSE" | jq -r '.verdict')"
    echo "Files parsed: $(echo "$STATUS_RESPONSE" | jq -r '.parsed_files')"
    
    # Delete the scan
    echo ""
    echo "Cleaning up..."
    curl -s -X DELETE "$BASE_URL/scans/$SCAN_ID" > /dev/null
    echo "✓ Scan deleted"
    exit 0
  fi
  
  if [ "$STATUS" != "queued" ] && [ "$STATUS" != "running" ]; then
    echo ""
    echo "✗ Scan failed"
    echo "Status: $STATUS"
    echo "Error code: $ERROR_CODE"
    echo "Error message: $ERROR_MSG"
    
    # Delete the scan
    curl -s -X DELETE "$BASE_URL/scans/$SCAN_ID" > /dev/null
    echo ""
    echo "✓ Scan deleted"
    exit 1
  fi
done

echo ""
echo "✗ Scan timed out after 2 minutes"
curl -s -X DELETE "$BASE_URL/scans/$SCAN_ID" > /dev/null
exit 1
