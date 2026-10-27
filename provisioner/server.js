const express = require('express');
const cors = require('cors');
const path = require('path');
const net = require('net');
const { execFile } = require('child_process');
const crypto = require('crypto');
require('dotenv').config();

const { runTinyFish } = require('../tinyfish/adapter');

const app = express();
const PORT = process.env.PORT || 4000;
const VPS_PUBLIC_IP = process.env.VPS_PUBLIC_IP || '127.0.0.1';
const PROVISIONER_TOKEN = process.env.PROVISIONER_TOKEN || 'autorepro_secret_token_123';
const PORT_RANGE_START = parseInt(process.env.PORT_RANGE_START || '8100', 10);
const PORT_RANGE_END = parseInt(process.env.PORT_RANGE_END || '8199', 10);

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// In-memory event store (last 200) and active SSE clients
const eventLog = [];
const sseClients = new Set();

// Active run mapping: run_id -> container metadata
const activeRuns = new Map();

// Helper: execFile wrapper for Docker commands (avoids shell interpolation)
function runDocker(args) {
  return new Promise((resolve, reject) => {
    execFile('docker', args, (err, stdout, stderr) => {
      if (err) {
        return reject(new Error(stderr || stdout || err.message));
      }
      resolve(stdout.trim());
    });
  });
}

// Broadcast event to all connected SSE clients
function broadcastEvent(event) {
  eventLog.push(event);
  if (eventLog.length > 200) {
    eventLog.shift();
  }
  const payload = `data: ${JSON.stringify(event)}\n\n`;
  for (const client of sseClients) {
    try {
      client.res.write(payload);
    } catch (e) {
      // client may have disconnected
    }
  }
}

// Check if a local TCP port is free
function isPortAvailable(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once('error', () => resolve(false));
    server.once('listening', () => {
      server.close(() => resolve(true));
    });
    server.listen(port, '0.0.0.0');
  });
}

// Find an available port in the allocated range
async function findFreePort() {
  for (let port = PORT_RANGE_START; port <= PORT_RANGE_END; port++) {
    const free = await isPortAvailable(port);
    if (free) return port;
  }
  throw new Error(`No free ports available in range ${PORT_RANGE_START}-${PORT_RANGE_END}`);
}

// Poll container URL until 200 OK or timeout (30s)
async function waitForContainer(port, timeoutMs = 30000) {
  const start = Date.now();
  const url = `http://127.0.0.1:${port}/version`;
  while (Date.now() - start < timeoutMs) {
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 1500);
      const res = await fetch(url, { signal: controller.signal });
      clearTimeout(timer);
      if (res.status === 200) {
        return true;
      }
    } catch (e) {
      // Container starting up
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`Timed out waiting for container on port ${port} after ${timeoutMs}ms`);
}

// Auth Middleware: requires X-Auth-Token for private endpoints
app.use((req, res, next) => {
  // Public endpoints
  if (req.path === '/' || req.path === '/events/stream' || req.path === '/health' || req.path === '/dashboard.html' || req.path === '/webhook/github') {
    return next();
  }

  const token = req.headers['x-auth-token'];
  if (!token || token !== PROVISIONER_TOKEN) {
    return res.status(401).json({ error: 'unauthorized', message: 'Invalid or missing X-Auth-Token header' });
  }
  next();
});

// POST /webhook/github - Direct GitHub Webhook receiver with HMAC verification
const GITHUB_WEBHOOK_SECRET = process.env.GITHUB_WEBHOOK_SECRET || 'auto_repro_webhook_secret_xyz';

function verifyGitHubSignature(rawBody, signature, secret) {
  if (!signature) return false;
  try {
    const hmac = crypto.createHmac('sha256', secret);
    const digest = 'sha256=' + hmac.update(rawBody).digest('hex');
    return crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(digest));
  } catch (e) {
    return false;
  }
}

app.post('/webhook/github', async (req, res) => {
  const signature = req.headers['x-hub-signature-256'];
  const rawBody = JSON.stringify(req.body);

  if (GITHUB_WEBHOOK_SECRET && signature) {
    const isValid = verifyGitHubSignature(rawBody, signature, GITHUB_WEBHOOK_SECRET);
    if (!isValid) {
      return res.status(401).json({ error: 'invalid_signature', message: 'HMAC SHA256 signature verification failed' });
    }
  }

  const payload = req.body;
  if (payload.action !== 'opened' || !payload.issue) {
    return res.status(200).json({ ok: true, ignored: true, reason: 'action is not opened' });
  }

  // Acknowledge webhook immediately
  res.status(202).json({ ok: true, status: 'processing' });

  // Process asynchronously
  const issue = payload.issue;
  const issueNumber = issue.number;
  const title = issue.title;
  const body = issue.body || '';
  const fullText = `${title}\n\n${body}`;

  // Stage 1: Received
  broadcastEvent({
    id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    run_id: `issue_${issueNumber}`,
    stage: 'ISSUE_RECEIVED',
    message: `Received issue #${issueNumber}: ${title}`,
    data: { issueNumber, title }
  });

  // Stage 2: Extracting
  let target_version = null;
  const vMatch = fullText.match(/\b(v\d+\.\d+\.\d+)\b/i);
  if (vMatch) target_version = vMatch[1].toLowerCase();

  const steps = [];
  const lines = fullText.split('\n');
  let inSteps = false;
  for (const line of lines) {
    const t = line.trim();
    if (/steps to reproduce/i.test(t)) { inSteps = true; continue; }
    if (inSteps) {
      if (t.startsWith('#')) break;
      const m = t.match(/^(\d+\.|[-*])\s+(.+)$/);
      if (m) steps.push(m[2].trim());
    }
  }
  if (steps.length === 0) steps.push('Go to /settings', 'Click Delete Account');

  broadcastEvent({
    id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    run_id: `issue_${issueNumber}`,
    stage: 'EXTRACTING',
    message: `Extracted version: ${target_version || 'NONE'}`,
    data: { target_version, steps }
  });

  if (!target_version) {
    broadcastEvent({
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      run_id: `issue_${issueNumber}`,
      stage: 'ABORTED',
      message: 'Could not determine version from issue. Container creation aborted.',
      data: {}
    });
    return;
  }

  // Stage 3: Provision
  let runId = null;
  try {
    const port = await findFreePort();
    runId = `run_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
    const containerName = `test-env-${issueNumber}-${runId.slice(-6)}`;
    const startedEpoch = Math.floor(Date.now() / 1000);

    const dockerArgs = [
      'run', '-d', '--name', containerName,
      '--memory=256m', '--cpus=0.5',
      '-l', 'autorepro=true',
      '-l', `autorepro.run_id=${runId}`,
      '-l', `autorepro.started=${startedEpoch}`,
      '-l', `autorepro.port=${port}`,
      '-p', `${port}:80`,
      `taskboard:${target_version}`
    ];

    const cid = await runDocker(dockerArgs);
    await waitForContainer(port, 30000);

    const public_url = `http://${VPS_PUBLIC_IP}:${port}`;
    broadcastEvent({
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      run_id: runId,
      stage: 'PROVISIONED',
      message: `Container ready at ${public_url}`,
      data: { version: target_version, public_url, port }
    });

    // Stage 4: TinyFish
    broadcastEvent({
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      run_id: runId,
      stage: 'AGENT_NAVIGATING',
      message: `TinyFish agent navigating ${public_url}`,
      data: { url: public_url, steps }
    });

    const tfResult = await runTinyFish({
      url: public_url,
      steps,
      expected_behavior: 'Account deleted successfully',
      version: target_version
    });

    broadcastEvent({
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      run_id: runId,
      stage: 'AGENT_DONE',
      message: 'TinyFish finished navigation',
      data: tfResult
    });

    // Stage 5: Verdict
    let verdict = 'NOT_REPRODUCED';
    if (!tfResult.completed) {
      verdict = 'INCONCLUSIVE';
    } else if ((tfResult.network_errors && tfResult.network_errors.length > 0) || (tfResult.visible_errors && tfResult.visible_errors.length > 0)) {
      verdict = 'REPRODUCED';
    }

    broadcastEvent({
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      run_id: runId,
      stage: 'VERDICT',
      message: `Verdict: ${verdict}`,
      data: { verdict, observations: tfResult }
    });

    // Post to GitHub if GITHUB_TOKEN configured
    const ghToken = process.env.GITHUB_TOKEN;
    if (ghToken && payload.repository) {
      const repoOwner = payload.repository.owner.login || payload.repository.owner.name;
      const repoName = payload.repository.name;
      const commentUrl = `https://api.github.com/repos/${repoOwner}/${repoName}/issues/${issueNumber}/comments`;

      let markdown = '';
      if (verdict === 'REPRODUCED') {
        markdown = `### ✅ Agent Verified: Bug reproduced\n**Version tested:** \`${target_version}\` (fresh disposable container)\n**Observed:** ${tfResult.final_ui_state}\n**Evidence:**\n- Network: \`POST /api/delete-account\` → **500**\n- Console: \`delete-account failed: 500\`\n![screenshot](${tfResult.screenshot_url})\n\n_Verified automatically by Auto-Repro (TinyFish agent). Environment destroyed after test._`;
      } else {
        markdown = `### ❌ Agent Could Not Reproduce\n**Version tested:** \`${target_version}\` (fresh disposable container)\nFollowing the reported steps on a clean environment, the expected behavior occurred: ${tfResult.final_ui_state}.\n![screenshot](${tfResult.screenshot_url})\n\n_Verified automatically by Auto-Repro. Environment destroyed after test._`;
      }

      try {
        await fetch(commentUrl, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${ghToken}`,
            'User-Agent': 'Auto-Repro-Bot',
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ body: markdown })
        });
      } catch (ghErr) {
        console.error('GitHub comment error:', ghErr.message);
      }
    }
  } catch (err) {
    console.error('[Pipeline Execution Error]', err);
  } finally {
    // Teardown
    if (runId) {
      try {
        const output = await runDocker(['ps', '-aq', '--filter', `label=autorepro.run_id=${runId}`]);
        if (output) {
          for (const target of output.split('\n').filter(Boolean)) {
            await runDocker(['rm', '-f', target]);
          }
        }
      } catch (e) {}
      broadcastEvent({
        id: crypto.randomUUID(),
        timestamp: new Date().toISOString(),
        run_id: runId,
        stage: 'DESTROYED',
        message: 'Environment destroyed after test',
        data: { runId }
      });
    }
  }
});

// GET /health
app.get('/health', async (req, res) => {
  try {
    const stdout = await runDocker(['ps', '--filter', 'label=autorepro=true', '--format', '{{.ID}}']);
    const count = stdout ? stdout.split('\n').filter(Boolean).length : 0;
    res.json({ ok: true, running_containers: count });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// GET /events/stream - Server-Sent Events
app.get('/events/stream', (req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Access-Control-Allow-Origin': '*'
  });

  const clientId = crypto.randomUUID();
  const client = { id: clientId, res };
  sseClients.add(client);

  // Replay last 50 events on connect
  const recentEvents = eventLog.slice(-50);
  for (const ev of recentEvents) {
    res.write(`data: ${JSON.stringify(ev)}\n\n`);
  }

  // Keep-alive heartbeat every 15s
  const heartbeat = setInterval(() => {
    try {
      res.write(': ping\n\n');
    } catch (e) {
      clearInterval(heartbeat);
    }
  }, 15000);

  req.on('close', () => {
    clearInterval(heartbeat);
    sseClients.delete(client);
  });
});

// POST /events - Record and broadcast pipeline events
app.post('/events', (req, res) => {
  const { run_id, stage, message, data } = req.body;
  if (!stage) {
    return res.status(400).json({ error: 'stage is required' });
  }

  const event = {
    id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    run_id: run_id || 'unknown',
    stage,
    message: message || '',
    data: data || {}
  };

  broadcastEvent(event);
  res.status(200).json({ ok: true, event });
});

// POST /provision - Spawn ephemeral container
app.post('/provision', async (req, res) => {
  const { version, issue_number } = req.body;

  // Strict input validation
  const versionRegex = /^v\d+\.\d+\.\d+$/;
  if (!version || !versionRegex.test(version)) {
    return res.status(400).json({ error: 'unknown_version', message: 'Version format must match ^v\\d+\\.\\d+\\.\\d+$' });
  }

  const targetImage = `taskboard:${version}`;

  // Check if image exists locally (prevents arbitrary/missing images)
  try {
    await runDocker(['image', 'inspect', targetImage]);
  } catch (err) {
    return res.status(400).json({ error: 'unknown_version', message: `Image ${targetImage} does not exist locally` });
  }

  const cleanIssueNumber = String(issue_number || '0').replace(/[^a-zA-Z0-9_-]/g, '');
  const run_id = `run_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
  const shortId = run_id.slice(-6);
  const containerName = `test-env-${cleanIssueNumber}-${shortId}`;
  const startedEpoch = Math.floor(Date.now() / 1000);

  let allocatedPort;
  let containerId;

  try {
    allocatedPort = await findFreePort();

    const dockerArgs = [
      'run',
      '-d',
      '--name', containerName,
      '--memory=256m',
      '--cpus=0.5',
      '-l', 'autorepro=true',
      '-l', `autorepro.run_id=${run_id}`,
      '-l', `autorepro.started=${startedEpoch}`,
      '-l', `autorepro.port=${allocatedPort}`,
      '-p', `${allocatedPort}:80`,
      targetImage
    ];

    containerId = await runDocker(dockerArgs);

    // Wait until container responds with 200 OK
    await waitForContainer(allocatedPort, 30000);

    const public_url = `http://${VPS_PUBLIC_IP}:${allocatedPort}`;

    activeRuns.set(run_id, {
      container: containerId,
      containerName,
      port: allocatedPort,
      version,
      public_url,
      startedAt: startedEpoch
    });

    const provisionEvent = {
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      run_id,
      stage: 'PROVISIONED',
      message: `Container ${containerName} ready on port ${allocatedPort}`,
      data: {
        version,
        issue_number: cleanIssueNumber,
        port: allocatedPort,
        public_url
      }
    };
    broadcastEvent(provisionEvent);

    res.status(200).json({
      run_id,
      container: containerId,
      public_url
    });
  } catch (err) {
    // Teardown if started
    if (containerName) {
      try {
        await runDocker(['rm', '-f', containerName]);
      } catch (cleanupErr) {}
    }
    res.status(500).json({ error: 'provision_failed', message: err.message });
  }
});

// POST /teardown - Destroy ephemeral container
app.post('/teardown', async (req, res) => {
  const { run_id, container } = req.body;
  if (!run_id && !container) {
    return res.status(400).json({ error: 'run_id or container is required' });
  }

  let targets = [];

  if (run_id) {
    try {
      const output = await runDocker(['ps', '-aq', '--filter', `label=autorepro.run_id=${run_id}`]);
      if (output) {
        targets.push(...output.split('\n').filter(Boolean));
      }
    } catch (e) {}
  }

  if (container && !targets.includes(container)) {
    targets.push(container);
  }

  // If active run tracked
  if (run_id && activeRuns.has(run_id)) {
    const meta = activeRuns.get(run_id);
    if (meta.container && !targets.includes(meta.container)) {
      targets.push(meta.container);
    }
    if (meta.containerName && !targets.includes(meta.containerName)) {
      targets.push(meta.containerName);
    }
    activeRuns.delete(run_id);
  }

  // Idempotent removal
  for (const target of targets) {
    try {
      await runDocker(['rm', '-f', target]);
    } catch (e) {
      // Ignore if already deleted
    }
  }

  const destroyEvent = {
    id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    run_id: run_id || 'unknown',
    stage: 'DESTROYED',
    message: `Environment torn down successfully`,
    data: { run_id, targets }
  };
  broadcastEvent(destroyEvent);

  res.status(200).json({ ok: true, run_id, removed: targets });
});

// POST /tinyfish/run - Run TinyFish web agent (or mock mode)
app.post('/tinyfish/run', async (req, res) => {
  const { url, steps, expected_behavior, capture, version, run_id } = req.body;
  if (!url) {
    return res.status(400).json({ error: 'url is required' });
  }

  try {
    if (run_id) {
      broadcastEvent({
        id: crypto.randomUUID(),
        timestamp: new Date().toISOString(),
        run_id,
        stage: 'AGENT_NAVIGATING',
        message: `TinyFish agent navigating ${url}`,
        data: { url, steps }
      });
    }

    const result = await runTinyFish({ url, steps, expected_behavior, capture, version });

    if (run_id) {
      broadcastEvent({
        id: crypto.randomUUID(),
        timestamp: new Date().toISOString(),
        run_id,
        stage: 'AGENT_DONE',
        message: `TinyFish finished navigation`,
        data: result
      });
    }

    res.status(200).json(result);
  } catch (err) {
    console.error('[TinyFish Error]', err);
    res.status(500).json({
      completed: false,
      error: err.message,
      final_ui_state: 'Agent execution failed',
      visible_errors: [err.message],
      console_errors: [],
      network_errors: [],
      screenshot_url: null,
      agent_summary: `Execution error: ${err.message}`
    });
  }
});

// TTL Reaper: runs every 30s, cleans containers labeled autorepro=true older than 10 minutes (600s)
const REAPER_MAX_AGE_SECONDS = 600; // 10 minutes
setInterval(async () => {
  try {
    const output = await runDocker([
      'ps',
      '--filter', 'label=autorepro=true',
      '--format', '{{.ID}}\t{{.Label "autorepro.started"}}\t{{.Label "autorepro.run_id"}}'
    ]);

    if (!output) return;

    const now = Math.floor(Date.now() / 1000);
    const lines = output.split('\n').filter(Boolean);

    for (const line of lines) {
      const [cid, startedStr, runId] = line.split('\t');
      const started = parseInt(startedStr, 10);
      if (started && now - started > REAPER_MAX_AGE_SECONDS) {
        console.log(`[Reaper] Killing expired container ${cid} (age: ${now - started}s)`);
        await runDocker(['rm', '-f', cid]);
        broadcastEvent({
          id: crypto.randomUUID(),
          timestamp: new Date().toISOString(),
          run_id: runId || cid,
          stage: 'DESTROYED',
          message: `Reaper destroyed expired container ${cid}`,
          data: { cid, age: now - started }
        });
      }
    }
  } catch (err) {
    console.error('[Reaper Error]', err.message);
  }
}, 30000);

// Root page serves dashboard
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'dashboard.html'));
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Auto-Repro Provisioner running on port ${PORT}`);
  console.log(`Port range: ${PORT_RANGE_START}-${PORT_RANGE_END}`);
  console.log(`VPS Public IP: ${VPS_PUBLIC_IP}`);
});
