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
   - Webhook accepts GitHub issue events; checks `action === "opened"`.
   - HMAC verification is implemented using the standard GitHub SHA-256 HMAC header `X-Hub-Signature-256`, with a fallback to secret query token if testing via simple curl.
6. **Network & Public Access**:
   - Ephemeral containers run on host ports in range 8100–8199.
   - `VPS_PUBLIC_IP` can be set to the server IP or host IP (or localhost when testing locally).
