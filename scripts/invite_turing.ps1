<#
.SYNOPSIS
    Turing-Agent Instant Collaborator Invite & Auto-Accept for PowerShell

.DESCRIPTION
    Invites 'Turing-agent' as Admin to the current GitHub repository using the GitHub CLI (gh),
    then immediately invokes the n8n webhook to automatically accept the invitation.

.EXAMPLE
    # In PowerShell:
    . .\scripts\invite_turing.ps1
    Invite-Turing
#>

function Invite-Turing {
    param (
        [string]$WebhookUrl = $env:TURING_N8N_INVITE_WEBHOOK
    )

    if (-not $WebhookUrl) {
        $WebhookUrl = "https://your-n8n-instance.com/webhook/accept-turing-invite"
    }

    # 1. Check gh CLI
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Write-Error "GitHub CLI ('gh') is not installed or not found in PATH. Install from https://cli.github.com/"
        return
    }

    # 2. Get repository nameWithOwner
    $repo = gh repo view --json nameWithOwner -q .nameWithOwner 2>$null
    if (-not $repo) {
        Write-Error "Not inside a valid GitHub repository or unable to fetch repository details."
        return
    }

    Write-Host "🐟 [Turing-Agent] Inviting 'Turing-agent' to $repo as Admin..." -ForegroundColor Cyan

    # 3. Send collaborator invitation
    gh api --method PUT `
        -H "Accept: application/vnd.github+json" `
        -H "X-GitHub-Api-Version: 2022-11-28" `
        "/repos/$repo/collaborators/Turing-agent" `
        -f permission=admin | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to send collaborator invite to Turing-agent for $repo."
        return
    }

    Write-Host "⚡ [Turing-Agent] Invitation dispatched. Triggering instant auto-accept..." -ForegroundColor Yellow

    # 4. Trigger n8n webhook
    if ($WebhookUrl -ne "https://your-n8n-instance.com/webhook/accept-turing-invite") {
        try {
            Invoke-RestMethod -Uri $WebhookUrl -Method Get -TimeoutSec 10 | Out-Null
        } catch {
            Write-Warning "Could not reach webhook URL ($WebhookUrl): $_"
        }
    } else {
        Write-Warning "TURING_N8N_INVITE_WEBHOOK is set to the default placeholder. Please configure your actual n8n Webhook URL."
    }

    Write-Host "✅ [Turing-Agent] Turing-agent has accepted the invitation and is now an Admin on $repo!" -ForegroundColor Green
}

# Alias for ease of use
Set-Alias -Name invite_turing -Value Invite-Turing
