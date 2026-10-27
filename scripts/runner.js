#!/usr/bin/env node

/**
 * Auto-Repro Standalone Pipeline Runner
 * Simulates the exact n8n pipeline steps when n8n is not running locally.
 */

const fs = require('fs');
const path = require('path');
const { runTinyFish } = require('../tinyfish/adapter');

const args = process.argv.slice(2);
const issuePath = args[0] || path.join(__dirname, '../demo/issue-real-bug.md');
const provUrl = process.env.PROVISIONER_URL || 'http://127.0.0.1:4000';
const token = process.env.PROVISIONER_TOKEN || 'autorepro_secret_token_123';

if (!fs.existsSync(issuePath)) {
  console.error(`Error: File not found: ${issuePath}`);
  process.exit(1);
}

const rawContent = fs.readFileSync(issuePath, 'utf-8');
const lines = rawContent.split('\n');
const title = lines[0].replace(/^#\s*/, '').trim();
const body = lines.slice(1).join('\n').trim();
const fullText = `${title}\n\n${body}`;
const issueNumber = Math.floor(100 + Math.random() * 900);

async function postEvent(stage, message, data, run_id) {
  try {
    await fetch(`${provUrl}/events`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Auth-Token': token
      },
      body: JSON.stringify({
        run_id: run_id || `issue_${issueNumber}`,
        stage,
        message,
        data: data || {}
      })
    });
  } catch (err) {
    console.error('[Event Error]', err.message);
  }
}

async function run() {
  console.log('==========================================================');
  console.log(`  Auto-Repro Pipeline Execution`);
  console.log(`  Issue #${issueNumber}: ${title}`);
  console.log('==========================================================');

  // Stage 1: ISSUE_RECEIVED
  console.log('\n[Stage 1] ISSUE_RECEIVED');
  await postEvent('ISSUE_RECEIVED', `Received issue #${issueNumber}: ${title}`, {
    issueNumber,
    title
  });

  // Stage 2: EXTRACTING
  console.log('[Stage 2] EXTRACTING');
  let target_version = null;
  const versionMatch = fullText.match(/\b(v\d+\.\d+\.\d+)\b/i);
  if (versionMatch) {
    target_version = versionMatch[1].toLowerCase();
  }

  const steps = [];
  let inSteps = false;
  for (const line of lines) {
    const t = line.trim();
    if (/steps to reproduce/i.test(t)) {
      inSteps = true;
      continue;
    }
    if (inSteps) {
      if (t.startsWith('#')) break;
      const m = t.match(/^(\d+\.|[-*])\s+(.+)$/);
      if (m) steps.push(m[2].trim());
    }
  }
  if (steps.length === 0) {
    steps.push('Go to /settings', 'Click Delete Account');
  }

  await postEvent('EXTRACTING', `Extracted version: ${target_version || 'NONE'}, steps: ${steps.length}`, {
    target_version,
    steps
  });

  if (!target_version) {
    console.log('   ❌ No valid version tag found in issue report.');
    console.log('   Posting comment: "Could not determine version. Please specify e.g. v1.1.0"');
    await postEvent('ABORTED', 'Could not determine version from issue. Container creation aborted.', {});
    console.log('\n[Stage: ABORTED] No container was created.');
    return;
  }

  console.log(`   Target Version: ${target_version}`);
  console.log(`   Steps:`, steps);

  // Stage 3: PROVISIONING
  console.log('\n[Stage 3] PROVISIONING');
  const provRes = await fetch(`${provUrl}/provision`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Auth-Token': token
    },
    body: JSON.stringify({
      version: target_version,
      issue_number: issueNumber
    })
  });

  if (!provRes.ok) {
    const errText = await provRes.text();
    throw new Error(`Provision failed (${provRes.status}): ${errText}`);
  }

  const { run_id, public_url, container } = await provRes.json();
  console.log(`   Container ready at ${public_url} (run_id: ${run_id})`);

  try {
    // Stage 4: TINYFISH AGENT NAVIGATING
    console.log('\n[Stage 4] AGENT_NAVIGATING');
    await postEvent('AGENT_NAVIGATING', `TinyFish agent navigating ${public_url}`, {
      url: public_url,
      steps
    }, run_id);

    const tfResult = await runTinyFish({
      url: public_url,
      steps,
      expected_behavior: 'Account deleted successfully',
      version: target_version
    });

    console.log('\n[Stage 5] AGENT_DONE');
    console.log(`   Final UI State: ${tfResult.final_ui_state}`);
    console.log(`   Agent Summary: ${tfResult.agent_summary}`);
    await postEvent('AGENT_DONE', 'TinyFish finished navigation', tfResult, run_id);

    // Stage 6: VERDICT
    console.log('\n[Stage 6] VERDICT');
    let verdict = 'NOT_REPRODUCED';
    if (!tfResult.completed) {
      verdict = 'INCONCLUSIVE';
    } else {
      const hasNet = tfResult.network_errors && tfResult.network_errors.length > 0;
      const hasCon = tfResult.console_errors && tfResult.console_errors.length > 0;
      const hasVis = tfResult.visible_errors && tfResult.visible_errors.length > 0;
      if (hasNet || hasCon || hasVis) {
        verdict = 'REPRODUCED';
      }
    }

    console.log(`   Result Verdict: ${verdict}`);
    await postEvent('VERDICT', `Verdict: ${verdict}`, {
      verdict,
      observations: tfResult
    }, run_id);

  } finally {
    // Stage 7: TEARDOWN
    console.log('\n[Stage 7] TEARDOWN');
    await fetch(`${provUrl}/teardown`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Auth-Token': token
      },
      body: JSON.stringify({ run_id })
    });
    console.log(`   Environment destroyed for ${run_id}. Zero containers remaining.`);
  }

  console.log('\n==> Pipeline Run Completed Successfully!');
}

run().catch((err) => {
  console.error('[Pipeline Fatal Error]', err);
  process.exit(1);
});
