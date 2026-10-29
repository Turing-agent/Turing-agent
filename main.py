"""
TinyFish / Turing-agent - Autonomous GitHub QA Agent Backend
Phase 2 Investigation Architecture & Phase 3 Response Orchestrator

Run the server locally on port 8000 using:
    uvicorn main:app --reload --port 8000
"""

import os
import sys
import time
import requests
import logging
import traceback
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load local environment variables if available
load_dotenv()

# Import Phase 2 Agentic Workflow Modules
from vision_module import (
    analyze_video_and_discussion,
    BugReproductionPlan
)
from docker_provisioner import (
    provision_docker_sandbox,
    SandboxEnvironment
)
from agent_runner import (
    hunt_and_capture,
    AgentHuntResult
)
from analyzer import (
    analyze_root_cause,
    RootCauseAnalysisResult
)
from tinyfish_correlator import (
    generate_turing_validation,
    scrape_repository_issues_and_discussions,
    generate_tinyfish_correlation_report
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("tinyfish.main")

app = FastAPI(
    title="TinyFish Autonomous QA Agent",
    description="Webhook receiver and autonomous investigation orchestrator for n8n pipeline",
    version="2.0.0"
)


class RunTinyFishPayload(BaseModel):
    discussion_title: Optional[str] = Field(None, description="GitHub Discussion Title")
    title: Optional[str] = Field(None, description="Alternative title key from n8n")
    discussion_body: Optional[str] = Field(None, description="GitHub Discussion Body description")
    body: Optional[str] = Field(None, description="Alternative body key from n8n")
    video_url: Optional[str] = Field(None, description="URL or filepath to video screen recording of the bug")
    media_urls: Optional[List[str]] = Field(default_factory=list, description="Array of media links from n8n")
    live_url: Optional[str] = Field(None, description="Live deployment URL provided by repo owner")
    discussion_url: Optional[str] = Field(None, description="GitHub discussion URL")
    discussion_number: Optional[Any] = Field(None, description="GitHub discussion number")
    repository: Optional[str] = Field(None, description="GitHub repository full name")
    author: Optional[str] = Field(None, description="Author login")

    def get_title(self) -> str:
        return self.discussion_title or self.title or "Reported Bug Investigation"

    def get_body(self) -> str:
        return self.discussion_body or self.body or ""

    def get_video_url(self) -> Optional[str]:
        if self.video_url:
            return self.video_url
        if self.media_urls:
            # Pick first video-like or image media
            for u in self.media_urls:
                if any(ext in u.lower() for ext in [".mp4", ".mov", ".webm", ".mkv", "user-attachments"]):
                    return u
            return self.media_urls[0]
        return None




def generate_markdown_report(
    plan: BugReproductionPlan,
    sandbox: SandboxEnvironment,
    hunt_result: AgentHuntResult,
    root_cause: RootCauseAnalysisResult
) -> str:
    """Compile the complete multi-phase investigation evidence into a rich GitHub-compatible Markdown report."""
    verdict_badge = (
        "## 🎯 TinyFish Investigation Report: **`BUG REPRODUCED & VERIFIED`** ✅"
        if hunt_result.reproduced
        else "## 🎯 TinyFish Investigation Report: **`UNABLE TO REPRODUCE`** ⚠️"
    )

    steps_md = "\n".join([f"{idx + 1}. {step}" for idx, step in enumerate(plan.steps)])
    visual_cues_md = "\n".join([f"- {cue}" for cue in plan.visual_cues_found]) or "- Direct text extraction from report"

    console_logs_md = (
        "```log\n" + "\n".join(hunt_result.console_logs) + "\n```"
        if hunt_result.console_logs
        else "*No console errors intercepted.*"
    )

    if hunt_result.network_logs:
        network_logs_md = "| Method | Endpoint / URL | Status |\n|---|---|---|\n"
        for net in hunt_result.network_logs:
            network_logs_md += f"| `{net.get('method', 'GET')}` | `{net.get('url', '-')}` | **{net.get('status', '-')}** |\n"
    else:
        network_logs_md = "*No failed network requests intercepted.*"

    screencast_section = ""
    if hunt_result.screencast_url or hunt_result.screencast_path:
        sc_link = hunt_result.screencast_url or f"file:///{hunt_result.screencast_path.replace(os.sep, '/')}"
        screencast_section = (
            f"### 📹 Screencast & Visual Evidence\n"
            f"- **Reproduction Recording**: [{os.path.basename(hunt_result.screencast_path or 'screencast.mp4')}]({sc_link})\n"
            f"- **Final UI State**: `{hunt_result.final_ui_state}`\n"
        )
        if hunt_result.screenshots:
            screencast_section += f"![Browser State]({hunt_result.screenshots[0]})\n"

    report = f"""{verdict_badge}

> **Autonomous Agent**: TinyFish / Turing-agent  
> **Investigation Target**: `{plan.discussion_title}`  
> **Target Repo**: `https://github.com/YASHK-arch/RepoOwl-extension.git`  
> **Verdict Confidence**: **{int(root_cause.confidence * 100)}%**

---

### 📋 Executive Summary
{plan.summary}

- **Observed Symptom**: `{plan.observed_bug}`
- **Expected Application Behavior**: `{plan.expected_behavior}`

---

### 👁️ Phase 2.1: Multimodal Video & Discussion Intake
- **Video Source**: {'`' + str(plan.has_video) + '` (' + str(plan.frames_analyzed) + ' keyframes extracted via OpenCV at 1 fps)' if plan.has_video else '*No video attachment provided; analyzed discussion context directly.*'}
- **Extracted Visual Cues**:
{visual_cues_md}

#### Generated Reproduction Steps:
{steps_md}

---

### 🐳 Phase 2.2: Ephemeral Sandbox Environment
- **Provisioner Mode**: `{sandbox.mode.upper()}`
- **Sandbox Container/Instance ID**: `{sandbox.container_id or 'local-sandbox'}`
- **Allocated Port**: `{sandbox.port}`
- **Sandbox Provisioning Log**:
```text
{chr(10).join(sandbox.provisioning_logs)}
```

---

### 🕵️ Phase 2.3: Autonomous Agent Hunt & Visual Capture
{screencast_section}

#### Browser Console Traces
{console_logs_md}

#### Intercepted Network Failures (Status >= 400)
{network_logs_md}

#### Autonomous Agent Investigation Notes
> {hunt_result.agent_summary}

---

### 🔬 Phase 2.4: Codebase Scrape & Root Cause Analysis
TinyFish traced the runtime stack trace and network logs against the cloned repository AST and source logic:

- **Offending File**: [`{root_cause.file_path}`](file:///{root_cause.file_path}) (Lines {root_cause.line_start}–{root_cause.line_end})
- **Technical Root Cause**:
  {root_cause.root_cause_explanation}

#### Offending Code Block:
```javascript
{root_cause.offending_code}
```

---

### 🛠️ Recommended Pull Request Patch
{root_cause.recommended_patch}

---
*Generated autonomously by **TinyFish QA Agent** for n8n GitHub Workflow.*
"""
    return report


@app.get("/")
def read_root():
    """Health check endpoint."""
    return {
        "agent": "TinyFish (Turing-agent)",
        "status": "healthy",
        "version": "2.0.0",
        "workflow": "Phase 2 Autonomous Investigation Pipeline"
    }


@app.api_route("/accept-turing-invite", methods=["GET", "POST"])
def accept_turing_invite():
    """
    Webhook endpoint to instantly accept pending GitHub repository invitations for Turing-agent.
    Triggered by `invite_turing` terminal command or n8n webhook.
    """
    import requests
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        logger.warning("[Invite] GITHUB_TOKEN not configured in environment.")
        return {
            "status": "warning",
            "message": "GITHUB_TOKEN not configured. Please set GITHUB_TOKEN in .env to enable auto-accept."
        }

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    try:
        # Step 1: Fetch pending invitations
        res = requests.get("https://api.github.com/user/repository_invitations", headers=headers, timeout=10)
        res.raise_for_status()
        invitations = res.json()

        if not invitations:
            logger.info("[Invite] Checked pending invitations: 0 pending.")
            return {
                "status": "success",
                "accepted_count": 0,
                "message": "Turing-agent has no pending repository invitations."
            }

        accepted_repos = []
        for inv in invitations:
            inv_id = inv.get("id")
            repo_info = inv.get("repository", {})
            repo_name = repo_info.get("full_name", f"Invitation #{inv_id}")
            logger.info(f"[Invite] Accepting invitation for {repo_name} (ID: {inv_id})...")

            # Step 2: Accept invitation
            patch_res = requests.patch(
                f"https://api.github.com/user/repository_invitations/{inv_id}",
                headers=headers,
                timeout=10
            )
            if patch_res.status_code in (204, 200):
                accepted_repos.append(repo_name)
                logger.info(f"[Invite] Successfully accepted invitation for {repo_name}!")
            else:
                logger.warning(f"[Invite] Failed to accept {repo_name}: {patch_res.status_code} {patch_res.text}")

        return {
            "status": "success",
            "accepted_count": len(accepted_repos),
            "repositories": accepted_repos,
            "message": f"Turing-agent accepted {len(accepted_repos)} collaborator invitation(s) successfully!"
        }
    except Exception as e:
        logger.error(f"[Invite] Error accepting GitHub invitations: {e}")
        return {
            "status": "error",
            "message": str(e)
        }



@app.post("/run-tinyfish")
async def run_tinyfish(payload: RunTinyFishPayload):
    """
    Main webhook receiver endpoint for n8n orchestration pipeline.
    Orchestrates Phase 2.1 -> Phase 2.2 -> Phase 2.3 -> Phase 2.4 -> Markdown Report.
    """
    logger.info("=" * 60)
    logger.info(f"Incoming /run-tinyfish request for: {payload.discussion_title}")
    logger.info(f"Video URL: {payload.video_url or 'None'}")
    logger.info("=" * 60)

    # Print incoming payload to console for n8n debugging verification
    print("--- [n8n Webhook Payload Received] ---")
    print(payload.model_dump_json(indent=2))
    print("--------------------------------------")

    sandbox: Optional[SandboxEnvironment] = None
    try:
        # Phase 2.1: Multimodal Video Analysis
        title = payload.get_title()
        body = payload.get_body()
        video = payload.get_video_url()
        logger.info(f"[Phase 2.1] Analyzing video and context for: {title}")
        plan = analyze_video_and_discussion(
            video_url=video,
            discussion_title=title,
            discussion_body=body
        )
        logger.info(f"[Phase 2.1] Complete. Formulated {len(plan.steps)} reproduction steps.")

        # Phase 2.2: Ephemeral Docker Sandbox Provisioning
        logger.info("[Phase 2.2] Provisioning sandbox environment & codebase...")
        sandbox = provision_docker_sandbox()
        if payload.live_url:
            sandbox.app_url = payload.live_url.rstrip("/")
            sandbox.mode = "live_deployment"
            sandbox.add_log(f"Configured live deployment target: {sandbox.app_url}")
        logger.info(f"[Phase 2.2] Complete. Sandbox running at {sandbox.app_url} in {sandbox.mode} mode.")

        # Phase 2.3: Autonomous Hunt & Visual Capture
        logger.info("[Phase 2.3] Starting autonomous hunt and browser interaction...")
        hunt_result = hunt_and_capture(sandbox=sandbox, plan=plan)
        logger.info(f"[Phase 2.3] Complete. Bug reproduced: {hunt_result.reproduced}.")

        # Phase 2.4: Repository Scrape & Root Cause Analysis
        logger.info("[Phase 2.4] Scraping repository logic and correlating errors...")
        root_cause = analyze_root_cause(
            repo_path=sandbox.repo_path,
            plan=plan,
            hunt_result=hunt_result
        )
        logger.info(f"[Phase 2.4] Complete. Root cause located in {root_cause.file_path}:{root_cause.line_start}.")

        # Phase 3: Compile Markdown Bug Verification Report
        logger.info("[Phase 3] Compiling Markdown Bug Verification Report...")
        report_markdown = generate_markdown_report(
            plan=plan,
            sandbox=sandbox,
            hunt_result=hunt_result,
            root_cause=root_cause
        )

        logger.info("[Phase 3] Investigation finished successfully. Returning report to n8n.")
        return {
            "status": "success",
            "report": report_markdown
        }

    except Exception as e:
        logger.error(f"Error during TinyFish investigation workflow: {e}", exc_info=True)
        tb_str = traceback.format_exc()

        # Build resilient diagnostic error report so n8n always gets actionable output
        error_report = f"""## ⚠️ TinyFish Autonomous QA Agent Notice
**Status**: Investigation encountered an operational exception during execution.

### Exception Diagnostics:
```text
{str(e)}
```

### Stack Trace:
```text
{tb_str}
```

*TinyFish will retry when container dependencies or media assets become accessible.*
"""
        return {
            "status": "success",
            "report": error_report
        }

    finally:
        # Guarantee teardown of ephemeral container and temp workspace
        if sandbox:
            try:
                sandbox.teardown()
            except Exception as teardown_err:
                logger.warning(f"Error during sandbox teardown: {teardown_err}")


# ---------------------------------------------------------------------------
# /resolve-issue  — AI-powered code resolution endpoint
# ---------------------------------------------------------------------------

class ResolveIssuePayload(BaseModel):
    """Payload from n8n to resolve a GitHub issue with real code changes."""
    issue_title: str = Field(..., description="GitHub issue title")
    issue_body: str = Field(..., description="GitHub issue body (full description)")
    issue_number: int = Field(..., description="GitHub issue number")
    repo_full_name: str = Field(..., description="owner/repo, e.g. YASHK-arch/RepoOwl-extension")
    base_tree_sha: str = Field(..., description="SHA of the base git tree to build changes on")
    base_commit_sha: Optional[str] = Field(None, description="SHA of the base commit to parent the new commit")
    author: Optional[str] = Field("contributor", description="Author username for co-attribution")
    branch_name: Optional[str] = Field(None, description="Feature branch name (defaults to issue-{number})")
    discussion_url: Optional[str] = Field(None, description="Link back to the original discussion")
    issue_url: Optional[str] = Field(None, description="Link to the created issue")
    progress_comment_id: Optional[str] = Field(None, description="GraphQL node ID of progress comment in discussion")
    live_url: Optional[str] = Field(None, description="Optional live website or deployment URL to inspect with TinyFish")


class FileChange(BaseModel):
    path: str
    content: str


class ResolveIssueResult(BaseModel):
    changes: list[FileChange]
    commit_message: str
    summary: str


import re
import base64


def _update_discussion_progress(token: str, comment_id: Optional[str], body: str):
    """Updates a GitHub Discussion comment in-place using GraphQL mutation."""
    if not comment_id or not token:
        return
    query = """
    mutation($input: UpdateDiscussionCommentInput!) {
      updateDiscussionComment(input: $input) {
        comment { id updatedAt }
      }
    }
    """
    try:
        requests.post(
            "https://api.github.com/graphql",
            json={"query": query, "variables": {"input": {"commentId": comment_id, "body": body}}},
            headers={"Authorization": f"Bearer {token}", "User-Agent": "Turing-agent"},
            timeout=10,
        )
    except Exception as e:
        logger.warning(f"[Progress] Failed to update discussion comment {comment_id}: {e}")


def _build_progress_markdown(
    issue_number: int,
    issue_url: str,
    author: str,
    stage: str,  # "intake" | "analyzing" | "coding" | "committed" | "pr_created" | "error"
    file_count: int = 0,
    changed_paths: Optional[list[str]] = None,
    commit_sha: Optional[str] = None,
    pr_number: Optional[int] = None,
    pr_url: Optional[str] = None,
    summary: Optional[str] = None,
    error_message: Optional[str] = None,
) -> str:
    """Builds a live checklist markdown showing real-time autonomous progress."""
    changed_paths = changed_paths or []
    branch = f"issue-{issue_number}"

    chk_maintainer = f"[x] Maintainer approval verified (@{author})"
    chk_issue = f"[x] Created & linked Issue [#{issue_number}]({issue_url})"

    if stage == "intake":
        chk_files = "[⏳] Inspecting codebase files & ephemeral environment..."
        chk_solve = "[ ] Synthesizing solution & patch with Groq AI"
        chk_commit = f"[ ] Committing changes to branch `{branch}`"
        chk_pr = "[ ] Opening Pull Request"
        header = "### ⚡ Turing-agent Fix in Progress..."
    elif stage == "analyzing":
        chk_files = f"[x] Codebase files inspected ({file_count} files analyzed)"
        chk_solve = "[⏳] Synthesizing solution & patch with Groq AI..."
        chk_commit = f"[ ] Committing changes to branch `{branch}`"
        chk_pr = "[ ] Opening Pull Request"
        header = "### ⚡ Turing-agent Fix in Progress..."
    elif stage == "coding":
        chk_files = f"[x] Codebase files inspected ({file_count} files analyzed)"
        chk_solve = f"[x] Solution synthesized by Groq AI ({len(changed_paths)} file(s) modified)"
        chk_commit = f"[⏳] Building Git tree and committing to `{branch}`..."
        chk_pr = "[ ] Opening Pull Request"
        header = "### ⚡ Turing-agent Fix in Progress..."
    elif stage == "committed":
        sha_short = commit_sha[:7] if commit_sha else ""
        chk_files = f"[x] Codebase files inspected ({file_count} files analyzed)"
        chk_solve = f"[x] Solution synthesized by Groq AI ({len(changed_paths)} file(s) modified)"
        chk_commit = f"[x] Changes committed & pushed to branch `{branch}` (`{sha_short}`)"
        chk_pr = "[⏳] Opening Pull Request..."
        header = "### ⚡ Turing-agent Fix in Progress..."
    elif stage == "pr_created":
        sha_short = commit_sha[:7] if commit_sha else ""
        chk_files = f"[x] Codebase files inspected ({file_count} files analyzed)"
        chk_solve = f"[x] Solution synthesized by Groq AI ({len(changed_paths)} file(s) modified)"
        chk_commit = f"[x] Changes committed & pushed to branch `{branch}` (`{sha_short}`)"
        chk_pr = f"[x] **Pull Request Opened**: [#{pr_number}]({pr_url}) 🎉"
        header = "### ✅ Turing-agent Fix Completed!"
    elif stage == "error":
        chk_files = f"[x] Codebase files inspected ({file_count} files analyzed)" if file_count else "[ ] Codebase files inspected"
        chk_solve = "[❌] Error during solution generation"
        chk_commit = f"[ ] Committing changes to branch `{branch}`"
        chk_pr = "[ ] Opening Pull Request"
        header = "### ⚠️ Turing-agent Fix Encountered an Error"
    else:
        header = "### ⚡ Turing-agent Fix in Progress..."

    lines = [
        "<!-- turing-bot-progress -->",
        header,
        f"- {chk_maintainer}",
        f"- {chk_issue}",
        f"- {chk_files}",
        f"- {chk_solve}",
        f"- {chk_commit}",
        f"- {chk_pr}",
    ]

    if changed_paths:
        lines.append("\n**Modified Files:**")
        for p in changed_paths:
            lines.append(f"- `{p}`")

    if summary and stage in ("committed", "pr_created"):
        lines.append(f"\n> **Summary**: {summary}")

    if error_message and stage == "error":
        lines.append(f"\n> **Error**: `{error_message}`")

    if stage == "pr_created":
        lines.append(f"\n_Co-authored with @{author}._")

    return "\n".join(lines)


def _commit_and_push_changes(
    repo: str,
    base_tree_sha: str,
    base_commit_sha: Optional[str],
    branch_name: str,
    changes: list[FileChange],
    commit_message: str,
    author: str,
    token: str,
) -> tuple[str, str]:
    """
    Applies changes to GitHub repository via Git Data API:
    1. Creates blobs for modified files
    2. Builds new git tree on top of base_tree_sha
    3. Creates commit referencing base_commit_sha with co-author attribution
    4. Creates or updates branch refs/heads/{branch_name}
    Returns (commit_sha, tree_sha).
    """
    headers = _github_headers(token)

    tree_entries = []
    for change in changes:
        blob_resp = requests.post(
            f"https://api.github.com/repos/{repo}/git/blobs",
            headers=headers,
            json={"content": change.content, "encoding": "utf-8"},
            timeout=20,
        )
        blob_resp.raise_for_status()
        blob_sha = blob_resp.json()["sha"]
        tree_entries.append({
            "path": change.path,
            "mode": "100644",
            "type": "blob",
            "sha": blob_sha,
        })

    if tree_entries:
        tree_resp = requests.post(
            f"https://api.github.com/repos/{repo}/git/trees",
            headers=headers,
            json={"base_tree": base_tree_sha, "tree": tree_entries},
            timeout=20,
        )
        tree_resp.raise_for_status()
        new_tree_sha = tree_resp.json()["sha"]
    else:
        new_tree_sha = base_tree_sha

    co_author = f"\n\nCo-authored-by: {author} <{author}@users.noreply.github.com>"
    full_msg = commit_message.strip() + co_author

    commit_payload = {
        "message": full_msg,
        "tree": new_tree_sha,
    }
    if base_commit_sha:
        commit_payload["parents"] = [base_commit_sha]

    commit_resp = requests.post(
        f"https://api.github.com/repos/{repo}/git/commits",
        headers=headers,
        json=commit_payload,
        timeout=20,
    )
    commit_resp.raise_for_status()
    commit_sha = commit_resp.json()["sha"]

    # Create or update branch refs/heads/{branch_name}
    ref_resp = requests.post(
        f"https://api.github.com/repos/{repo}/git/refs",
        headers=headers,
        json={"ref": f"refs/heads/{branch_name}", "sha": commit_sha},
        timeout=20,
    )
    if ref_resp.status_code == 422:
        # Branch already exists -> update it with force=True
        patch_resp = requests.patch(
            f"https://api.github.com/repos/{repo}/git/refs/heads/{branch_name}",
            headers=headers,
            json={"sha": commit_sha, "force": True},
            timeout=20,
        )
        patch_resp.raise_for_status()
    else:
        ref_resp.raise_for_status()

    return commit_sha, new_tree_sha

# Extensions to consider as source code (no binaries/lock files)
_SOURCE_EXTS = re.compile(
    r'\.(js|ts|jsx|tsx|mjs|cjs|py|html|css|scss|less|json|yaml|yml|md|sh|go|rs|java|kt|'
    r'swift|rb|php|c|cpp|h|hpp|vue|svelte|astro|toml|ini|conf|env\.example)$',
    re.IGNORECASE
)
_EXCLUDE_DIRS = re.compile(
    r'(^|/)(\.'
    r'|node_modules|dist|build|\.next|__pycache__|\.pyc|coverage|\.cache|vendor|'
    r'\.turbo|\.svelte-kit|\.nuxt|out)/',
    re.IGNORECASE
)


def _github_headers(token: str) -> dict:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Turing-agent",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _score_file_relevance(path: str, issue_title: str, issue_body: str) -> int:
    """
    Ranks files based on relevance to the issue using:
    - Component and filename matching (e.g., NavBar, Header, App)
    - Tokens, anchors, and identifiers mentioned in the issue
    - Directory context (web/landing vs extension)
    """
    text = f"{issue_title} {issue_body}".lower()
    path_low = path.lower()
    filename = os.path.basename(path).lower()
    name_no_ext = os.path.splitext(filename)[0]

    score = 0

    # 1. Exact or partial component/filename match (e.g. "NavBar" or "navbar")
    if name_no_ext and len(name_no_ext) > 2:
        if name_no_ext in text or name_no_ext.replace('-', '') in text or name_no_ext.replace('_', '') in text:
            score += 100

    # 2. Extract issue tokens (words, #anchors, identifiers)
    tokens = set(re.findall(r'[a-zA-Z0-9_#]{3,}', text))
    stop_words = {'the', 'and', 'for', 'this', 'that', 'with', 'from', 'repo', 'github', 'issue', 'button', 'must', 'should', 'here', 'there'}
    for tok in tokens:
        if tok in stop_words:
            continue
        clean_tok = tok.lstrip('#')
        if clean_tok in filename:
            score += 40
        elif clean_tok in path_low:
            score += 20

    # 3. Context clues from problem domain
    if any(k in text for k in ['landing', 'web', 'site', 'frontend', 'page']):
        if any(dir_k in path_low for dir_k in ['web', 'react', 'site', 'src/components', 'pages']):
            score += 30
    if any(k in text for k in ['extension', 'popup', 'background', 'content script']):
        if 'extension' in path_low or 'popup' in path_low:
            score += 30
    if any(k in text for k in ['nav', 'navbar', 'header', 'menu']):
        if 'nav' in path_low or 'header' in path_low:
            score += 60
    if any(k in text for k in ['doc', 'docs', 'documentation']):
        if 'doc' in path_low:
            score += 25

    # Prioritize active source files over configs
    if path_low.endswith(('.jsx', '.tsx', '.js', '.ts', '.vue', '.html', '.css')):
        score += 10

    return score


def _fetch_repo_files(
    repo: str,
    tree_sha: str,
    token: str,
    issue_title: str = "",
    issue_body: str = "",
    max_files: int = 15,
) -> dict[str, str]:
    """
    Fetches the recursive git tree, scores files based on relevance to the issue,
    and downloads full content of the top relevant source files in parallel.
    """
    import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed
    headers = _github_headers(token)

    # 1. Get recursive tree
    resp = requests.get(
        f"https://api.github.com/repos/{repo}/git/trees/{tree_sha}?recursive=1",
        headers=headers, timeout=20
    )
    resp.raise_for_status()
    tree = resp.json().get("tree", [])

    blobs = [
        f for f in tree
        if f.get("type") == "blob"
        and _SOURCE_EXTS.search(f.get("path", ""))
        and not _EXCLUDE_DIRS.search("/" + f.get("path", ""))
        and f.get("size", 0) < 120_000  # skip excessively large assets
    ]

    # Rank files by relevance to the issue
    blobs.sort(
        key=lambda f: _score_file_relevance(f.get("path", ""), issue_title, issue_body),
        reverse=True
    )
    # Pick top relevant files
    blobs = blobs[:max_files]
    logger.info(f"[fetch-files] Top relevant candidate files: {[b['path'] for b in blobs[:5]]}")

    def _fetch_single_blob(blob: dict) -> tuple[str, Optional[str]]:
        try:
            r = requests.get(
                f"https://api.github.com/repos/{repo}/contents/{blob['path']}",
                headers=headers, timeout=10
            )
            r.raise_for_status()
            data = r.json()
            raw = data.get("content", "")
            if raw:
                return blob["path"], base64.b64decode(raw).decode("utf-8", errors="replace")
        except Exception as fetch_err:
            logger.warning(f"[resolve-issue] Could not fetch {blob.get('path')}: {fetch_err}")
        return blob.get("path", ""), None

    contents: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_blob = {executor.submit(_fetch_single_blob, b): b for b in blobs}
        for future in as_completed(future_to_blob):
            path, text = future.result()
            if path and text is not None:
                contents[path] = text

    return contents


def _extract_live_url(text: str) -> Optional[str]:
    """Finds live deployment URLs in issue description."""
    urls = re.findall(r'https?://[^\s)\]"<>]+', text)
    for u in urls:
        low = u.lower()
        if any(h in low for h in ['vercel.app', 'netlify.app', 'pages.dev', 'koyeb.app', 'onrender.com']):
            return u
        if not any(h in low for h in ['github.com', 'githubusercontent.com', 'loom.com', 'groq.com', 'tinyfish.ai']):
            return u
    return None


def _run_tinyfish_inspection(url: str, goal: str, api_key: str) -> tuple[Optional[str], list[str]]:
    """Runs TinyFish web agent on the target URL to observe the live bug state and capture screenshots."""
    import time
    try:
        logger.info(f"[TinyFish Inspection] Running agent on live URL: {url}...")
        headers = {"Content-Type": "application/json", "X-API-Key": api_key}
        res = requests.post(
            "https://agent.tinyfish.ai/v1/automation/run-async",
            json={
                "url": url,
                "goal": goal,
                "browser_profile": "lite",
            },
            headers=headers,
            timeout=15
        )
        if not res.ok:
            logger.warning(f"[TinyFish Inspection] Start failed: {res.status_code} {res.text}")
            return None, []

        run_id = res.json().get("run_id")
        logger.info(f"[TinyFish Inspection] Started run {run_id}. Polling...")

        for _ in range(15):
            time.sleep(2)
            poll = requests.get(f"https://agent.tinyfish.ai/v1/runs/{run_id}", headers=headers, timeout=10)
            if poll.ok:
                data = poll.json()
                if data.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
                    result_obj = data.get("result", {})
                    summary = (
                        result_obj.get("result")
                        if isinstance(result_obj, dict)
                        else str(result_obj)
                    )
                    steps = data.get("steps", [])
                    screenshots = [s["screenshot"] for s in steps if s.get("screenshot")]
                    logger.info(f"[TinyFish Inspection] Done! Found {len(screenshots)} screenshots.")
                    return summary, screenshots
    except Exception as e:
        logger.warning(f"[TinyFish Inspection] Exception during run: {e}")
    return None, []


def _call_groq_for_fix(
    issue_title: str,
    issue_body: str,
    issue_number: int,
    repo: str,
    file_contents: dict[str, str],
    discussion_url: Optional[str],
    tinyfish_observation: Optional[str] = None,
) -> ResolveIssueResult:
    """
    Calls Groq (openai/gpt-oss-120b) with issue + codebase context + TinyFish observation.
    Returns structured file changes.
    """
    import json
    from groq import Groq

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add GROQ_API_KEY=gsk_... to your .env file. "
            "Free keys available at https://console.groq.com/"
        )

    client = Groq(api_key=api_key)

    # Build file context with full content (up to 35k chars per file, total 90k chars)
    file_context_parts = []
    total_chars = 0
    char_budget = 90_000  # Groq 128k context window easily accommodates full files
    for path, content in file_contents.items():
        snippet = content if len(content) <= 35_000 else content[:35_000] + "\n// ... [remaining content truncated for length]"
        part = f"### File: `{path}`\n```\n{snippet}\n```"
        if total_chars + len(part) > char_budget:
            break
        file_context_parts.append(part)
        total_chars += len(part)

    file_context = "\n\n".join(file_context_parts) if file_context_parts else "No relevant source files found."

    system_prompt = (
        "You are an expert senior software engineer and autonomous code repair agent.\n"
        "Given a GitHub issue description and the repository's source files, your goal is to make the EXACT, SURGICAL fix.\n\n"
        "CRITICAL RULES:\n"
        "1. SURGICAL REPAIR: If the bug is a broken link, wrong URL, bad property, missing attribute, or typo, make ONLY that specific change.\n"
        "2. STRICT PRESERVATION: You MUST preserve ALL existing imports, components, functions, styles, comments, and unrelated logic.\n"
        "   NEVER remove existing components, delete imports, or replace a full file with a skeleton or placeholder.\n"
        "3. TARGET THE CORRECT COMPONENT: Fix the bug in the specific child component where the element lives (e.g. `NavBar.jsx` for navbar buttons, `HeroSection.jsx` for hero content).\n"
        "   Do NOT modify container files (like `App.jsx`) unless the container file itself directly contains the buggy code.\n"
        "4. COMPLETE FILE CONTENT: Return the COMPLETE file content for each modified file with the surgical fix applied, with all original code intact.\n"
        "5. Return ONLY a valid JSON object matching the schema:\n"
        "{\n"
        '  "changes": [\n'
        '    { "path": "relative/path/to/file.ext", "content": "...complete file content with fix applied..." }\n'
        "  ],\n"
        '  "commit_message": "fix: precise description of the change",\n'
        '  "summary": "1-2 sentence explanation of the fix"\n'
        "}\n"
    )

    user_prompt = (
        f"## GitHub Issue #{issue_number}: {issue_title}\n\n"
        f"**Repository**: `{repo}`\n"
        + (f"**Source Discussion**: {discussion_url}\n" if discussion_url else "")
        + (f"\n### 🐟 TinyFish Web Agent Live Observation:\n{tinyfish_observation}\n\n" if tinyfish_observation else "")
        + f"\n### Issue Description:\n{issue_body}\n\n"
        "---\n\n"
        "### Repository Source Files:\n\n"
        f"{file_context}\n\n"
        "---\n\n"
        "Now resolve this issue with surgical precision, preserving all other existing code intact."
    )

    models_to_try = [
        m for m in [
            os.getenv("GROQ_MODEL"),
            "openai/gpt-oss-120b",
            "qwen/qwen3.8-27b",
            "openai/gpt-oss-20b",
        ] if m
    ]

    response = None
    last_err = None
    for model_name in models_to_try:
        try:
            logger.info(f"[resolve-issue] Calling Groq ({model_name}) for issue #{issue_number}...")
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=8000,
                response_format={"type": "json_object"},
            )
            logger.info(f"[resolve-issue] Successfully generated fix with model {model_name}")
            break
        except Exception as groq_err:
            logger.warning(f"[resolve-issue] Groq model {model_name} failed: {groq_err}")
            last_err = groq_err

    if not response:
        raise RuntimeError(f"All Groq models failed. Last error: {last_err}")

    raw = response.choices[0].message.content.strip()
    logger.info(f"[resolve-issue] Groq responded ({len(raw)} chars)")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Groq returned invalid JSON: {e}\n\nRaw response:\n{raw[:500]}")

    changes = [FileChange(**c) for c in parsed.get("changes", [])]
    return ResolveIssueResult(
        changes=changes,
        commit_message=parsed.get("commit_message", f"fix: resolve issue #{issue_number}"),
        summary=parsed.get("summary", "Automated fix generated by Turing-agent."),
    )


@app.post("/resolve-issue")
def resolve_issue(payload: ResolveIssuePayload):
    """
    AI-powered code resolution and branch commit endpoint.

    Called by n8n after a maintainer approves an issue.
    1. Updates discussion progress: Intake & inspection
    2. Fetches relevant repo files + runs TinyFish inspection if live URL exists
    3. Updates discussion progress: Analyzing & LLM synthesizing
    4. Calls Groq LLM to synthesize code modifications
    5. Directly builds Git tree, commits with co-author attribution, and pushes branch
    6. Updates discussion progress: Committed & ready for PR
    7. Returns complete commit details for n8n to open the Pull Request
    """
    logger.info(f"[resolve-issue] Request: issue #{payload.issue_number} — {payload.issue_title}")

    github_token = os.getenv("GITHUB_TOKEN")
    branch_name = payload.branch_name or f"issue-{payload.issue_number}"
    author = payload.author or "contributor"
    issue_url = payload.issue_url or f"https://github.com/{payload.repo_full_name}/issues/{payload.issue_number}"

    # Progress Step 1: Intake
    _update_discussion_progress(
        token=github_token,
        comment_id=payload.progress_comment_id,
        body=_build_progress_markdown(
            issue_number=payload.issue_number,
            issue_url=issue_url,
            author=author,
            stage="intake",
        )
    )

    file_contents = {}
    try:
        # Step 1: Fetch repo source files with relevance scoring
        logger.info(f"[resolve-issue] Fetching relevant files for '{payload.issue_title}' from {payload.repo_full_name}...")
        file_contents = _fetch_repo_files(
            repo=payload.repo_full_name,
            tree_sha=payload.base_tree_sha,
            token=github_token,
            issue_title=payload.issue_title,
            issue_body=payload.issue_body,
            max_files=15,
        )
        logger.info(f"[resolve-issue] Fetched {len(file_contents)} source files.")

        # Progress Step 2: Analyzing
        _update_discussion_progress(
            token=github_token,
            comment_id=payload.progress_comment_id,
            body=_build_progress_markdown(
                issue_number=payload.issue_number,
                issue_url=issue_url,
                author=author,
                stage="analyzing",
                file_count=len(file_contents),
            )
        )

        # Step 2: TinyFish Web Agent Live Site Inspection (if live URL found)
        tinyfish_key = os.getenv("TINYFISH_API_KEY")
        live_target_url = payload.live_url or _extract_live_url(payload.issue_body)
        tf_summary = None
        tf_screenshots = []

        if live_target_url and tinyfish_key:
            goal_prompt = (
                f"Verify bug on {live_target_url}. Bug: {payload.issue_title}. "
                "Observe page contents, navigation, buttons, and note any error banners or unexpected states."
            )
            tf_summary, tf_screenshots = _run_tinyfish_inspection(
                url=live_target_url,
                goal=goal_prompt,
                api_key=tinyfish_key,
            )

        # Step 3: Call Groq LLM for surgical code fix
        result = _call_groq_for_fix(
            issue_title=payload.issue_title,
            issue_body=payload.issue_body,
            issue_number=payload.issue_number,
            repo=payload.repo_full_name,
            file_contents=file_contents,
            discussion_url=payload.discussion_url,
            tinyfish_observation=tf_summary,
        )

        # Step 3.1: Guardrail against accidental excessive code deletion
        sanitized_changes = []
        for change in result.changes:
            orig = file_contents.get(change.path)
            if orig:
                orig_lines = orig.splitlines()
                new_lines = change.content.splitlines()
                # If the file lost >40% of its lines and original had >25 lines, reject hallucinated truncation
                if len(orig_lines) > 25 and len(new_lines) < len(orig_lines) * 0.6:
                    logger.warning(
                        f"[Safety Guardrail] Detected excessive code deletion in {change.path}: "
                        f"{len(orig_lines)} original lines reduced to {len(new_lines)} lines! "
                        "Rejecting hallucinated truncation to protect existing codebase."
                    )
                    continue
            sanitized_changes.append(change)
        result.changes = sanitized_changes

        logger.info(
            f"[resolve-issue] Groq generated {len(result.changes)} file change(s). "
            f"Commit: '{result.commit_message}'"
        )

        # Progress Step 3: Coding
        _update_discussion_progress(
            token=github_token,
            comment_id=payload.progress_comment_id,
            body=_build_progress_markdown(
                issue_number=payload.issue_number,
                issue_url=issue_url,
                author=author,
                stage="coding",
                file_count=len(file_contents),
                changed_paths=[c.path for c in result.changes],
            )
        )

        # Step 4: Commit and push changes via Git Data API
        commit_sha, tree_sha = _commit_and_push_changes(
            repo=payload.repo_full_name,
            base_tree_sha=payload.base_tree_sha,
            base_commit_sha=payload.base_commit_sha,
            branch_name=branch_name,
            changes=result.changes,
            commit_message=result.commit_message,
            author=author,
            token=github_token,
        )
        logger.info(f"[resolve-issue] Committed {commit_sha[:8]} on branch {branch_name}")

        # Progress Step 4: Committed (ready for PR opening)
        _update_discussion_progress(
            token=github_token,
            comment_id=payload.progress_comment_id,
            body=_build_progress_markdown(
                issue_number=payload.issue_number,
                issue_url=issue_url,
                author=author,
                stage="committed",
                file_count=len(file_contents),
                changed_paths=[c.path for c in result.changes],
                commit_sha=commit_sha,
                summary=result.summary,
            )
        )

        return {
            "status": "success",
            "commit_sha": commit_sha,
            "tree_sha": tree_sha,
            "branch_name": branch_name,
            "commit_message": result.commit_message,
            "summary": result.summary,
            "changes": [{"path": c.path, "content": c.content} for c in result.changes],
            "files_changed": len(result.changes),
            "changed_paths": [c.path for c in result.changes],
            "files_analyzed": len(file_contents),
            "tinyfish_summary": tf_summary,
            "tinyfish_screenshots": tf_screenshots,
            "live_url": live_target_url,
            "progress_comment_id": payload.progress_comment_id,
            "author": author,
        }

    except Exception as e:
        logger.error(f"[resolve-issue] Unexpected error: {e}", exc_info=True)
        _update_discussion_progress(
            token=github_token,
            comment_id=payload.progress_comment_id,
            body=_build_progress_markdown(
                issue_number=payload.issue_number,
                issue_url=issue_url,
                author=author,
                stage="error",
                file_count=len(file_contents),
                error_message=str(e),
            )
        )
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e), "traceback": traceback.format_exc()},
        )


# ---------------------------------------------------------------------------
# /triage-discussion — Immediate Maintainer Validation + TinyFish Correlation
# ---------------------------------------------------------------------------

class TriageDiscussionPayload(BaseModel):
    """Payload sent by n8n when a new GitHub discussion is opened."""
    discussion_title: str = Field(..., description="GitHub discussion title")
    discussion_body: str = Field(..., description="GitHub discussion description body")
    discussion_number: Optional[Any] = Field(None, description="Discussion number")
    discussion_url: Optional[str] = Field(None, description="GitHub discussion URL")
    author: Optional[str] = Field("contributor", description="Author username")
    repository: Optional[str] = Field("YASHK-arch/RepoOwl-extension", description="Full repo name owner/repo")


@app.post("/triage-discussion")
def triage_discussion(payload: TriageDiscussionPayload):
    """
    Called immediately upon a new GitHub discussion.
    1. Generates Turing's maintainer validation comment.
    2. Uses TinyFish to scrape open & closed issues/discussions across the repository.
    3. Correlates impacted components, past PRs, commits, and scopes the issue for work.
    4. Returns both comments so n8n can post them to GitHub.
    """
    logger.info(f"[triage-discussion] Triaging #{payload.discussion_number}: {payload.discussion_title} by @{payload.author}")

    try:
        # Step 1: Immediate Turing validation review
        validation_comment = generate_turing_validation(
            discussion_title=payload.discussion_title,
            discussion_body=payload.discussion_body,
            author=payload.author or "contributor",
            repo=payload.repository or "YASHK-arch/RepoOwl-extension"
        )

        # Step 2: TinyFish issue scraping & component correlation
        tinyfish_key = os.getenv("TINYFISH_API_KEY", "")
        scraped_issues = []
        if tinyfish_key:
            scraped_issues = scrape_repository_issues_and_discussions(
                repo=payload.repository or "YASHK-arch/RepoOwl-extension",
                api_key=tinyfish_key,
                max_issues_to_inspect=3
            )

        # Step 3: Produce TinyFish correlation report
        correlation_report = generate_tinyfish_correlation_report(
            repo=payload.repository or "YASHK-arch/RepoOwl-extension",
            discussion_title=payload.discussion_title,
            discussion_body=payload.discussion_body,
            scraped_issues=scraped_issues
        )

        logger.info(f"[triage-discussion] Successfully generated validation & TinyFish correlation ({len(scraped_issues)} issues examined).")
        return {
            "status": "success",
            "validation_comment": validation_comment,
            "tinyfish_correlation_comment": correlation_report,
            "scraped_issues_count": len(scraped_issues)
        }

    except Exception as e:
        logger.error(f"[triage-discussion] Error during triage: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e), "traceback": traceback.format_exc()}
        )


# ---------------------------------------------------------------------------
# /chat-turing — Intent-driven Q&A & live TinyFish investigation endpoint
# ---------------------------------------------------------------------------

class ChatTuringPayload(BaseModel):
    """Payload from n8n when a discussion comment mentions Turing."""
    discussion_title: str = Field(..., description="GitHub discussion title")
    discussion_body: str = Field(..., description="GitHub discussion body")
    comment_body: str = Field(..., description="Incoming comment text")
    comment_author: str = Field(..., description="Author of the comment")
    discussion_number: Optional[Any] = Field(None, description="Discussion number")
    discussion_url: Optional[str] = Field(None, description="Discussion URL")
    discussion_id: Optional[str] = Field(None, description="GraphQL node ID of discussion")
    comment_id: Optional[str] = Field(None, description="GraphQL node ID of comment")
    repository: Optional[str] = Field("YASHK-arch/RepoOwl-extension", description="Repository full name")
    live_url: Optional[str] = Field(None, description="Optional live deployment URL")


@app.post("/chat-turing")
def chat_turing(payload: ChatTuringPayload):
    """
    Intelligent live Q&A endpoint for Turing-agent:
    1. Parses the incoming comment using the LLM intent layer (Groq).
    2. Serializes appropriate execution:
       - FIND_RELATED_ISSUES: Uses TinyFish Web Fetch API to scrape repo issues & PRs, checks for component conflicts.
       - REPRODUCE_BUG: Uses TinyFish Web Agent to automate live browser reproduction and capture visual screencast/proof.
       - ANALYZE_PROPOSAL: Evaluates trade-offs, architectural drawbacks, and edge-cases of proposed alternatives.
       - GENERAL_QA: Direct, contextual technical answer without boilerplate validation templates.
    3. Returns the reply markdown.
    """
    logger.info(f"[chat-turing] Processing comment from @{payload.comment_author}: '{payload.comment_body[:80]}'")
    try:
        from turing_qa import dispatch_turing_chat

        result = dispatch_turing_chat(
            discussion_title=payload.discussion_title,
            discussion_body=payload.discussion_body,
            comment_body=payload.comment_body,
            comment_author=payload.comment_author,
            repository=payload.repository or "YASHK-arch/RepoOwl-extension",
            discussion_url=payload.discussion_url,
            live_url=payload.live_url,
            tinyfish_api_key=os.getenv("TINYFISH_API_KEY"),
            github_token=os.getenv("GITHUB_TOKEN")
        )
        return result
    except Exception as e:
        logger.error(f"[chat-turing] Error processing chat: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e), "traceback": traceback.format_exc()}
        )


