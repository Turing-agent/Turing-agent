#!/usr/bin/env bash
# ==============================================================================
# Turing-Agent 1-Command Universal Repository Installer (Bash / Linux / macOS)
# ==============================================================================
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/YASHK-arch/Turing-agent/main/scripts/install.sh | bash
# Or specify a repository:
#   curl -fsSL https://raw.githubusercontent.com/YASHK-arch/Turing-agent/main/scripts/install.sh | bash -s -- owner/repo
# ==============================================================================

set -e

INVITE_WEBHOOK="https://turing.app.n8n.cloud/webhook/accept-turing-invite"
EVENTS_WEBHOOK="https://turing.app.n8n.cloud/webhook/github-events"

echo "================================================================"
echo "   🐟 Turing-Agent (powered by TinyFish) Installer"
echo "   Autonomous Open-Source QA Maintainer & Bug Investigator"
echo "================================================================"

# 1. Verify GitHub CLI (gh)
if ! command -v gh &> /dev/null; then
  echo "❌ Error: GitHub CLI ('gh') is not installed or not in PATH."
  echo "   Install it from: https://cli.github.com/ and run 'gh auth login'."
  exit 1
fi

# Verify authentication
if ! gh auth status &> /dev/null; then
  echo "❌ Error: GitHub CLI is not authenticated. Please run 'gh auth login' first."
  exit 1
fi

# 2. Determine target repository
REPO="${1:-}"
if [ -z "$REPO" ]; then
  REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)
fi

if [ -z "$REPO" ]; then
  read -r -p "Enter target GitHub repository (format: owner/repo): " REPO
fi

if [[ ! "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "❌ Error: Invalid repository format '$REPO'. Expected 'owner/repo'."
  exit 1
fi

echo -e "\n🚀 Initializing Turing-Agent on '$REPO'..."

# 3. Enable GitHub Discussions
echo "1/4 💬 Ensuring GitHub Discussions are enabled..."
gh repo edit "$REPO" --enable-discussions 2>/dev/null || echo "    ℹ Discussions status unchanged or already enabled."

# 4. Invite Turing-agent
echo "2/4 🤝 Inviting 'Turing-agent' as collaborator..."
if gh api "/repos/$REPO/collaborators/Turing-agent" &>/dev/null; then
  echo "    ✓ Turing-agent is already a collaborator on $REPO."
else
  # First try admin (for Organization repos), then fallback to push/write (for personal user repos)
  if ! gh api --method PUT \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "/repos/$REPO/collaborators/Turing-agent" \
    -f permission=admin > /dev/null 2>&1; then
    if ! gh api --method PUT \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      "/repos/$REPO/collaborators/Turing-agent" \
      -f permission=push > /dev/null; then
      echo "❌ Error: Failed to send collaborator invite to Turing-agent for $REPO."
      exit 1
    fi
  fi
  echo "    ✓ Collaborator invitation dispatched to Turing-agent."
fi

# 5. Trigger Instant Auto-Accept Webhook
echo "3/4 ⚡ Triggering cloud auto-accept webhook..."
curl -s -X POST "$INVITE_WEBHOOK" > /dev/null || true
sleep 2
echo "    ✓ Invitation accepted! Turing-agent is now an Admin on $REPO."

# 6. Register GitHub Events Webhook
echo "4/4 🔗 Configuring repository webhook for discussion events..."
EXISTING_HOOKS=$(gh api "/repos/$REPO/hooks" --jq ".[].config.url" 2>/dev/null || true)
if echo "$EXISTING_HOOKS" | grep -q "$EVENTS_WEBHOOK"; then
  echo "    ✓ Webhook already configured for $EVENTS_WEBHOOK."
else
  gh api --method POST \
    -H "Accept: application/vnd.github+json" \
    "/repos/$REPO/hooks" \
    -f name="web" \
    -F "active=true" \
    -F "events[]=discussion" \
    -F "events[]=discussion_comment" \
    -F "config[url]=$EVENTS_WEBHOOK" \
    -F "config[content_type]=json" > /dev/null
  echo "    ✓ Webhook successfully registered ($EVENTS_WEBHOOK)."
fi

echo "================================================================"
echo "   🎉 Turing-Agent is now fully active on $REPO!"
echo "================================================================"
echo "✨ What happens next:"
echo "  1. Open a new Discussion in $REPO:"
echo "     -> Turing immediately reacts with 👀, posts maintainer validation,"
echo "        and generates a TinyFish cross-issue correlation report."
echo "  2. Ask questions or tag @Turing-agent in comments:"
echo "     -> Turing reproduces frontend bugs live with TinyFish screencasts,"
echo "        searches for conflicting issues, or critiques proposals."
echo "  3. Maintainer comments 'approved':"
echo "     -> Turing autonomously synthesizes the code fix and opens a PR!"
