#!/usr/bin/env bash
# ==============================================================================
# Turing-Agent Instant Collaborator Invite & Auto-Accept Script
# ==============================================================================
# Usage:
#   1. Add to your ~/.bashrc or ~/.zshrc:
#        source /path/to/scripts/invite_turing.sh
#      OR copy the function into your shell profile.
#   2. In any repository folder, run:
#        invite_turing
# ==============================================================================

# Configure your n8n Production Webhook URL (or set via environment variable)
TURING_N8N_INVITE_WEBHOOK="${TURING_N8N_INVITE_WEBHOOK:-https://your-n8n-instance.com/webhook/accept-turing-invite}"

invite_turing() {
  local webhook_url="${1:-$TURING_N8N_INVITE_WEBHOOK}"

  # 1. Verify GitHub CLI (gh) availability
  if ! command -v gh &> /dev/null; then
    echo "❌ Error: GitHub CLI ('gh') is not installed or not in PATH."
    echo "   Install it from: https://cli.github.com/"
    return 1
  fi

  # 2. Get current repository from local git context
  local repo
  repo=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)
  if [ -z "$repo" ]; then
    echo "❌ Error: Not inside a valid GitHub repository or unable to fetch repository details."
    return 1
  fi

  echo "🐟 [Turing-Agent] Inviting 'Turing-agent' to $repo as Admin..."

  # 3. Send the invite using your local authenticated GitHub account
  if ! gh api --method PUT \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "/repos/$repo/collaborators/Turing-agent" \
    -f permission=admin > /dev/null; then
    echo "❌ Error: Failed to send collaborator invite to Turing-agent for $repo."
    return 1
  fi

  echo "⚡ [Turing-Agent] Collaborator invitation dispatched. Triggering instant auto-accept..."

  # 4. Ping your n8n webhook to force instant acceptance
  if [ "$webhook_url" != "https://your-n8n-instance.com/webhook/accept-turing-invite" ]; then
    curl -s -m 10 "$webhook_url" > /dev/null
  else
    echo "⚠️ Note: TURING_N8N_INVITE_WEBHOOK is set to default template URL."
    echo "   Update the webhook URL in scripts/invite_turing.sh or export TURING_N8N_INVITE_WEBHOOK."
  fi

  echo "✅ [Turing-Agent] Turing-agent has accepted the invitation and is now an Admin on $repo!"
}

# If executed directly as a script (instead of sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  invite_turing "$@"
fi
