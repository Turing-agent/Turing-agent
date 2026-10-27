# 🐟 Auto-Repro: Autonomous OSS Bug Verifier

> **"A bouncer for your issue tracker: every bug report is reproduced on a clean, disposable environment by an AI web agent before a human looks at it."**

Built for the **"Swim with TinyFish"** Hackathon. Auto-Repro turns incoming GitHub issue bug reports into deterministic, autonomous UI verifications.

---

## ⚡ Architecture Overview

```
GitHub (issues.opened)
        │  webhook (HMAC-SHA256 verified)
        ▼
┌──────────────────────────── Host / VPS (Public IP) ────────────────────────────┐
│                                                                                │
│  n8n Pipeline Engine / Webhook Receiver                                        │
│    ├─ Webhook: receives GitHub issue event                                      │
│    ├─ LLM / Parser: extracts {target_version, reproduction_steps, expected}    │
│    ├─ HTTP → Provisioner /provision                                            │
│    ├─ HTTP → TinyFish Agent API                                                │
│    ├─ Judge: computes verdict (REPRODUCED / NOT_REPRODUCED / INCONCLUSIVE)     │
│    ├─ GitHub API: posts structured Markdown comment with evidence              │
│    └─ HTTP → Provisioner /teardown (idempotent, always cleans up)              │
│                                                                                │
│  Provisioner Service (:4000)                                                   │
│    ├─ POST /provision   → spins up taskboard:<version>, assigns port 8100-8199 │
│    ├─ POST /teardown    → docker rm -f container                              │
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

---

## 🚀 Key Features & Guardrails

1. **TinyFish Web Agent at the Core**: TinyFish receives the target URL and natural-language steps, clicks through the real UI, observes visual states, and captures network & console errors.
2. **Deterministic Planted Target App (`TaskBoard`)**:
   - `taskboard:v1.0.0`: Working version (Account deletion succeeds with 200 OK).
   - `taskboard:v1.1.0`: Planted bug (Account deletion triggers 500 NullReference error).
3. **Zero Orphaned Containers**: Every run is guaranteed to destroy its container upon completion, failure, or timeout. Additionally, a background **TTL reaper** continuously enforces a 10-minute maximum container lifetime.
4. **Command Injection Prevention**: Version inputs strictly validate against `^v\d+\.\d+\.\d+$` and must match a pre-existing local image. Docker interactions use argument arrays (`execFile`), never raw shell strings.
5. **Real-time Live Dashboard**: Single-page, vanilla JS dashboard streaming real-time pipeline status over Server-Sent Events (SSE).
6. **Dual Execution Modes**: Works seamlessly with **n8n** (via `n8n/auto-repro-workflow.json`) AND standalone via `scripts/simulate-issue.sh` and `scripts/runner.js`.

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
├── provisioner/               # Orchestration & UI service (:4000)
│   ├── Dockerfile             # Container definition for provisioner
│   ├── server.js              # Provision, teardown, SSE, HMAC, and TTL reaper
│   └── public/
│       └── dashboard.html     # Live projector-friendly dark dashboard
├── tinyfish/
│   └── adapter.js             # TinyFish Web Agent API adapter & mock mode
├── n8n/
│   └── auto-repro-workflow.json # Importable n8n workflow definition
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
*(Default settings work out of the box with `TINYFISH_MOCK=true`).*

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

## 🔄 n8n Self-Hosted Workflow

To run with full n8n automation:
1. Start the stack: `docker compose up -d`
2. Open n8n at `http://localhost:5678`
3. Click **Import from File** and select `n8n/auto-repro-workflow.json`
4. Set credentials for GitHub and activate the workflow.

---

## 🔒 Security & Guardrails

- **Zero Arbitrary Image Execution**: Only version strings matching `^v\d+\.\d+\.\d+$` are accepted. The provisioner verifies image existence before launching.
- **No Shell Interpolation**: All Docker operations use `child_process.execFile` with direct arguments array.
- **Ephemeral Isolation**: Each test container has strict resource limits (256MB memory, 0.5 CPU) and is torn down immediately after testing.
- **TTL Reaper**: Background interval reaps any containers older than 10 minutes automatically.
- **HMAC SHA-256 Webhook Verification**: GitHub webhooks are verified with constant-time equality check.

---

## 📝 Assumptions & Limitations
See [`ASSUMPTIONS.md`](file:///Users/omrajput/Desktop/Projects/Auto-Repro/ASSUMPTIONS.md) for detailed notes on scope boundaries, production considerations, and multi-tenant isolation requirements.