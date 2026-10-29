<#
.SYNOPSIS
    Turing-Agent 1-Command Universal Repository Installer (PowerShell)

.DESCRIPTION
    Installs and initializes Turing-Agent (powered by TinyFish) on any GitHub repository.
    1. Verifies GitHub CLI ('gh') authentication.
    2. Enables GitHub Discussions on the repository.
    3. Invites 'Turing-agent' as Admin collaborator.
    4. Automatically accepts the invitation via the cloud webhook.
    5. Configures the repository webhook to stream discussion events to Turing.

.EXAMPLE
    # Run directly from the web inside any local repository:
    irm https://raw.githubusercontent.com/YASHK-arch/Turing-agent/main/scripts/install.ps1 | iex

    # Or specify a remote repository:
    irm https://raw.githubusercontent.com/YASHK-arch/Turing-agent/main/scripts/install.ps1 | iex -Repo "owner/repo"
#>

param (
    [string]$Repo = "",
    [string]$InviteWebhook = "https://turing.app.n8n.cloud/webhook/accept-turing-invite",
    [string]$EventsWebhook = "https://turing.app.n8n.cloud/webhook/github-events"
)

Write-Host @"
================================================================
   🐟 Turing-Agent (powered by TinyFish) Installer
   Autonomous Open-Source QA Maintainer & Bug Investigator
================================================================
"@ -ForegroundColor Cyan

# 1. Verify GitHub CLI (gh)
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Error: GitHub CLI ('gh') is not installed or not in PATH." -ForegroundColor Red
    Write-Host "   Install it from: https://cli.github.com/ and run 'gh auth login'."
    return
}

# Verify authentication
$authCheck = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error: GitHub CLI is not authenticated. Please run 'gh auth login' first." -ForegroundColor Red
    return
}

# 2. Determine target repository
if (-not $Repo) {
    $Repo = gh repo view --json nameWithOwner -q .nameWithOwner 2>$null
}

if (-not $Repo) {
    $Repo = Read-Host "Enter target GitHub repository (format: owner/repo)"
}

if (-not $Repo -or $Repo -notmatch "^[\w\.-]+/[\w\.-]+$") {
    Write-Host "❌ Error: Invalid repository format '$Repo'. Expected 'owner/repo'." -ForegroundColor Red
    return
}

Write-Host "`n🚀 Initializing Turing-Agent on '$Repo'..." -ForegroundColor Green

# 3. Enable GitHub Discussions (if not enabled)
Write-Host "1/4 💬 Ensuring GitHub Discussions are enabled..." -ForegroundColor Yellow
try {
    gh repo edit $Repo --enable-discussions 2>$null | Out-Null
    Write-Host "    ✓ GitHub Discussions active." -ForegroundColor Green
} catch {
    Write-Host "    ℹ Discussions status unchanged or already enabled." -ForegroundColor Gray
}

# 4. Invite Turing-agent as Admin
Write-Host "2/4 🤝 Inviting 'Turing-agent' as Admin collaborator..." -ForegroundColor Yellow
$inviteOut = gh api --method PUT `
    -H "Accept: application/vnd.github+json" `
    -H "X-GitHub-Api-Version: 2022-11-28" `
    "/repos/$Repo/collaborators/Turing-agent" `
    -f permission=admin 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error sending collaborator invitation: $inviteOut" -ForegroundColor Red
    return
}
Write-Host "    ✓ Collaborator invitation dispatched to Turing-agent." -ForegroundColor Green

# 5. Trigger Instant Auto-Accept Webhook
Write-Host "3/4 ⚡ Triggering cloud auto-accept webhook..." -ForegroundColor Yellow
try {
    $res = Invoke-RestMethod -Uri $InviteWebhook -Method Post -TimeoutSec 15
    Start-Sleep -Seconds 2
    Write-Host "    ✓ Invitation accepted! Turing-agent is now an Admin on $Repo." -ForegroundColor Green
} catch {
    Write-Host "    ⚠️ Auto-accept webhook pinged. Verify collaborator acceptance on GitHub." -ForegroundColor Yellow
}

# 6. Register GitHub Events Webhook
Write-Host "4/4 🔗 Configuring repository webhook for discussion events..." -ForegroundColor Yellow
# Check if webhook already exists
$existingHooks = gh api "/repos/$Repo/hooks" --jq ".[].config.url" 2>$null
if ($existingHooks -and ($existingHooks -contains $EventsWebhook)) {
    Write-Host "    ✓ Webhook already configured for $EventsWebhook." -ForegroundColor Green
} else {
    $hookRes = gh api --method POST `
        -H "Accept: application/vnd.github+json" `
        "/repos/$Repo/hooks" `
        -f name="web" `
        -F "active=true" `
        -F "events[]=discussion" `
        -F "events[]=discussion_comment" `
        -F "config[url]=$EventsWebhook" `
        -F "config[content_type]=json" 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host "    ✓ Webhook successfully registered ($EventsWebhook)." -ForegroundColor Green
    } else {
        Write-Host "    ⚠️ Webhook creation returned: $hookRes" -ForegroundColor Yellow
    }
}

Write-Host @"

================================================================
   🎉 Turing-Agent is now fully active on $Repo!
================================================================
✨ What happens next:
  1. Open a new Discussion in $Repo:
     -> Turing immediately reacts with 👀, posts maintainer validation,
        and generates a TinyFish cross-issue correlation report.
  2. Ask questions or tag @Turing-agent in comments:
     -> Turing reproduces frontend bugs live with TinyFish screencasts,
        searches for conflicting issues, or critiques proposals.
  3. Maintainer comments 'approved':
     -> Turing autonomously synthesizes the code fix and opens a PR!
"@ -ForegroundColor Cyan
