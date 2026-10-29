# 🚀 Getting Started with Turing-Agent & TinyFish

**Turing-Agent** (powered by **TinyFish**) is an autonomous open-source QA engineer, live bug investigator, and code repair maintainer for GitHub repositories.

This guide walks you through:
1. Setting up the local backend & orchestration pipeline.
2. Initializing Turing on any new or existing open-source repository in seconds.
3. Interacting with Turing for autonomous triage, live screencast reproduction, and automated PR fixes.

---

## 📋 Prerequisites

Before getting started, ensure you have installed and authenticated:
- **Python 3.10+**
- **Git** & **GitHub CLI (`gh`)**: Authenticated via `gh auth login`
- **ngrok**: For exposing your local backend server to cloud webhooks
- **API Keys**:
  - [Groq API Key](https://console.groq.com/) (for high-speed LLM reasoning and intent parsing)
  - [TinyFish API Key](https://agent.tinyfish.ai/) (for live browser automation & web scraping)
  - GitHub Personal Access Token (PAT) for the `Turing-agent` account

---

## ⚙️ 1. Local Backend Setup

### 1.1. Clone & Install Dependencies
```bash
git clone https://github.com/YASHK-arch/AgentX-TinyFish.git
cd AgentX-TinyFish

# Create and activate a virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 1.2. Configure Environment Variables
Create a `.env` file in the project root:
```env
# Groq LLM Configuration
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-120b

# TinyFish Agent Configuration
TINYFISH_API_KEY=sk-tinyfish_your_key_here
TINYFISH_MOCK=false

# GitHub Integration
GITHUB_TOKEN=ghp_your_github_token_here

# Server
PORT=8000
```

### 1.3. Run the FastAPI Server & ngrok Tunnel
Start the local server with hot reloading enabled:
```bash
uvicorn main:app --reload --port 8000
```

In a separate terminal, start the ngrok tunnel:
```bash
ngrok http 8000
```
Note your public forwarding URL (e.g., `https://your-domain.ngrok-free.dev`).

---

## ⚡ 2. Universal 1-Command Installation on Any Repository

Any open-source maintainer can install and fully initialize **Turing-Agent** on their repository using a single terminal command—**without needing to clone this codebase or download local scripts**.

The installer automatically:
1. Verifies your authenticated GitHub CLI (`gh`).
2. Detects your repository from your local git context (or accepts `owner/repo`).
3. Enables GitHub Discussions on the repository (if not already enabled).
4. Dispatches the collaborator invitation to `Turing-agent` as Admin.
5. Pings the cloud webhook to instantly accept the invitation.
6. Registers the repository webhook to stream discussion events to Turing.

---

### Option 1: Universal 1-Liner (`curl` / `irm` — No Node.js required)

Run this directly in your terminal inside your repository directory:

#### 🪟 Windows PowerShell:
```powershell
irm https://raw.githubusercontent.com/YASHK-arch/Turing-agent/main/scripts/install.ps1 | iex
```

#### 🐧 Linux / 🍎 macOS (Bash / Zsh):
```bash
curl -fsSL https://raw.githubusercontent.com/YASHK-arch/Turing-agent/main/scripts/install.sh | bash
```

> 💡 **Targeting a remote repo from anywhere?** You can pass the repository parameter:
> - **PowerShell**: `& ([scriptblock]::Create((irm https://raw.githubusercontent.com/YASHK-arch/Turing-agent/main/scripts/install.ps1))) -Repo "owner/repo"`
> - **Bash**: `curl -fsSL https://raw.githubusercontent.com/YASHK-arch/Turing-agent/main/scripts/install.sh | bash -s -- owner/repo`

---

### Option 2: Zero-Install NPX Command (Cross-Platform)

If you have Node.js / npm installed, run the universal interactive CLI:

```bash
# Inside your repository folder (auto-detects repo):
npx github:YASHK-arch/Turing-agent

# Or specifying the target repository explicitly:
npx github:YASHK-arch/Turing-agent owner/repo
```

---

### Option 3: Manual 3-Step Setup via GitHub CLI (`gh`)

If you prefer to run each step manually:

#### Step 1: Enable GitHub Discussions
```bash
gh repo edit OWNER/REPO --enable-discussions
```

#### Step 2: Invite `Turing-agent` & Trigger Auto-Accept
```bash
# 1. Dispatch collaborator invitation with Admin permissions
gh api --method PUT \
  -H "Accept: application/vnd.github+json" \
  "/repos/OWNER/REPO/collaborators/Turing-agent" \
  -f permission=admin

# 2. Trigger instant acceptance webhook
# Windows PowerShell:
Invoke-RestMethod -Uri "https://turing.app.n8n.cloud/webhook/accept-turing-invite" -Method Post

# Bash / Linux / macOS:
curl -s -X POST "https://turing.app.n8n.cloud/webhook/accept-turing-invite"
```

#### Step 3: Register the GitHub Webhook
```bash
gh api --method POST \
  -H "Accept: application/vnd.github+json" \
  "/repos/OWNER/REPO/hooks" \
  -f name="web" \
  -F "active=true" \
  -F "events[]=discussion" \
  -F "events[]=discussion_comment" \
  -F "config[url]=https://turing.app.n8n.cloud/webhook/github-events" \
  -F "config[content_type]=json"
```

---

Turing is now fully initialized on the target repository! 🎉

---

## 🔄 3. How Turing Operates (Autonomous Workflow)

### 3.1. Instant Bug Report Intake & Triage
- **Trigger**: Contributor opens a new bug report in GitHub Discussions.
- **Immediate Acknowledgment**: Turing reacts with `👀` (`EYES`) within 1 second.
- **Maintainer Validation**: Turing automatically posts a core maintainer review confirming the issue and initial root cause hypothesis.
- **TinyFish Cross-Issue Correlation**: Uses the **TinyFish Web Fetch API** to scrape open/closed issues and PRs across the repository, posting a threaded correlation report under the validation comment.
- **Single-Validation Guarantee**: This review runs **only once** on discussion creation; subsequent comments will never re-trigger canned templates.

### 3.2. Intent-Driven Live Q&A (`@Turing-agent` mentions)
Contributors can interact live with Turing by commenting in the discussion. The **LLM Intent Classifier** (`turing_qa.py`) parses the inquiry and executes serialized tasks:

| User Inquiry / Action | Intent Detected | What Turing & TinyFish Do |
| :--- | :---: | :--- |
| *"Can you reproduce this bug on the live site?"* | `REPRODUCE_BUG` | Dispatches **TinyFish Web Agent** to navigate the live deployment, interact with the element, capture step screenshots and screencast recordings, and apply the `reproducible` tag. |
| *"Is there any related issue or duplicate?"* | `FIND_RELATED_ISSUES` | Webscrapes repository issues, PRs, and discussions via **TinyFish Web Fetch**, identifies component collisions and active PRs, returning a status table with direct links. |
| *"Instead of modifying NavBar.jsx, why don't we use X?"* | `ANALYZE_PROPOSAL` | Evaluates the contributor's idea against codebase AST, analyzing architectural trade-offs, potential drawbacks, routing/security risks, and concrete code recommendations. |
| *"Which files did you inspect to find this bug?"* | `GENERAL_QA` | Answers conversationally with exact codebase context without boilerplate greetings. |

### 3.3. Maintainer Approval & Autonomous PR Fix
- **Trigger**: Repository maintainer comments `approved` on the discussion thread.
- **Workflow Execution**:
  1. Opens an official GitHub issue labeled `ready-for-work`.
  2. Posts a real-time progress checklist comment in the discussion (`[⏳] Analyzing codebase...`).
  3. Inspects codebase files in parallel (`ThreadPoolExecutor`) and scores relevance.
  4. Synthesizes surgical code modifications using Groq LLM (`openai/gpt-oss-120b`).
  5. Commits changes directly via the GitHub Git Data API to branch `issue-<number>` with co-author credit.
  6. Opens a Pull Request with AI fix summaries, live visual evidence, and closes the issue.
  7. Updates the discussion progress comment to `✅ Turing-agent Fix Completed!` linking the new PR.

---

## 🛠️ 4. n8n Workflow Reference

The repository includes preconfigured, production-ready n8n workflow templates:
- [`turing-agent-workflow.json`](turing-agent-workflow.json): Main pipeline handling discussion webhooks, eyes reactions, `/triage-discussion`, `/chat-turing`, and `/resolve-issue`.
- [`accept-turing-invite-workflow.json`](accept-turing-invite-workflow.json): On-demand webhook endpoint (`/webhook/accept-turing-invite`) accepting repository invitations using `Turing-agent`'s credentials.

To import or update in your n8n workspace:
1. Open n8n Cloud or self-hosted instance.
2. Select **Workflows** -> **Import from File**.
3. Select `turing-agent-workflow.json`.
4. Ensure your GitHub credential and HTTP Request endpoints point to your ngrok tunnel URL.

---

## 📚 5. Additional Documentation
- [`project_context.md`](project_context.md): Deep-dive into technical architecture, Mermaid diagrams, API schemas, and data structures.
- [`main.py`](main.py): Primary FastAPI server implementation.
- [`turing_qa.py`](turing_qa.py): Intent parsing and serialized investigation handlers.
- [`tinyfish_correlator.py`](tinyfish_correlator.py): Web scraping and cross-issue correlation engine.
