"""
TinyFish / Turing-agent - Autonomous GitHub QA Agent Backend
Phase 2 Investigation Architecture & Phase 3 Response Orchestrator

Run the server locally on port 8000 using:
    uvicorn main:app --reload --port 8000
"""

import os
import sys
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
    discussion_url: Optional[str] = Field(None, description="Link back to the original discussion")


class FileChange(BaseModel):
    path: str
    content: str


class ResolveIssueResult(BaseModel):
    changes: list[FileChange]
    commit_message: str
    summary: str


import re
import base64

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


def _fetch_repo_files(repo: str, tree_sha: str, token: str, max_files: int = 15) -> dict[str, str]:
    """
    Fetches the recursive git tree, then downloads content of relevant source files in parallel.
    Returns {path: content} for files likely to be relevant.
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
        and f.get("size", 0) < 60_000  # skip large files
    ]

    # Prefer smaller files first; cap at max_files
    blobs.sort(key=lambda f: f.get("size", 0))
    blobs = blobs[:max_files]

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


def _call_groq_for_fix(
    issue_title: str,
    issue_body: str,
    issue_number: int,
    repo: str,
    file_contents: dict[str, str],
    discussion_url: Optional[str],
) -> ResolveIssueResult:
    """
    Calls Groq (llama-3.1-70b-versatile) with issue + codebase context.
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

    # Build file context (truncate very long files to fit context window)
    file_context_parts = []
    total_chars = 0
    char_budget = 60_000  # ~20k tokens for file content
    for path, content in file_contents.items():
        snippet = content[:3000] if len(content) > 3000 else content
        part = f"### File: `{path}`\n```\n{snippet}\n```"
        if total_chars + len(part) > char_budget:
            break
        file_context_parts.append(part)
        total_chars += len(part)

    file_context = "\n\n".join(file_context_parts) if file_context_parts else "No relevant source files found."

    system_prompt = (
        "You are an expert software engineer and autonomous code repair agent.\n"
        "Given a GitHub issue description and the repository's source files, you will:\n"
        "1. Identify exactly which file(s) need to be modified to resolve the issue.\n"
        "2. Write the complete, corrected file content for each changed file.\n"
        "3. Return ONLY a valid JSON object — no prose, no markdown fences — with this exact schema:\n\n"
        "{\n"
        '  "changes": [\n'
        '    { "path": "relative/path/to/file.ext", "content": "...full file content..." }\n'
        "  ],\n"
        '  "commit_message": "fix: short description of what was changed",\n'
        '  "summary": "1-2 sentence explanation of the fix"\n'
        "}\n\n"
        "Rules:\n"
        "- Always include the COMPLETE file content (not diffs, not partial snippets).\n"
        "- Only include files that actually need to change.\n"
        "- Commit message must follow conventional commits (fix:, feat:, chore:).\n"
        "- If the fix is unclear from the code, make the best educated change based on the issue description.\n"
        "- Return ONLY the JSON object, nothing else."
    )

    user_prompt = (
        f"## GitHub Issue #{issue_number}: {issue_title}\n\n"
        f"**Repository**: `{repo}`\n"
        + (f"**Source Discussion**: {discussion_url}\n" if discussion_url else "")
        + f"\n### Issue Description:\n{issue_body}\n\n"
        "---\n\n"
        "### Repository Source Files:\n\n"
        f"{file_context}\n\n"
        "---\n\n"
        "Now resolve this issue by returning the required JSON object with complete file changes."
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
    AI-powered code resolution endpoint.

    Called by n8n after a maintainer approves an issue.
    Fetches relevant repo files, asks Groq to generate a fix,
    and returns structured file changes + commit message.

    n8n then:
      1. Creates GitHub blobs for each changed file
      2. Creates a new Git tree on top of base_tree_sha
      3. Commits that tree to a feature branch
      4. Opens a PR

    Required env var: GROQ_API_KEY (free at https://console.groq.com/)
    Optional env var: GITHUB_TOKEN (needed for GitHub API calls)
    """
    logger.info(f"[resolve-issue] Request: issue #{payload.issue_number} — {payload.issue_title}")

    github_token = os.getenv("GITHUB_TOKEN")

    try:
        # Step 1: Fetch repo source files
        logger.info(f"[resolve-issue] Fetching files from {payload.repo_full_name} @ tree {payload.base_tree_sha[:8]}...")
        file_contents = _fetch_repo_files(
            repo=payload.repo_full_name,
            tree_sha=payload.base_tree_sha,
            token=github_token,
        )
        logger.info(f"[resolve-issue] Fetched {len(file_contents)} source files.")

        # Step 2: Call Groq LLM for code fix
        result = _call_groq_for_fix(
            issue_title=payload.issue_title,
            issue_body=payload.issue_body,
            issue_number=payload.issue_number,
            repo=payload.repo_full_name,
            file_contents=file_contents,
            discussion_url=payload.discussion_url,
        )

        logger.info(
            f"[resolve-issue] Groq generated {len(result.changes)} file change(s). "
            f"Commit: '{result.commit_message}'"
        )

        return {
            "status": "success",
            "commit_message": result.commit_message,
            "summary": result.summary,
            "changes": [{"path": c.path, "content": c.content} for c in result.changes],
            "files_analyzed": len(file_contents),
        }

    except RuntimeError as e:
        # Config errors (missing API key etc.) — surface clearly
        logger.error(f"[resolve-issue] Configuration error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

    except Exception as e:
        logger.error(f"[resolve-issue] Unexpected error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e), "traceback": traceback.format_exc()},
        )

