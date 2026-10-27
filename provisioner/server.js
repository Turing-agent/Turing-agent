const express = require('express');
const cors = require('cors');
const path = require('path');
const net = require('net');
const { execFile } = require('child_process');
const crypto = require('crypto');
require('dotenv').config();

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
  if (req.path === '/' || req.path === '/events/stream' || req.path === '/health' || req.path === '/dashboard.html') {
    return next();
  }

  const token = req.headers['x-auth-token'];
  if (!token || token !== PROVISIONER_TOKEN) {
    return res.status(401).json({ error: 'unauthorized', message: 'Invalid or missing X-Auth-Token header' });
  }
  next();
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
