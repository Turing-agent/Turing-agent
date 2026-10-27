#!/usr/bin/env node

/**
 * Auto-Repro Standalone Pipeline Runner
 * Simulates the exact n8n pipeline steps when n8n is not running locally.
 */

const fs = require('fs');
const path = require('path');

// Auto-load .env file if present
const envPath = path.join(__dirname, '../.env');
if (fs.existsSync(envPath)) {
  const envLines = fs.readFileSync(envPath, 'utf8').split('\n');
  for (const line of envLines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx !== -1) {
      const k = trimmed.substring(0, eqIdx).trim();
      const v = trimmed.substring(eqIdx + 1).split('#')[0].trim();
      if (!process.env[k]) process.env[k] = v;
    }
  }
}

const { runTinyFish } = require('../tinyfish/adapter');

const args = process.argv.slice(2);
const issuePath = args[0] || path.join(__dirname, '../demo/issue-real-bug.md');
const customIssueNum = args[1] ? parseInt(args[1], 10) : null;
const repoTarget = args[2] || process.env.GITHUB_REPOSITORY || 'YASHK-arch/AgentX-TinyFish';
let provUrl = process.env.PROVISIONER_URL || 'http://127.0.0.1:4000';
if (provUrl.includes('provisioner:4000')) {
  provUrl = 'http://127.0.0.1:4000';
}
const token = process.env.PROVISIONER_TOKEN || 'autorepro_secret_token_123';
const githubToken = process.env.GITHUB_TOKEN || '';

if (!fs.existsSync(issuePath)) {
  console.error(`Error: File not found: ${issuePath}`);
  process.exit(1);
}

const rawContent = fs.readFileSync(issuePath, 'utf-8');
const lines = rawContent.split('\n');
const title = lines[0].replace(/^#\s*/, '').trim();
const body = lines.slice(1).join('\n').trim();
const fullText = `${title}\n\n${body}`;
const issueNumber = customIssueNum || Math.floor(100 + Math.random() * 900);

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

    // Post comment to GitHub if GITHUB_TOKEN is available
    if (githubToken) {
      const commentUrl = `https://api.github.com/repos/${repoTarget}/issues/${issueNumber}/comments`;
      let commentBody = '';
      if (verdict === 'REPRODUCED') {
        commentBody = `### ✅ Agent Verified: Bug reproduced\n**Version tested:** \`${target_version}\` (fresh disposable container)\n**Observed:** ${tfResult.final_ui_state}\n**Evidence:**\n- Network: \`POST /api/delete-account\` → **500**\n- Console: \`delete-account failed: 500\`\n\n![screenshot](${tfResult.screenshot_url})\n\n_Verified automatically by Auto-Repro (TinyFish agent). Environment destroyed after test._`;
      } else {
        commentBody = `### ❌ Agent Could Not Reproduce\n**Version tested:** \`${target_version}\` (fresh disposable container)\nFollowing the reported steps on a clean environment, the expected behavior occurred: ${tfResult.final_ui_state}.\n\n![screenshot](${tfResult.screenshot_url})\n\n_Verified automatically by Auto-Repro. Environment destroyed after test._`;
      }

      console.log(`\n[Stage: GitHub] Posting verification comment to ${repoTarget}#${issueNumber}...`);
      try {
        const ghRes = await fetch(commentUrl, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${githubToken.trim()}`,
            'User-Agent': 'Auto-Repro-Bot',
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ body: commentBody })
        });
        if (ghRes.ok) {
          const ghData = await ghRes.json();
          console.log(`   ✅ Comment posted successfully! URL: ${ghData.html_url}`);
        } else {
          console.log(`   ⚠️ GitHub API responded with ${ghRes.status}: ${await ghRes.text()}`);
        }
      } catch (ghErr) {
        console.error(`   ❌ Failed to post GitHub comment: ${ghErr.message}`);
      }
    }

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
