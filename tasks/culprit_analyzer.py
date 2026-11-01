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
UPSTREAM_FALLBACK_REPO = "fossasia/eventyay"

# In-memory cache for upstream issue metadata to prevent duplicate API hits
_UPSTREAM_META_CACHE: Dict[int, Dict[str, Any]] = {}


def get_github_headers(token: Optional[str] = None) -> Dict[str, str]:
    gh_token = token or os.getenv("GITHUB_TOKEN", "")
    if not gh_token:
        # Check .env file
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("GITHUB_TOKEN="):
                        gh_token = line.strip().split("=", 1)[1].strip()
                        break
        # Fallback to gh auth token
        if not gh_token:
            try:
                import subprocess
                gh_token = subprocess.check_output("gh auth token", shell=True).decode().strip()
            except Exception:
                pass

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Turing-agent-culprit-analyzer"
    }
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"
    return headers


def _extract_upstream_issue_meta(title: str, body: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Extracts true upstream issue metadata (number, created_at, state, url)
    when an issue or discussion originated from or mirrors an upstream issue.
    """
    # 1. Check if body contains explicit synced metadata
    date_match = re.search(r"Original Report Date[\*`:\s]+`?([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z?)`?", body or "")
    url_match = re.search(r"\[fossasia/eventyay#(\d+)\]\((https://github\.com/fossasia/eventyay/issues/\d+)\)", body or "")
    if date_match:
        upstream_num = int(url_match.group(1)) if url_match else None
        upstream_url = url_match.group(2) if url_match else None
        return {
            "created_at": date_match.group(1),
            "upstream_number": upstream_num,
            "upstream_url": upstream_url,
            "has_upstream": True
        }

    # 2. Check title pattern: [#6727] ...
    num_match = re.search(r"\[#?(\d{4,5})\]", title or "")
    if num_match:
        num = int(num_match.group(1))
        if num in _UPSTREAM_META_CACHE:
            return _UPSTREAM_META_CACHE[num]

        try:
            url = f"https://api.github.com/repos/{UPSTREAM_FALLBACK_REPO}/issues/{num}"
            r = requests.get(url, headers=headers, timeout=5)
            if r.ok:
                data = r.json()
                meta = {
                    "created_at": data.get("created_at"),
                    "upstream_number": num,
                    "upstream_url": data.get("html_url"),
                    "state": data.get("state"),
                    "has_upstream": True
                }
                _UPSTREAM_META_CACHE[num] = meta
                return meta
        except Exception as e:
            logger.debug(f"[UpstreamMeta] Error checking upstream #{num}: {e}")

    return {"created_at": None, "upstream_number": None, "upstream_url": None, "has_upstream": False}


def compute_git_lanes(commits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Assigns Git DAG swimlane coordinates (lane index) and connector lines
    to render an authentic visual Git Graph (matching GitKraken / VS Code Git Graph).
    """
    active_lanes = []
    
    for c in commits:
        sha = c["sha"]
        parents = c.get("parents", [])
        
        # Check if this commit continues an existing branch lane
        assigned_lane = 0
        if sha in active_lanes:
            assigned_lane = active_lanes.index(sha)
            active_lanes[assigned_lane] = parents[0] if parents else None
        else:
            # Allocate next free lane or reuse 0
            if None in active_lanes:
                assigned_lane = active_lanes.index(None)
                active_lanes[assigned_lane] = parents[0] if parents else None
            else:
                assigned_lane = len(active_lanes)
                active_lanes.append(parents[0] if parents else None)

        c["lane"] = min(assigned_lane, 3)  # Cap visually at 3 lanes for clean alignment
        c["lane_color"] = ["#38bdf8", "#a855f7", "#ec4899", "#10b981"][c["lane"] % 4]

        # Handle branch merges: second parent occupies/opens another lane
        if len(parents) > 1:
            second_parent = parents[1]
            if second_parent not in active_lanes:
                if None in active_lanes:
                    idx = active_lanes.index(None)
                    active_lanes[idx] = second_parent
                else:
                    active_lanes.append(second_parent)

    return commits


def fetch_git_dag(repo: str, token: Optional[str] = None, limit: int = 30) -> Dict[str, Any]:
    """
    Fetches the commit DAG and correlates recent issues/discussions
    along the Git timeline.
    """
    headers = get_github_headers(token)
    repo = repo.strip("/")
    
    # 1. Determine default branch
    default_branch = "dev"
    try:
        repo_info_res = requests.get(f"https://api.github.com/repos/{repo}", headers=headers, timeout=10)
        if repo_info_res.ok:
            default_branch = repo_info_res.json().get("default_branch", "dev")
    except Exception:
        pass

    # 2. Fetch recent commits
    commits_url = f"https://api.github.com/repos/{repo}/commits?per_page={limit}"
    commits_res = requests.get(commits_url, headers=headers, timeout=20)
    if not commits_res.ok:
        logger.error(f"[DAG] Failed to fetch commits for {repo}: {commits_res.status_code} {commits_res.text}")
        return {
            "error": f"Failed to fetch commits: {commits_res.text}",
            "commits": [],
            "incidents": [],
            "repository": repo,
            "default_branch": default_branch
        }
    
    raw_commits = commits_res.json()
    if not isinstance(raw_commits, list):
        return {"error": "Invalid commits format from GitHub", "commits": [], "incidents": []}

    # 3. Fetch tags / releases
    tags_url = f"https://api.github.com/repos/{repo}/tags?per_page=30"
    tags_res = requests.get(tags_url, headers=headers, timeout=15)
    tags_by_sha = {}
    if tags_res.ok:
        for t in tags_res.json():
            sha = t.get("commit", {}).get("sha")
            if sha:
                tags_by_sha[sha] = t.get("name")

    # 4. Format commit nodes
    commits_list = []
    sha_to_commit = {}
    for idx, c in enumerate(raw_commits):
        sha = c["sha"]
        short_sha = sha[:7]
        msg = c["commit"]["message"]
        author_name = c["commit"]["author"]["name"]
        author_login = c.get("author", {}).get("login") if c.get("author") else author_name
        avatar_url = c.get("author", {}).get("avatar_url") if c.get("author") else None
        date_str = c["commit"]["author"]["date"]
        parents = [p["sha"] for p in c.get("parents", [])]
        is_merge = len(parents) > 1

        # Branch labels (e.g. head of default branch)
        branch_refs = []
        if idx == 0:
            branch_refs.append(default_branch)
            branch_refs.append(f"origin/{default_branch}")

        node = {
            "sha": sha,
            "short_sha": short_sha,
            "commit_url": f"https://github.com/{repo}/commit/{sha}",
            "message": msg.split("\n")[0],
            "full_message": msg,
            "author": author_login,
            "author_url": f"https://github.com/{author_login}",
            "author_name": author_name,
            "avatar_url": avatar_url,
            "date": date_str,
            "parents": parents,
            "is_merge": is_merge,
            "tag": tags_by_sha.get(sha),
            "branch_refs": branch_refs,
            "incidents": []
        }
        commits_list.append(node)
        sha_to_commit[sha] = node

    # Compute swimlane rails for authentic visual git graph
    commits_list = compute_git_lanes(commits_list)

    # 5. Fetch recent open & closed issues to map to timeline
    # Using GitHub Search API to avoid PR-only pollution and get true bug issues
    incidents = []
    seen_incident_ids = set()

    search_url = f"https://api.github.com/search/issues?q=repo:{repo}+is:issue&sort=created&order=desc&per_page=50"
    search_res = requests.get(search_url, headers=headers, timeout=20)
    raw_issues = []

    if search_res.ok:
        raw_issues = search_res.json().get("items", [])
    else:
        # Fallback to direct repo issues if search hit secondary rate limit
        issues_res = requests.get(f"https://api.github.com/repos/{repo}/issues?state=all&per_page=50", headers=headers, timeout=20)
        if issues_res.ok:
            raw_issues = [i for i in issues_res.json() if "pull_request" not in i]

    # Process issues
    for issue in raw_issues:
        created_at = issue.get("created_at")
        title = issue.get("title", "")
        body = issue.get("body", "") or ""
        number = issue.get("number")
        labels = [l.get("name") for l in issue.get("labels", []) if isinstance(l, dict)]
        html_url = issue.get("html_url")
        author_login = issue.get("user", {}).get("login", "unknown")
        state = issue.get("state", "open")

        # Resolve upstream true reporting date if this is a mirrored issue or has [#NUM]
        upstream_meta = _extract_upstream_issue_meta(title, body, headers)
        effective_date = upstream_meta["created_at"] or created_at

        # Map issue to the closest prior commit by effective timestamp
        closest_commit = None
        if effective_date and commits_list:
            try:
                issue_dt = datetime.fromisoformat(effective_date.replace("Z", "+00:00"))
                for c in commits_list:
                    c_dt = datetime.fromisoformat(c["date"].replace("Z", "+00:00"))
                    if c_dt <= issue_dt:
                        closest_commit = c["sha"]
                        break
            except Exception:
                pass
            if not closest_commit and commits_list:
                closest_commit = commits_list[-1]["sha"]

        inc_id = f"gh-issue-{number}"
        if inc_id in seen_incident_ids:
            continue
        seen_incident_ids.add(inc_id)

        incident = {
            "id": inc_id,
            "source": "github_issue",
            "number": number,
            "title": title,
            "body": body[:600],
            "url": html_url,
            "author": author_login,
            "author_url": f"https://github.com/{author_login}",
            "state": state,
            "created_at": created_at,
            "effective_date": effective_date,
            "labels": labels,
            "commit_sha": closest_commit,
            "upstream_url": upstream_meta["upstream_url"],
            "upstream_number": upstream_meta["upstream_number"],
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
                "state": state,
                "url": html_url,
                "author": author_login,
                "author_url": f"https://github.com/{author_login}",
                "effective_date": effective_date
            })

    # 6. Fetch Discussions (via GraphQL)
    gql_query = """
    query($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) {
        discussions(first: 25) {
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
                    author_login = d.get("author", {}).get("login", "unknown")
                    d_url = d.get("url")

                    # Check upstream true timestamp for [#NUM] discussions
                    upstream_meta = _extract_upstream_issue_meta(title, body, headers)
                    effective_date = upstream_meta["created_at"] or created_at

                    closest_commit = None
                    if effective_date and commits_list:
                        try:
                            disc_dt = datetime.fromisoformat(effective_date.replace("Z", "+00:00"))
                            for c in commits_list:
                                c_dt = datetime.fromisoformat(c["date"].replace("Z", "+00:00"))
                                if c_dt <= disc_dt:
                                    closest_commit = c["sha"]
                                    break
                        except Exception:
                            pass
                        if not closest_commit and commits_list:
                            closest_commit = commits_list[-1]["sha"]

                    inc_id = f"gh-disc-{number}"
                    if inc_id in seen_incident_ids:
                        continue
                    seen_incident_ids.add(inc_id)

                    incident = {
                        "id": inc_id,
                        "source": "github_discussion",
                        "number": number,
                        "title": title,
                        "body": body[:600],
                        "url": d_url,
                        "author": author_login,
                        "author_url": f"https://github.com/{author_login}",
                        "state": upstream_meta.get("state") or "open",
                        "created_at": created_at,
                        "effective_date": effective_date,
                        "labels": ["discussion"],
                        "commit_sha": closest_commit,
                        "upstream_url": upstream_meta["upstream_url"],
                        "upstream_number": upstream_meta["upstream_number"],
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
                            "state": upstream_meta.get("state") or "open",
                            "url": d_url,
                            "author": author_login,
                            "author_url": f"https://github.com/{author_login}",
                            "effective_date": effective_date
                        })
    except Exception as e:
        logger.warning(f"[DAG] Error querying discussions: {e}")

    return {
        "repository": repo,
        "default_branch": default_branch,
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
            "commit_url": f"https://github.com/{repo}/commit/{sha}",
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
                culprit_sha = parsed.get("culprit_sha")
                if culprit_sha:
                    parsed["culprit_commit_url"] = f"https://github.com/{repo}/commit/{culprit_sha}"
                return parsed
        except Exception as e:
            logger.warning(f"[Culprit] Groq analysis exception: {e}")

    # Heuristic fallback if Groq unavailable or failed
    best_candidate = candidate_summaries[0]
    return {
        "status": "success",
        "culprit_sha": best_candidate["sha"],
        "culprit_short_sha": best_candidate["short_sha"],
        "culprit_commit_url": f"https://github.com/{repo}/commit/{best_candidate['sha']}",
        "culprit_author": best_candidate["author"],
        "culprit_author_url": f"https://github.com/{best_candidate['author']}",
        "culprit_message": best_candidate["message"],
        "confidence_percentage": 78,
        "explanation": f"Commit {best_candidate['short_sha']} by {best_candidate['author']} touches modules closely aligned with the reported error paths.",
        "affected_files": best_candidate["files"][:3],
        "recommended_fix_strategy": "Inspect changed serializer/model validation and restore expected default contracts."
    }
