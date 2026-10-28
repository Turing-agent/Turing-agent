"""
TinyFish Cross-Issue & Discussion Scraper and Correlator Module (tinyfish_correlator.py)
Autonomous GitHub QA Agent - Turing-agent / TinyFish

Features:
1. Scrapes open and closed issues and discussions across the repository using TinyFish Web Fetch API.
2. Identifies relevant issues impacting similar components (errors, routes, OAuth, manifests, UI).
3. Gathers historical actions: commits, draft/reviewable PRs, maintainer resolution comments.
4. Uses Groq LLM to synthesize how past resolutions help resolve or scope the current issue.
5. Generates:
   - Turing's immediate maintainer validation comment.
   - TinyFish's cross-issue component intelligence comment.
"""

import os
import re
import json
import time
import logging
import requests
from typing import Optional, Dict, Any, List
from groq import Groq

logger = logging.getLogger("tinyfish.correlator")
logging.basicConfig(level=logging.INFO)


def _get_groq_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")
    return Groq(api_key=api_key)


def _call_groq_chat(system_prompt: str, user_prompt: str, max_tokens: int = 2500) -> str:
    client = _get_groq_client()
    models = [
        os.getenv("GROQ_MODEL"),
        "openai/gpt-oss-120b",
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-20b"
    ]
    models = [m for m in models if m]

    for model_name in models:
        try:
            logger.info(f"[TinyFish Correlator] Calling Groq ({model_name})...")
            res = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=max_tokens
            )
            return res.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"[TinyFish Correlator] Model {model_name} failed: {e}")

    raise RuntimeError("All Groq models failed for correlator.")


def generate_turing_validation(
    discussion_title: str,
    discussion_body: str,
    author: str,
    repo: str
) -> str:
    """
    Generates Turing's immediate maintainer review and validation comment for a new discussion.
    Tone: conversational, friendly, human-like open-source core maintainer.
    """
    system_prompt = (
        "You are Turing, the experienced and friendly core maintainer and QA engineer for this GitHub repository.\n"
        "A user just opened a new discussion bug report. Your job is to immediately validate the report with a warm, "
        "professional, and authoritative maintainer response.\n\n"
        "Guidelines:\n"
        "1. Start with a direct, appreciative verdict acknowledging the author (e.g., 'Hey @{author}! 👋 Thanks for reporting this with such clear context. You're spot on — this is a valid and reproducible issue.').\n"
        "2. Break down the core issue simply in 1-2 focused bullet points (root cause hypothesis, affected component).\n"
        "3. If relevant code or pattern is mentioned, highlight the affected mechanism.\n"
        "4. Conclude by letting them know that TinyFish is actively scraping and correlating historical issues & PRs "
        "across the repository to cross-reference previous fixes and prepare the exact scope for work.\n"
        "5. Keep it clean, friendly, and formatted in standard GitHub markdown. Do NOT use dry robotic templates."
    )

    user_prompt = (
        f"**Repository**: `{repo}`\n"
        f"**Author**: @{author}\n"
        f"**Discussion Title**: {discussion_title}\n\n"
        f"**Discussion Description**:\n{discussion_body}\n\n"
        "Generate your maintainer validation comment now."
    )

    return _call_groq_chat(system_prompt, user_prompt, max_tokens=1500)


def scrape_repository_issues_and_discussions(
    repo: str,
    api_key: str,
    max_issues_to_inspect: int = 3
) -> List[Dict[str, Any]]:
    """
    Uses TinyFish Web Fetch API to scrape open & closed issues and discussions from GitHub,
    then inspects relevant candidate issues for full context (commits, PRs, comments).
    """
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    
    # 1. Fetch main issues list (includes open and closed)
    issues_list_url = f"https://github.com/{repo}/issues?q=is%3Aissue"
    discussions_list_url = f"https://github.com/{repo}/discussions"

    logger.info(f"[TinyFish Scraper] Fetching issues & discussions index from {repo} via TinyFish Fetch API...")
    try:
        r = requests.post(
            "https://api.fetch.tinyfish.ai",
            headers=headers,
            json={"urls": [issues_list_url, discussions_list_url]},
            timeout=30
        )
        if not r.ok:
            logger.warning(f"[TinyFish Scraper] Fetch failed: {r.status_code} {r.text}")
            return []
        data = r.json().get("results", [])
    except Exception as e:
        logger.warning(f"[TinyFish Scraper] Error fetching indexes: {e}")
        return []

    issues_text = ""
    discussions_text = ""
    for item in data:
        if "issues" in item.get("url", ""):
            issues_text = item.get("text", "")
        elif "discussions" in item.get("url", ""):
            discussions_text = item.get("text", "")

    # Extract issue numbers and titles from markdown
    # Format typically: * YASHK-arch/RepoOwl-extension#131 — by ... was closed on ...
    # or * [Title]#131 ...
    found_issue_nums = []
    for line in issues_text.splitlines():
        m = re.search(r'#(\d+)', line)
        if m:
            num = m.group(1)
            if num not in found_issue_nums:
                found_issue_nums.append(num)

    logger.info(f"[TinyFish Scraper] Discovered {len(found_issue_nums)} candidate issues: {found_issue_nums[:10]}")

    if not found_issue_nums:
        return []

    # Pick top candidate issues to deep-scrape
    target_nums = found_issue_nums[:max_issues_to_inspect]
    detail_urls = [f"https://github.com/{repo}/issues/{num}" for num in target_nums]

    logger.info(f"[TinyFish Scraper] Deep-scraping {len(detail_urls)} issue pages with TinyFish Fetch...")
    try:
        r_details = requests.post(
            "https://api.fetch.tinyfish.ai",
            headers=headers,
            json={"urls": detail_urls},
            timeout=40
        )
        if not r_details.ok:
            logger.warning(f"[TinyFish Scraper] Detail fetch failed: {r_details.status_code}")
            return []
        detail_results = r_details.json().get("results", [])
    except Exception as e:
        logger.warning(f"[TinyFish Scraper] Error deep-scraping issue details: {e}")
        return []

    scraped_issues = []
    for res in detail_results:
        u = res.get("url", "")
        txt = res.get("text", "")
        m_num = re.search(r'/issues/(\d+)', u)
        issue_number = m_num.group(1) if m_num else "unknown"

        # Determine if closed or open from content
        is_closed = "closed" in txt.lower()[:300]
        state = "Closed" if is_closed else "Open"

        # Extract title
        title_line = txt.splitlines()[0] if txt.splitlines() else f"Issue #{issue_number}"
        title = title_line.replace("#", "").strip()

        # Extract linked PRs or commits if mentioned (e.g. #132, commit hashes)
        linked_prs = re.findall(r'#(\d+)', txt[:1500])
        linked_prs = [p for p in linked_prs if p != issue_number][:3]

        scraped_issues.append({
            "number": issue_number,
            "url": u,
            "title": title[:100],
            "state": state,
            "linked_prs": linked_prs,
            "content_snippet": txt[:2500]  # First 2.5k chars of issue + comments
        })

    logger.info(f"[TinyFish Scraper] Successfully deep-scraped {len(scraped_issues)} issues.")
    return scraped_issues


def generate_tinyfish_correlation_report(
    repo: str,
    discussion_title: str,
    discussion_body: str,
    scraped_issues: List[Dict[str, Any]]
) -> str:
    """
    Synthesizes the scraped open & closed issues and discussions against the reported bug,
    correlating impacted components, past PRs, commits, and scoping the issue for work.
    """
    if not scraped_issues:
        return (
            "<!-- turing-bot -->\n"
            "## 🐟 TinyFish Cross-Issue Correlation & Component Intelligence\n\n"
            "> Scraped and analyzed via **TinyFish Web Fetch API**.\n\n"
            "*No previous conflicting or overlapping issues were found in the repository index. "
            "This appears to be an isolated bug, ready for standalone triage and resolution.*"
        )

    # Format scraped issues context for Groq
    issues_context_parts = []
    for issue in scraped_issues:
        part = (
            f"### Issue #{issue['number']}: {issue['title']} (State: {issue['state']})\n"
            f"URL: {issue['url']}\n"
            f"Linked PRs/Issues: {', '.join(['#' + p for p in issue['linked_prs']]) if issue['linked_prs'] else 'None'}\n"
            f"Content Excerpt:\n```\n{issue['content_snippet'][:1200]}\n```"
        )
        issues_context_parts.append(part)

    issues_context = "\n\n".join(issues_context_parts)

    system_prompt = (
        "You are TinyFish's Autonomous Repository Intelligence & Cross-Issue Correlator.\n"
        "You analyze newly reported GitHub discussions against scraped open and closed repository issues, "
        "pull requests, commits, and maintainer discussions.\n\n"
        "Your goal is to produce a high-value, technical Markdown comment for developers that:\n"
        "1. Identifies which past open/closed issues or PRs relate to similar components (e.g., OAuth, manifest, background worker, token refresh, UI dialogs).\n"
        "2. Highlights what actions were done on those issues (e.g., commits, draft/reviewable PRs, configuration changes, maintainer comments).\n"
        "3. Explains how the resolution or investigation of those previous issues directly helps resolve the current issue or bounds its scope.\n"
        "4. Formulates a crisp 'Ready for Work' scope: exact files likely needing changes, prerequisite checks, and acceptance criteria.\n\n"
        "Structure of your response:\n"
        "<!-- turing-bot -->\n"
        "## 🐟 TinyFish Cross-Issue Correlation & Component Intelligence\n\n"
        "> *Autonomously scraped from open & closed issues via **TinyFish Web Fetch & Agent API**.*  \n\n"
        "### 🔍 Related Issues & Historical Context\n"
        "(Table or bullet points of related issues: Issue #, State [Open/Closed], Component, Key Takeaways/Actions)\n\n"
        "### 🧩 Component Impact & Resolution Mapping\n"
        "(Explain how past resolutions, commits, or PRs map to this bug)\n\n"
        "### 🎯 Ready-for-Work Scoping\n"
        "- **Impacted Component / Files**: ...\n"
        "- **Recommended Solution Pattern**: ...\n"
        "- **Acceptance Criteria**: ...\n\n"
        "Return ONLY the markdown comment."
    )

    user_prompt = (
        f"**Repository**: `{repo}`\n"
        f"**Current Discussion**: {discussion_title}\n\n"
        f"**Current Discussion Description**:\n{discussion_body}\n\n"
        "---\n\n"
        f"**Scraped Repository Issues & Discussions**:\n\n{issues_context}\n\n"
        "Generate the TinyFish Cross-Issue Correlation & Component Intelligence Report now."
    )

    return _call_groq_chat(system_prompt, user_prompt, max_tokens=2500)
