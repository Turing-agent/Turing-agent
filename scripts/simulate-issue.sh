#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

ISSUE_FILE="${1:-"${ROOT_DIR}/demo/issue-real-bug.md"}"
N8N_URL="${N8N_WEBHOOK_URL:-"http://localhost:5678/webhook/github-issues"}"
GITHUB_SECRET="${GITHUB_WEBHOOK_SECRET:-"auto_repro_webhook_secret_xyz"}"
PROVISIONER_URL="${PROVISIONER_URL:-"http://127.0.0.1:4000"}"
PROVISIONER_TOKEN="${PROVISIONER_TOKEN:-"autorepro_secret_token_123"}"

if [ ! -f "$ISSUE_FILE" ]; then
  echo "Error: Issue file not found: $ISSUE_FILE"
  exit 1
fi

TITLE=$(head -n 1 "$ISSUE_FILE" | sed 's/^# //')
BODY=$(tail -n +2 "$ISSUE_FILE")
ISSUE_NUM=$((100 + RANDOM % 900))

echo "=========================================================="
echo "  Auto-Repro Simulation: GitHub Issue Opened"
echo "  File: $ISSUE_FILE"
echo "  Issue #: $ISSUE_NUM"
echo "  Title: $TITLE"
echo "=========================================================="

# Build GitHub webhook JSON payload
PAYLOAD=$(node -e "
  const fs = require('fs');
  const title = process.argv[1];
  const body = process.argv[2];
  const issueNum = parseInt(process.argv[3], 10);
  const payload = {
    action: 'opened',
    issue: {
      number: issueNum,
      title: title,
      body: body,
      user: { login: 'demo-reporter' }
    },
    repository: {
      name: 'AgentX-TinyFish',
      owner: { login: 'YASHK-arch' }
    },
    sender: { login: 'demo-reporter' }
  };
  console.log(JSON.stringify(payload));
" "$TITLE" "$BODY" "$ISSUE_NUM")

# Calculate HMAC SHA-256 signature
SIG="sha256=$(printf "%s" "$PAYLOAD" | openssl dgst -sha256 -hmac "$GITHUB_SECRET" | sed 's/^.* //')"

echo "==> Sending webhook payload (HMAC: ${SIG:0:20}...)..."

# Try sending to n8n webhook if available
N8N_RUNNING=false
if curl -s --connect-timeout 1 "${N8N_URL%/webhook/*}/healthz" >/dev/null 2>&1 || curl -s --connect-timeout 1 "http://localhost:5678" >/dev/null 2>&1; then
  N8N_RUNNING=true
fi

if [ "$N8N_RUNNING" = true ]; then
  echo "==> Testing live n8n webhook: $N8N_URL"
  RESP=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$N8N_URL" \
    -H "Content-Type: application/json" \
    -H "X-Hub-Signature-256: $SIG" \
    -H "X-GitHub-Event: issues" \
    -d "$PAYLOAD")
  HTTP_STATUS=$(echo "$RESP" | grep "HTTP_STATUS" | cut -d':' -f2)

  if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "202" ]; then
    echo "==> Webhook accepted by n8n (HTTP $HTTP_STATUS)!"
  else
    echo "==> n8n webhook returned HTTP $HTTP_STATUS (Workflow may not be activated yet in n8n UI)."
    echo "==> Falling back to automated pipeline runner against Provisioner ($PROVISIONER_URL)..."
    node "${ROOT_DIR}/scripts/runner.js" "$ISSUE_FILE"
  fi
else
  echo "==> Note: n8n is not listening on localhost:5678."
  echo "==> Executing automated pipeline runner against Provisioner ($PROVISIONER_URL)..."
  node "${ROOT_DIR}/scripts/runner.js" "$ISSUE_FILE"
fi
