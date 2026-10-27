# 🐟 Auto-Repro: Autonomous OSS Bug Verifier

> **"A bouncer for your issue tracker: every bug report is reproduced on a clean, disposable environment by an AI web agent before a human looks at it."**

Built for the **"Swim with TinyFish"** Hackathon. Auto-Repro turns incoming bug reports — from Jira or GitHub — into deterministic, autonomous UI verifications.

---

## ⚡ Architecture Overview

```
Jira Cloud (Issue created)  ← the raw "front door" for complaints
        │  webhook (issue created, with attachments)
        ▼
┌──────────────────────────── Host / VPS (Public IP) ────────────────────────────┐
│                                                                                │
│  n8n Pipeline Engine / Webhook Receiver                                        │
│    ├─ Webhook: receives Jira issue event                                       │
│    ├─ Download attachments via Jira API (Basic Auth: email:api_token)          │
│    ├─ POST /upload → re-host media on the provisioner, get public URLs         │
│    ├─ LLM Gatekeeper: rewrite the rant into pristine Markdown + JSON schema    │
│    │     { target_version, reproduction_steps, expected_behavior,              │
│    │       pristine_markdown (with embedded media) }                           │
│    ├─ HTTP → Provisioner /provision   (starts Docker container)                │
│    ├─ HTTP → TinyFish Agent API       (navigates the real UI)                  │
│    ├─ Route on verdict:                                                        │
│    │     ├─ REPRODUCED  → Create GitHub Issue (pristine markdown)              │
│    │     │                → Post TinyFish proof comment                        │
│    │     │                → Jira: transition to "Sent to Engineering"          │
│    │     └─ NOT REPRODUCED → GitHub untouched; Jira comment + "Cannot Reproduce"│
│    └─ HTTP → Provisioner /teardown (idempotent, always cleans up)              │
│                                                                                │
│  Provisioner Service (:4000)                                                   │
│    ├─ POST /provision   → spins up taskboard:<version>, assigns port 8100-8199 │
│    ├─ POST /teardown    → docker rm -f container                              │
│    ├─ POST /upload      → stores Jira attachments under public/uploads         │
│    ├─ GET  /uploads/*   → serves migrated media at a public URL                │
│    ├─ POST /events      → records & broadcasts pipeline progress               │
│    ├─ GET  /events/stream (SSE) → streams real-time updates to Dashboard       │
│    ├─ GET  /            → serves live dark-mode visual dashboard               │
│    └─ TTL Reaper        → kills any test container older than 10 minutes       │
│                                                                                │
│  Disposable Containers: taskboard:<version> (Host ports 8100–8199)              │
└────────────────────────────────────────────────────────────────────────────────┘
        ▲
        │ HTTPS API (Natural Language Task + Real UI Execution)
   TinyFish Cloud Web Agent ── navigates public_url ── returns UI state + errors
```

### The Bouncer Rule

| TinyFish verdict | GitHub | Jira |
| :--- | :--- | :--- |
| **REPRODUCED** | New issue created from `pristine_markdown`, plus a proof comment | Transitioned to "Sent to Engineering" |
| **NOT REPRODUCED** | Never touched | Comment asking for more info + transitioned to "Cannot Reproduce" |

---

## 🚀 Key Features & Guardrails

1. **TinyFish Web Agent at the Core**: TinyFish receives the target URL and natural-language steps, clicks through the real UI, observes visual states, and captures network & console errors.
2. **Jira as the Front Door (The Bouncer)**: Complaints land in Jira. n8n migrates the attachments to a public URL, rewrites the report into a pristine Markdown template, and tests the bug via TinyFish. GitHub is only touched when the bug is actually reproduced.
3. **Self-Hosted Media Migration**: Jira attachments are downloaded with Basic Auth and re-hosted by the existing provisioner (`POST /upload` → `/uploads/<hash>`). No S3 or third-party image host required.
4. **Deterministic Planted Target App (`TaskBoard`)**:
   - `taskboard:v1.0.0`: Working version (Account deletion succeeds with 200 OK).
   - `taskboard:v1.1.0`: Planted bug (Account deletion triggers 500 NullReference error).
5. **Zero Orphaned Containers**: Every run is guaranteed to destroy its container upon completion, failure, or timeout. Additionally, a background **TTL reaper** continuously enforces a 10-minute maximum container lifetime.
6. **Command Injection Prevention**: Version inputs strictly validate against `^v\d+\.\d+\.\d+$` and must match a pre-existing local image. Docker interactions use argument arrays (`execFile`), never raw shell strings.
7. **Upload Guardrails**: `/upload` requires `X-Auth-Token`, only accepts image/video MIME types, caps files at 25 MB, and stores everything under a random hash filename (no path traversal).
8. **Real-time Live Dashboard**: Single-page, vanilla JS dashboard streaming real-time pipeline status over Server-Sent Events (SSE).
9. **Dual Execution Modes**: Works seamlessly with **n8n** (via `n8n/auto-repro-workflow.json`) AND standalone via `scripts/simulate-issue.sh` and `scripts/runner.js`.

---

## 📦 Repository Structure

```
auto-repro/
├── README.md                  # Setup, demo script, and documentation
├── ASSUMPTIONS.md             # Key engineering decisions & assumptions
├── .env.example               # Environment variables template
├── docker-compose.yml         # Compose stack (n8n + provisioner)
├── taskboard/                 # Target app (Node/Express + HTML/JS UI)
│   ├── Dockerfile             # Multi-version Dockerfile (ARG APP_VERSION)
│   ├── server.js              # In-memory API with v1.1.0 planted bug
│   └── public/
│       ├── index.html         # Task list and navigation
│       └── settings.html      # Danger Zone: "Delete Account" button
├── provisioner/               # Orchestration, upload host & UI service (:4000)
│   ├── Dockerfile             # Container definition for provisioner
│   ├── server.js              # Provision, teardown, upload, SSE, HMAC, and TTL reaper
│   └── public/
│       ├── dashboard.html     # Live projector-friendly dark dashboard
│       └── uploads/           # Migrated Jira attachments (git-ignored, temporary)
├── tinyfish/
│   └── adapter.js             # TinyFish Web Agent API adapter & mock mode
├── n8n/
│   └── auto-repro-workflow.json # Importable n8n workflow (Jira front door)
├── scripts/
│   ├── build-images.sh        # Builds taskboard:v1.0.0 and taskboard:v1.1.0
│   ├── setup-vps.sh           # VPS initial configuration (Docker, UFW ports)
│   ├── runner.js              # Standalone pipeline execution engine
│   ├── simulate-issue.sh      # Webhook simulation with HMAC SHA-256
│   └── test-provisioner.sh    # Automated provisioner endpoint test suite
└── demo/
    ├── issue-real-bug.md      # Demo Issue 1: v1.1.0, Delete Account fails (500)
    ├── issue-fake-bug.md      # Demo Issue 2: v1.0.0, Reporter claims delete fails
    └── issue-no-version.md    # Demo Issue 3: Missing version tag (Aborts safely)
```

---

## 🛠️ Quickstart (Run Locally in Under 2 Minutes)

### 1. Prerequisites
- Docker & Docker Compose
- Node.js (v18+)

### 2. Configure Environment
```bash
cp .env.example .env
```
*(Default settings work out of the box with `TINYFISH_MOCK=true`. Add your Jira and GitHub credentials to run the full Jira → n8n → GitHub pipeline.)*

### 3. Build Demo Target Images
```bash
./scripts/build-images.sh
```
This builds `taskboard:v1.0.0` and `taskboard:v1.1.0`.

### 4. Start Provisioner & Dashboard
```bash
cd provisioner && npm install && cd ..
node provisioner/server.js
```
The live dashboard is now available at **[http://localhost:4000](http://localhost:4000)**.

---

## 🎬 90-Second Demo Script

| Time | Action | What Happens / What to Say |
| :--- | :--- | :--- |
| **00:00 - 00:15** | Open `http://localhost:4000` | *"This is Auto-Repro: an AI-powered bouncer for OSS maintainers. Currently idle, 0 containers running."* |
| **00:15 - 00:45** | Run `./scripts/simulate-issue.sh demo/issue-real-bug.md` | *"A user opens issue #430 claiming Delete Account crashes on v1.1.0. Auto-Repro extracts the version, spins up a fresh container on port 8100, and delegates navigation to TinyFish."* |
| **00:45 - 01:05** | Watch Dashboard light up | *TinyFish clicks through `/settings`, triggers the 500 error, and captures network/console evidence. The dashboard immediately flashes **REPRODUCED** in bold red.* |
| **01:05 - 01:15** | Check Terminal / `docker ps` | *The disposable container is instantly destroyed (`docker rm -f`). Zero leftover state.* |
| **01:15 - 01:30** | Run `./scripts/simulate-issue.sh demo/issue-fake-bug.md` | *A user files a false alarm on v1.0.0. TinyFish verifies the clean UI and marks it **NOT_REPRODUCED** in green.* |

---

## 🤖 TinyFish Integration

The TinyFish Web Agent adapter is located in [`tinyfish/adapter.js`](file:///Users/omrajput/Desktop/Projects/Auto-Repro/tinyfish/adapter.js).

### Supported Modes:
1. **Mock Mode (`TINYFISH_MOCK=true` or missing API key)**:
   - Inspects the ephemeral container dynamically.
   - For `v1.1.0`: Returns reproduction output with 500 network error, console error, and error screenshot.
   - For `v1.0.0`: Returns clean success output with 200 OK.
2. **Live Agent API Mode (`TINYFISH_MOCK=false` and `TINYFISH_API_KEY` set)**:
   - Dispatches natural-language goals to `POST https://agent.tinyfish.ai/v1/automation/run`.
   - Uses `output_schema` to enforce standardized response normalization.

---

## 🔄 n8n Self-Hosted Workflow (Jira Front Door)

To run with full n8n automation:
1. Start the stack: `docker compose up -d`
2. Open n8n at `http://localhost:5678`
3. Click **Import from File** and select `n8n/auto-repro-workflow.json`
4. Set credentials for GitHub and Jira, then activate the workflow.

### Jira setup

1. **Create a Jira Cloud project** (free tier is fine) and note your site domain (e.g. `yourcompany.atlassian.net`).
2. **Create an Atlassian API token**: https://id.atlassian.com/manage-profile/security/api-tokens
3. **Fill in `.env`**:
   ```bash
   JIRA_DOMAIN=yourcompany.atlassian.net
   JIRA_EMAIL=your.email@domain.com
   JIRA_API_TOKEN=your_atlassian_api_token
   GITHUB_REPO_OWNER=yourusername
   GITHUB_REPO_NAME=taskboard
   ```
4. **Register the Jira webhook**: Jira → **Settings → System → WebHooks → Create a WebHook**.
   - URL: `http://<VPS_PUBLIC_IP>:5678/webhook/jira-issues`
   - Events: tick **Issue → created** (and optionally **updated**)
   - A JQL filter such as `project = SUP` keeps unrelated issues out.
5. **Find your transition IDs** (project specific) and set them in `.env`:
   ```bash
   curl -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
     "https://$JIRA_DOMAIN/rest/api/2/issue/<ISSUE-KEY>/transitions" | jq '.transitions[] | {id, name}'
   ```
   Then set `JIRA_TRANSITION_SENT_TO_ENG` and `JIRA_TRANSITION_CANNOT_REPRODUCE`.

### Attachment migration (no S3 needed)

Jira attachments are protected, so the workflow:
1. Reads `issue.fields.attachment[].content` from the webhook payload.
2. Downloads each file with `Authorization: Basic base64(JIRA_EMAIL:JIRA_API_TOKEN)`.
3. `POST`s the bytes to the provisioner's `/upload` endpoint.
4. Receives a public URL (`http://<VPS_PUBLIC_IP>:4000/uploads/<hash>.png`) and embeds it in the `pristine_markdown`.

Test the upload endpoint directly:
```bash
curl -F "file=@test.png" -H "X-Auth-Token: $PROVISIONER_TOKEN" \
  http://localhost:4000/upload
# -> {"url":"http://127.0.0.1:4000/uploads/<hash>.png", ...}
```

### LLM Gatekeeper

The `LLM Gatekeeper` node (`@n8n/n8n-nodes-langchain.openAi`) implements the schema below and ships **disabled** so the workflow imports without an OpenAI credential:

```json
{
  "target_version": "string|null",
  "reproduction_steps": ["string"],
  "expected_behavior": "string|null",
  "pristine_markdown": "string"
}
```

To enable it, open the node, add an OpenAI credential, and disable `LLM Gatekeeper (Fallback)`. The fallback Code node produces the same schema deterministically, so the pipeline works either way.

---

## 🔒 Security & Guardrails

- **Zero Arbitrary Image Execution**: Only version strings matching `^v\d+\.\d+\.\d+$` are accepted. The provisioner verifies image existence before launching.
- **No Shell Interpolation**: All Docker operations use `child_process.execFile` with direct arguments array.
- **Ephemeral Isolation**: Each test container has strict resource limits (256MB memory, 0.5 CPU) and is torn down immediately after testing.
- **TTL Reaper**: Background interval reaps any containers older than 10 minutes automatically.
- **Upload Endpoint Guardrails**: `/upload` requires `X-Auth-Token`, accepts only image/video MIME types (plus Jira's `application/octet-stream`), caps uploads at 25 MB, and stores files under random hash names so uploads cannot traverse paths or overwrite each other.
- **Secrets Stay in Env**: Jira and GitHub credentials are read from environment variables only, never hardcoded. The `pristine_markdown` and GitHub issue body contain user content and migrated media URLs, not tokens.
- **HMAC SHA-256 Webhook Verification**: GitHub webhooks are verified with constant-time equality check.

---

## 📝 Assumptions & Limitations
See [`ASSUMPTIONS.md`](file:///Users/omrajput/Desktop/Projects/Auto-Repro/ASSUMPTIONS.md) for detailed notes on scope boundaries, production considerations, and multi-tenant isolation requirements.