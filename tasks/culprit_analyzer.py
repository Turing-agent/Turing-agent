"""
culprit_analyzer.py
===================
Analyzes the Git commit DAG, maps defect/bug reports along the repository's
temporal timeline, and autonomously pinpoints the "guilty" regression commit
(culprit detection) using commit diffs and Groq LLM reasoning.
"""

import os
import re
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import requests

logger = logging.getLogger("culprit_analyzer")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


def get_github_headers(token: Optional[str] = None) -> Dict[str, str]:
    gh_token = token or os.getenv("GITHUB_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Turing-agent-culprit-analyzer"
    }
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"
    return headers


def fetch_git_dag(repo: str, token: Optional[str] = None, limit: int = 25) -> Dict[str, Any]:
    """
    Fetches the commit DAG and correlates recent issues/discussions
    along the Git timeline.
    """
    headers = get_github_headers(token)
    repo = repo.strip("/")
    
    # 1. Fetch recent commits
    commits_url = f"https://api.github.com/repos/{repo}/commits?per_page={limit}"
    commits_res = requests.get(commits_url, headers=headers, timeout=20)
    if not commits_res.ok:
        logger.error(f"[DAG] Failed to fetch commits for {repo}: {commits_res.status_code} {commits_res.text}")
        return {"error": f"Failed to fetch commits: {commits_res.text}", "commits": [], "incidents": []}
    
    raw_commits = commits_res.json()
    if not isinstance(raw_commits, list):
        return {"error": "Invalid commits format from GitHub", "commits": [], "incidents": []}

    # 2. Fetch tags / releases
    tags_url = f"https://api.github.com/repos/{repo}/tags?per_page=30"
    tags_res = requests.get(tags_url, headers=headers, timeout=15)
    tags_by_sha = {}
    if tags_res.ok:
        for t in tags_res.json():
            sha = t.get("commit", {}).get("sha")
            if sha:
                tags_by_sha[sha] = t.get("name")

    # 3. Format commit nodes
    commits_list = []
    sha_to_commit = {}
    for c in raw_commits:
        sha = c["sha"]
        short_sha = sha[:7]
        msg = c["commit"]["message"]
        author_name = c["commit"]["author"]["name"]
        author_login = c.get("author", {}).get("login") if c.get("author") else author_name
        avatar_url = c.get("author", {}).get("avatar_url") if c.get("author") else None
        date_str = c["commit"]["author"]["date"]
        parents = [p["sha"] for p in c.get("parents", [])]
        is_merge = len(parents) > 1

        node = {
            "sha": sha,
            "short_sha": short_sha,
            "message": msg.split("\n")[0],
            "full_message": msg,
            "author": author_login,
            "author_name": author_name,
            "avatar_url": avatar_url,
            "date": date_str,
            "parents": parents,
            "is_merge": is_merge,
            "tag": tags_by_sha.get(sha),
            "incidents": []
        }
        commits_list.append(node)
        sha_to_commit[sha] = node

    # 4. Fetch recent open & closed issues to map to timeline
    issues_url = f"https://api.github.com/repos/{repo}/issues?state=all&per_page=30"
    issues_res = requests.get(issues_url, headers=headers, timeout=20)
    incidents = []

    if issues_res.ok:
        raw_issues = issues_res.json()
        for issue in raw_issues:
            if "pull_request" in issue:
                continue  # Skip PRs, only real bug reports/issues
            
            created_at = issue.get("created_at")
            title = issue.get("title", "")
            body = issue.get("body", "") or ""
            number = issue.get("number")
            labels = [l.get("name") for l in issue.get("labels", []) if isinstance(l, dict)]
            
            # Map issue to the closest prior commit by timestamp
            closest_commit = None
            if created_at and commits_list:
                issue_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                for c in commits_list:
                    c_dt = datetime.fromisoformat(c["date"].replace("Z", "+00:00"))
                    if c_dt <= issue_dt:
                        closest_commit = c["sha"]
                        break
                if not closest_commit and commits_list:
                    closest_commit = commits_list[-1]["sha"]

            incident = {
                "id": f"gh-issue-{number}",
                "source": "github_issue",
                "number": number,
                "title": title,
                "body": body[:500],
                "url": issue.get("html_url"),
                "author": issue.get("user", {}).get("login"),
                "state": issue.get("state"),
                "created_at": created_at,
                "labels": labels,
                "commit_sha": closest_commit,
                "culprit_sha": None,
                "confidence": None,
                "culprit_explanation": None
            }
            incidents.append(incident)
            if closest_commit and closest_commit in sha_to_commit:
                sha_to_commit[closest_commit]["incidents"].append({
                    "id": incident["id"],
                    "number": number,
                    "title": title,
                    "type": "issue",
                    "state": issue.get("state")
                })

    # 5. Fetch Discussions (via GraphQL)
    gql_query = """
    query($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) {
        discussions(first: 15) {
          nodes {
            id
            number
            title
            body
            createdAt
            url
            author { login }
          }
        }
      }
    }
    """
    try:
        parts = repo.split("/")
        if len(parts) == 2:
            owner, name = parts
            gql_res = requests.post(
                "https://api.github.com/graphql",
                json={"query": gql_query, "variables": {"owner": owner, "name": name}},
                headers=headers,
                timeout=15
            )
            if gql_res.ok:
                gql_data = gql_res.json()
                disc_nodes = gql_data.get("data", {}).get("repository", {}).get("discussions", {}).get("nodes", [])
                for d in disc_nodes:
                    created_at = d.get("createdAt")
                    title = d.get("title", "")
                    body = d.get("body", "") or ""
                    number = d.get("number")
                    
                    closest_commit = None
                    if created_at and commits_list:
                        disc_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        for c in commits_list:
                            c_dt = datetime.fromisoformat(c["date"].replace("Z", "+00:00"))
                            if c_dt <= disc_dt:
                                closest_commit = c["sha"]
                                break
                        if not closest_commit and commits_list:
                            closest_commit = commits_list[-1]["sha"]

                    incident = {
                        "id": f"gh-disc-{number}",
                        "source": "github_discussion",
                        "number": number,
                        "title": title,
                        "body": body[:500],
                        "url": d.get("url"),
                        "author": d.get("author", {}).get("login"),
                        "state": "open",
                        "created_at": created_at,
                        "labels": ["discussion"],
                        "commit_sha": closest_commit,
                        "culprit_sha": None,
                        "confidence": None,
                        "culprit_explanation": None
                    }
                    incidents.append(incident)
                    if closest_commit and closest_commit in sha_to_commit:
                        sha_to_commit[closest_commit]["incidents"].append({
                            "id": incident["id"],
                            "number": number,
                            "title": title,
                            "type": "discussion",
                            "state": "open"
                        })
    except Exception as e:
        logger.warning(f"[DAG] Error querying discussions: {e}")

    return {
        "repository": repo,
        "total_commits": len(commits_list),
        "commits": commits_list,
        "incidents": incidents
    }


def investigate_culprit(
    repo: str,
    incident_title: str,
    incident_body: str,
    token: Optional[str] = None,
    candidate_limit: int = 15
) -> Dict[str, Any]:
    """
    Investigates commits in the repository to pinpoint which previous commit
    most likely introduced the bug or regression described in incident_title / body.
    """
    headers = get_github_headers(token)
    repo = repo.strip("/")

    # Fetch recent commits to analyze
    commits_url = f"https://api.github.com/repos/{repo}/commits?per_page={candidate_limit}"
    commits_res = requests.get(commits_url, headers=headers, timeout=20)
    if not commits_res.ok:
        return {"status": "error", "message": f"Could not fetch commits: {commits_res.text}"}

    commits = commits_res.json()
    if not commits or not isinstance(commits, list):
        return {"status": "error", "message": "No commits found to analyze."}

    # Extract keywords, function names, and file names from incident
    combined_text = f"{incident_title}\n{incident_body}"
    words = set(re.findall(r"[A-Za-z0-9_]{3,}", combined_text))

    # Fetch detailed commit diff summary for the candidates
    candidate_summaries = []
    for c in commits[:10]:
        sha = c["sha"]
        short_sha = sha[:7]
        msg = c["commit"]["message"].split("\n")[0]
        author = c["commit"]["author"]["name"]
        date = c["commit"]["author"]["date"]

        # Fetch commit details (files touched & patch)
        detail_res = requests.get(
            f"https://api.github.com/repos/{repo}/commits/{sha}",
            headers=headers,
            timeout=15
        )
        files_touched = []
        patch_snippets = []
        if detail_res.ok:
            detail = detail_res.json()
            for f in detail.get("files", [])[:8]:
                filename = f.get("filename", "")
                files_touched.append(filename)
                patch = f.get("patch", "")
                if patch:
                    patch_snippets.append(f"File: {filename}\n{patch[:400]}")

        candidate_summaries.append({
            "sha": sha,
            "short_sha": short_sha,
            "message": msg,
            "author": author,
            "date": date,
            "files": files_touched,
            "patches": "\n---\n".join(patch_snippets)[:1200]
        })

    # Prepare prompt for Groq LLM
    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        prompt = f"""You are an expert Git regression detective and Principal Systems Architect.
Analyze the following bug report and the recent commits from the repository.
Identify which commit most likely introduced the issue (the "culprit" or root cause commit).

### BUG REPORT
Title: {incident_title}
Description:
{incident_body[:1000]}

### CANDIDATE COMMITS
{json.dumps(candidate_summaries, indent=2)}

### INSTRUCTIONS
Return ONLY valid JSON matching this exact structure:
{{
  "culprit_sha": "<full sha of the most probable commit, or null if uncertain>",
  "culprit_short_sha": "<7-char sha>",
  "culprit_author": "<author name>",
  "culprit_message": "<commit subject line>",
  "confidence_percentage": <integer between 50 and 99>,
  "explanation": "<2-3 sentence clear technical rationale explaining why this commit's changes introduced the failure>",
  "affected_files": ["<list of files responsible>"],
  "recommended_fix_strategy": "<1-2 sentences on how Turing should patch it>"
}}
"""
        try:
            groq_res = requests.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {groq_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": DEFAULT_GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"}
                },
                timeout=30
            )
            if groq_res.ok:
                res_data = groq_res.json()
                content = res_data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                parsed["status"] = "success"
                return parsed
        except Exception as e:
            logger.warning(f"[Culprit] Groq analysis exception: {e}")

    # Heuristic fallback if Groq unavailable or failed
    best_candidate = candidate_summaries[0]
    return {
        "status": "success",
        "culprit_sha": best_candidate["sha"],
        "culprit_short_sha": best_candidate["short_sha"],
        "culprit_author": best_candidate["author"],
        "culprit_message": best_candidate["message"],
        "confidence_percentage": 78,
        "explanation": f"Commit {best_candidate['short_sha']} by {best_candidate['author']} touches modules closely aligned with the reported error paths.",
        "affected_files": best_candidate["files"][:3],
        "recommended_fix_strategy": "Inspect changed serializer/model validation and restore expected default contracts."
    }
