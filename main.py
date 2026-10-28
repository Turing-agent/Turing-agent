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
