# Assumptions & Decisions

1. **Target App Technology**: Built using Node.js / Express with vanilla HTML/JS in `taskboard/public`. It listens on port 80 inside the container.
2. **Deterministic Bug in v1.1.0**:
   - `GET /version` returns the version string (`v1.0.0` or `v1.1.0`).
   - For `v1.0.0`: `POST /api/delete-account` returns HTTP 200 with `{"success": true, "message": "Account deleted successfully"}`. UI sets `#status` to green "Account deleted successfully".
   - For `v1.1.0`: `POST /api/delete-account` returns HTTP 500 with `{"error": "NullReference: user.profile is undefined"}`. UI sets `#status` to red "Something went wrong" and logs `console.error("delete-account failed: 500")`.
3. **Provisioner Service**:
   - Built with Node.js and Express.
   - Listens on port 4000.
   - Requires `X-Auth-Token: $PROVISIONER_TOKEN` for all mutating endpoints.
   - Uses `dockerode` or direct Docker API / `execFile` without shell interpolation to prevent command injection.
   - Container port allocation dynamically scans 8100-8199.
   - Has a background TTL reaper checking every 30s for containers labeled `autorepro=true` with start epoch older than 10 minutes.
4. **TinyFish Adapter**:
   - Supports both mock mode (`TINYFISH_MOCK=true`) and live TinyFish Agent API (`https://agent.tinyfish.ai/v1/automation/run` with `X-API-Key`).
   - Normalizes output to `{ completed, final_ui_state, visible_errors, console_errors, network_errors, screenshot_url, agent_summary }`.
5. **n8n Workflow**:
   - Exported as self-contained JSON in `n8n/auto-repro-workflow.json`.
   - Primary trigger is the **Jira webhook** (`jira:issue_created`, path `jira-issues`). The legacy GitHub receiver in `provisioner/server.js` (`POST /webhook/github`) is retained for backward compatibility.
   - The Jira workflow checks for attachments, downloads them with Basic Auth, re-hosts them on the provisioner, then runs the LLM Gatekeeper.
   - HMAC verification is implemented using the standard GitHub SHA-256 HMAC header `X-Hub-Signature-256`, with a fallback to secret query token if testing via simple curl. (Jira webhook secrets are configured in Jira itself and validated at the Jira/n8n boundary.)
6. **Network & Public Access**:
   - Ephemeral containers run on host ports in range 8100–8199.
   - `VPS_PUBLIC_IP` can be set to the server IP or host IP (or localhost when testing locally).
7. **Jira Front Door (Bouncer upgrade)**:
   - Jira Cloud is the raw intake. n8n receives a Jira webhook (`jira:issue_created`), migrates attachments, and only opens a GitHub issue when TinyFish *reproduces* the bug.
   - **Attachment media host**: We deliberately avoid S3/third-party image hosts. The existing provisioner is extended with `POST /upload`, which stores files under `public/uploads` (random hash filename) and serves them publicly at `/uploads/<hash>`. This reuses the VPS we already run. Storage is temporary (hackathon scope) and the folder is git-ignored.
   - **Attachment download**: Jira attachments live behind authentication. n8n downloads each `attachment.content` URL with `Authorization: Basic base64(JIRA_EMAIL:JIRA_API_TOKEN)`, then re-uploads the bytes to the provisioner.
   - **Attachment handling / simplest option**: Every attachment in the webhook payload is downloaded and re-hosted. The flow is single-file-per-request (`files: 1`, 25 MB cap) so n8n's HTTP node posts one binary per item, which keeps the multipart upload trivial. `image/*` and `video/*` are accepted; `application/octet-stream` is tolerated because Jira sometimes serves attachments with that type. Unsupported types are rejected with HTTP 400.
   - **LLM Gatekeeper**: The schema-matching LLM node (`LLM Gatekeeper`, `@n8n/n8n-nodes-langchain.openAi`) ships **disabled** so the workflow imports and runs without an OpenAI credential. A deterministic `LLM Gatekeeper (Fallback)` Code node produces the identical `{ target_version, reproduction_steps, expected_behavior, pristine_markdown }` payload, embedding the re-hosted media URLs. Enable the LLM node and disable the fallback to use a real model.
   - **Jira description formats**: Jira Cloud v3 descriptions are ADF objects; v2 webhook payloads are plain strings. The parser flattens both to text.
   - **Jira transitions**: Workflow transition IDs are project-specific. `JIRA_TRANSITION_SENT_TO_ENG` and `JIRA_TRANSITION_CANNOT_REPRODUCE` are env-configurable placeholders (defaults `21` and `31`). Discover real IDs via `GET /rest/api/2/issue/<KEY>/transitions`.
   - **Jira REST version**: Uses the v2 REST API (`/rest/api/2/...`) for comments and transitions because it accepts plain-text comment bodies, which is the simplest option.
