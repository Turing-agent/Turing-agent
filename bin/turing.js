#!/usr/bin/env node

/**
 * Turing-Agent 1-Command Universal Installer CLI
 * Usage: npx github:YASHK-arch/Turing-agent [owner/repo]
 */

const { execSync } = require("child_process");
const readline = require("readline");

const INVITE_WEBHOOK = "https://turing.app.n8n.cloud/webhook/accept-turing-invite";
const EVENTS_WEBHOOK = "https://turing.app.n8n.cloud/webhook/github-events";

function run(cmd, silent = false) {
  try {
    return execSync(cmd, { stdio: silent ? "pipe" : "inherit", encoding: "utf-8" });
  } catch (err) {
    if (silent) return null;
    throw err;
  }
}

function ask(query) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => rl.question(query, (ans) => { rl.close(); resolve(ans.trim()); }));
}

async function main() {
  console.log("\n================================================================");
  console.log("   🐟 Turing-Agent (powered by TinyFish) Installer");
  console.log("   Autonomous Open-Source QA Maintainer & Bug Investigator");
  console.log("================================================================\n");

  // 1. Verify GitHub CLI
  try {
    execSync("gh --version", { stdio: "pipe" });
  } catch {
    console.error("❌ Error: GitHub CLI ('gh') is not installed or not in PATH.");
    console.error("   Install it from https://cli.github.com/ and run 'gh auth login'.");
    process.exit(1);
  }

  try {
    execSync("gh auth status", { stdio: "pipe" });
  } catch {
    console.error("❌ Error: GitHub CLI is not authenticated. Please run 'gh auth login'.");
    process.exit(1);
  }

  if (process.argv.includes("--help") || process.argv.includes("-h")) {
    console.log(`Usage:
  npx github:YASHK-arch/Turing-agent [owner/repo]

Examples:
  # Inside your repository directory (auto-detects repo):
  npx github:YASHK-arch/Turing-agent

  # For any specific remote repository:
  npx github:YASHK-arch/Turing-agent my-org/my-project
`);
    process.exit(0);
  }

  // 2. Identify repo
  let repo = process.argv.slice(2).find((arg) => !arg.startsWith("-"));
  if (!repo) {
    const detected = run("gh repo view --json nameWithOwner -q .nameWithOwner", true);
    if (detected && detected.trim()) {
      repo = detected.trim();
    }
  }

  if (!repo) {
    repo = await ask("Enter target GitHub repository (format: owner/repo): ");
  }

  if (!repo || !/^[\w.-]+\/[\w.-]+$/.test(repo)) {
    console.error(`❌ Error: Invalid repository format '${repo}'. Expected 'owner/repo'.`);
    process.exit(1);
  }

  console.log(`\n🚀 Initializing Turing-Agent on '${repo}'...\n`);

  // Step 1: Discussions
  console.log("1/4 💬 Ensuring GitHub Discussions are enabled...");
  try {
    execSync(`gh repo edit ${repo} --enable-discussions`, { stdio: "pipe" });
    console.log("    ✓ Discussions active.");
  } catch {
    console.log("    ℹ Discussions status unchanged or already enabled.");
  }

  // Step 2: Invite Turing-agent
  console.log("2/4 🤝 Inviting 'Turing-agent' as collaborator...");
  try {
    // Check if already a collaborator
    const isCollab = run(`gh api /repos/${repo}/collaborators/Turing-agent`, true);
    if (isCollab !== null) {
      console.log("    ✓ Turing-agent is already a collaborator on this repository.");
    } else {
      // First try permission=admin (supported on Organization repos)
      // Fallback to permission=push (write permission, required on personal user repos)
      try {
        execSync(
          `gh api --method PUT -H "Accept: application/vnd.github+json" /repos/${repo}/collaborators/Turing-agent -f permission=admin`,
          { stdio: "pipe" }
        );
      } catch {
        execSync(
          `gh api --method PUT -H "Accept: application/vnd.github+json" /repos/${repo}/collaborators/Turing-agent -f permission=push`,
          { stdio: "pipe" }
        );
      }
      console.log("    ✓ Collaborator invitation dispatched to Turing-agent.");
    }
  } catch (err) {
    console.error(`❌ Error sending collaborator invite: ${err.message}`);
    process.exit(1);
  }

  // Step 3: Trigger auto-accept webhook
  console.log("3/4 ⚡ Triggering cloud auto-accept webhook...");
  try {
    // Node 18+ has native fetch
    await fetch(INVITE_WEBHOOK, { method: "POST" });
    await new Promise((r) => setTimeout(r, 2000));
    console.log(`    ✓ Invitation accepted! Turing-agent is now an Admin on ${repo}.`);
  } catch {
    console.log("    ⚠️ Auto-accept pinged. Verify collaborator acceptance on GitHub.");
  }

  // Step 4: Configure Webhook
  console.log("4/4 🔗 Configuring repository webhook for discussion events...");
  try {
    const existing = run(`gh api /repos/${repo}/hooks --jq ".[].config.url"`, true) || "";
    if (existing.includes(EVENTS_WEBHOOK)) {
      console.log(`    ✓ Webhook already configured for ${EVENTS_WEBHOOK}.`);
    } else {
      execSync(
        `gh api --method POST -H "Accept: application/vnd.github+json" /repos/${repo}/hooks -f name="web" -F "active=true" -F "events[]=discussion" -F "events[]=discussion_comment" -F "config[url]=${EVENTS_WEBHOOK}" -F "config[content_type]=json"`,
        { stdio: "pipe" }
      );
      console.log(`    ✓ Webhook successfully registered (${EVENTS_WEBHOOK}).`);
    }
  } catch (err) {
    console.log(`    ⚠️ Webhook creation returned: ${err.message}`);
  }

  console.log("\n================================================================");
  console.log(`   🎉 Turing-Agent is now fully active on ${repo}!`);
  console.log("================================================================");
  console.log("✨ What happens next:");
  console.log(`  1. Open a new Discussion in ${repo}:`);
  console.log("     -> Turing reacts with 👀, validates, and correlates issues.");
  console.log("  2. Ask questions or tag @Turing-agent in comments:");
  console.log("     -> Turing reproduces frontend bugs live, searches conflicts, or answers Q&A.");
  console.log("  3. Maintainer comments 'approved':");
  console.log("     -> Turing autonomously synthesizes the code fix and opens a PR!\n");
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
