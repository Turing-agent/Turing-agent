#!/usr/bin/env python3
"""
scripts/retrigger_discussions.py
Idempotent, rate-limited bulk triage script for Turing-Agent.

Scans open discussions in YASHK-arch/eventyay_Sandbox (specifically "Issue reports"),
skips any discussion that Turing has already commented on, and triggers the full
triage pipeline (Turing maintainer review + TinyFish cross-issue correlation report)
with strict rate-limit pacing and exponential backoff.
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure parent directory and tasks are on sys.path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tasks"))

load_dotenv()

try:
    from tasks.tinyfish_correlator import (
        generate_turing_validation,
        scrape_repository_issues_and_discussions,
        generate_tinyfish_correlation_report
    )
except ImportError:
    from tinyfish_correlator import (
        generate_turing_validation,
        scrape_repository_issues_and_discussions,
        generate_tinyfish_correlation_report
    )

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
TINYFISH_API_KEY = os.getenv("TINYFISH_API_KEY", "")
OWNER = "YASHK-arch"
REPO = "eventyay_Sandbox"
REPO_FULL = f"{OWNER}/{REPO}"
GRAPHQL_URL = "https://api.github.com/graphql"

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "Turing-agent"
}

DELAY_BETWEEN_DISCUSSIONS = 4.0  # seconds to stay safe from rate limits


def run_graphql(query: str, variables: dict) -> dict:
    """Executes a GraphQL query/mutation against GitHub API with retry logic."""
    for attempt in range(3):
        try:
            res = requests.post(GRAPHQL_URL, json={"query": query, "variables": variables}, headers=HEADERS, timeout=30)
            if res.status_code == 200:
                data = res.json()
                if "errors" in data:
                    print(f"    [GraphQL Error]: {data['errors']}")
                return data
            elif res.status_code in [403, 429]:
                wait_time = (2 ** attempt) * 5
                print(f"    [Rate Limit] GitHub rate limit reached (HTTP {res.status_code}). Waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"    [HTTP {res.status_code}]: {res.text[:200]}")
                time.sleep(2)
        except Exception as e:
            print(f"    [GraphQL Exception]: {e}")
            time.sleep(2)
    return {}


def get_target_discussions(category_filter: str = "Issue reports", max_count: int = 50) -> list:
    """Fetches discussions matching category with node IDs, titles, and bodies."""
    query = """
    query($owner: String!, $name: String!, $count: Int!) {
      repository(owner: $owner, name: $name) {
        discussions(first: $count, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes {
            id
            number
            title
            body
            url
            category {
              name
            }
            author {
              login
            }
            comments(first: 20) {
              totalCount
              nodes {
                id
                body
                author {
                  login
                }
              }
            }
          }
        }
      }
    }
    """
    data = run_graphql(query, {"owner": OWNER, "name": REPO, "count": max_count})
    nodes = data.get("data", {}).get("repository", {}).get("discussions", {}).get("nodes", [])
    
    targets = []
    for d in nodes:
        cat = d.get("category", {}).get("name")
        if category_filter and cat != category_filter:
            continue
            
        # Check if Turing already commented
        has_turing = False
        for c in d.get("comments", {}).get("nodes", []):
            body = c.get("body", "")
            if "turing-bot" in body or "TinyFish" in body or "Turing" in c.get("author", {}).get("login", ""):
                has_turing = True
                break
                
        if not has_turing:
            targets.append(d)
            
    return targets


def triage_and_comment(discussion: dict) -> bool:
    """Performs triage review and posts validation comment + TinyFish correlation report."""
    num = discussion["number"]
    title = discussion["title"]
    body = discussion.get("body", "") or "No description provided."
    author = discussion.get("author", {}).get("login") or "contributor"
    node_id = discussion["id"]
    
    print(f"\n[{num}] Triaging: '{title[:60]}...' by @{author}")
    
    # 1. Generate maintainer validation review
    print(f"    Step 1/3: Generating maintainer validation comment (Groq)...")
    try:
        val_comment = generate_turing_validation(
            discussion_title=title,
            discussion_body=body,
            author=author,
            repo=REPO_FULL
        )
    except Exception as e:
        print(f"    [Error] Failed generating validation comment: {e}")
        return False

    # 2. Scrape repository issues and generate TinyFish correlation report
    print(f"    Step 2/3: Generating TinyFish cross-issue correlation report...")
    scraped = []
    if TINYFISH_API_KEY:
        try:
            scraped = scrape_repository_issues_and_discussions(
                repo=REPO_FULL,
                api_key=TINYFISH_API_KEY,
                max_issues_to_inspect=2
            )
        except Exception as e:
            print(f"    [Warning] TinyFish scraping skipped: {e}")
            
    try:
        corr_comment = generate_tinyfish_correlation_report(
            repo=REPO_FULL,
            discussion_title=title,
            discussion_body=body,
            scraped_issues=scraped
        )
    except Exception as e:
        print(f"    [Error] Failed generating correlation report: {e}")
        corr_comment = None

    # 3. Post Validation Comment to GitHub
    print(f"    Step 3/3: Posting comments to GitHub Discussion #{num}...")
    post_comment_mutation = """
    mutation($id: ID!, $body: String!) {
      addDiscussionComment(input: {discussionId: $id, body: $body}) {
        comment {
          id
          url
        }
      }
    }
    """
    full_val_body = "<!-- turing-bot -->\n\n" + val_comment
    res1 = run_graphql(post_comment_mutation, {"id": node_id, "body": full_val_body})
    parent_comment_id = res1.get("data", {}).get("addDiscussionComment", {}).get("comment", {}).get("id")
    
    if not parent_comment_id:
        print(f"    [Error] Failed to post validation comment to #{num}")
        return False
    print(f"    [Success] Validation comment posted successfully.")

    # 4. Post Threaded TinyFish Correlation Report (if generated)
    if corr_comment and parent_comment_id:
        post_reply_mutation = """
        mutation($id: ID!, $body: String!, $replyTo: ID) {
          addDiscussionComment(input: {discussionId: $id, body: $body, replyToId: $replyTo}) {
            comment {
              id
              url
            }
          }
        }
        """
        full_corr_body = "<!-- turing-bot -->\n\n" + corr_comment
        res2 = run_graphql(post_reply_mutation, {"id": node_id, "body": full_corr_body, "replyTo": parent_comment_id})
        if res2.get("data", {}).get("addDiscussionComment", {}).get("comment", {}).get("id"):
            print(f"    [Success] Threaded TinyFish correlation report posted.")

    # Also add EYES reaction if not present
    eyes_mutation = """
    mutation($id: ID!) {
      addReaction(input: {subjectId: $id, content: EYES}) {
        reaction {
          content
        }
      }
    }
    """
    run_graphql(eyes_mutation, {"id": node_id})
    return True


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    print("================================================================")
    print(f"   Turing-Agent Bulk Triage Runner (Safe Rate Pacing)")
    print(f"   Target: {REPO_FULL} (Category: Issue reports, Limit: {limit})")
    print("================================================================")
    
    targets = get_target_discussions("Issue reports", max_count=limit)
    print(f"Discovered {len(targets)} discussions needing triage.")
    
    if not targets:
        print("All discussions are already triaged!")
        return

    success_count = 0
    for idx, disc in enumerate(targets, 1):
        print(f"\n--- Progress: [{idx}/{len(targets)}] ---")
        ok = triage_and_comment(disc)
        if ok:
            success_count += 1
            
        if idx < len(targets):
            print(f"Rate safety cooldown: waiting {DELAY_BETWEEN_DISCUSSIONS}s before next discussion...")
            time.sleep(DELAY_BETWEEN_DISCUSSIONS)

    print("\n================================================================")
    print(f"   Done! Successfully triaged {success_count}/{len(targets)} discussions.")
    print("================================================================")


if __name__ == "__main__":
    main()
