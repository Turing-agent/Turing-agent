#!/usr/bin/env python3
"""
sync_upstream_issues.py
=======================
Synchronizes representative open and closed issues from upstream 'fossasia/eventyay'
to 'eventyaysandbox/eventyay_Sandbox' (or any sandbox repository) so that the sandbox
mirrors the real-world issue lifecycle, labels, metadata, and versioning history.
"""

import os
import sys
import time
import subprocess
import requests

# Ensure utf-8 stdout on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

UPSTREAM_REPO = "fossasia/eventyay"
TARGET_REPO = "eventyaysandbox/eventyay_Sandbox"

# Key issue numbers to ensure are synced (including those in existing discussions)
FEATURED_ISSUE_NUMBERS = [
    6960, 6958, 6953, 6950, 6948, 6946, 6944, 6941, 6937, 6931,
    6928, 6925, 6923, 6913, 6911, 6902, 6727, 6710, 6645, 6633,
    6629, 6606, 6585, 6580, 6573, 6568
]

def get_token():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        try:
            token = subprocess.check_output("gh auth token", shell=True).decode().strip()
        except Exception:
            pass
    return token

def get_headers(token):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Turing-agent-issue-sync",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def fetch_existing_target_issues(token):
    headers = get_headers(token)
    existing = {}
    page = 1
    while page <= 3:
        url = f"https://api.github.com/repos/{TARGET_REPO}/issues?state=all&per_page=100&page={page}"
        r = requests.get(url, headers=headers, timeout=15)
        if not r.ok:
            break
        items = r.json()
        if not items:
            break
        for it in items:
            if "pull_request" in it:
                continue
            title = it.get("title", "")
            existing[title] = it
            # check for [#NUM] tag
            import re
            m = re.search(r"\[#?(\d+)\]", title)
            if m:
                existing[int(m.group(1))] = it
        page += 1
    return existing

def fetch_upstream_issue(issue_num, token):
    headers = get_headers(token)
    url = f"https://api.github.com/repos/{UPSTREAM_REPO}/issues/{issue_num}"
    r = requests.get(url, headers=headers, timeout=15)
    if r.ok:
        data = r.json()
        if "pull_request" not in data:
            return data
    return None

def sync_issues():
    token = get_token()
    if not token:
        print("❌ Error: GITHUB_TOKEN or authenticated gh CLI required.")
        sys.exit(1)

    print(f"🔄 Starting issue synchronization from {UPSTREAM_REPO} to {TARGET_REPO}...")
    headers = get_headers(token)
    existing = fetch_existing_target_issues(token)
    print(f"ℹ️ Found {len(existing)} existing tracked issues in target sandbox.")

    synced_count = 0
    for num in FEATURED_ISSUE_NUMBERS:
        if num in existing:
            print(f"  ✓ Issue #{num} already exists in target (Sandbox #{existing[num]['number']}). Skipping creation.")
            continue

        upstream_data = fetch_upstream_issue(num, token)
        if not upstream_data:
            print(f"  ⚠️ Could not fetch upstream #{num} or it is a PR. Skipping.")
            continue

        raw_title = upstream_data.get("title", "").strip()
        title = f"[#{num}] {raw_title}"
        created_at = upstream_data.get("created_at")
        state = upstream_data.get("state", "open")
        author = upstream_data.get("user", {}).get("login", "unknown")
        html_url = upstream_data.get("html_url")
        raw_body = upstream_data.get("body", "") or "No description provided."
        labels = [l.get("name") for l in upstream_data.get("labels", []) if isinstance(l, dict)]

        body = f"""> 🔗 **Upstream Issue**: [{UPSTREAM_REPO}#{num}]({html_url})
> 👤 **Original Reporter**: @{author}
> 📅 **Original Report Date**: `{created_at}`
> 🏷️ **Labels**: {', '.join(f'`{l}`' for l in labels) if labels else 'None'}
> 📌 **Original State**: `{state.upper()}`

---

### Upstream Problem Statement
{raw_body}
"""

        print(f"  ➕ Creating #{num}: '{title[:50]}...' in {TARGET_REPO}...")
        create_payload = {
            "title": title,
            "body": body,
        }
        create_url = f"https://api.github.com/repos/{TARGET_REPO}/issues"
        res = requests.post(create_url, json=create_payload, headers=headers, timeout=15)
        
        if not res.ok:
            print(f"    ❌ Failed to create issue #{num}: {res.status_code} {res.text}")
            time.sleep(2)
            continue

        new_issue = res.json()
        new_number = new_issue.get("number")
        print(f"    ✓ Created Sandbox Issue #{new_number} for Upstream #{num} ({state})")
        synced_count += 1

        # If upstream state is closed, close target issue
        if state == "closed":
            time.sleep(1)
            close_url = f"https://api.github.com/repos/{TARGET_REPO}/issues/{new_number}"
            close_res = requests.patch(close_url, json={"state": "closed"}, headers=headers, timeout=15)
            if close_res.ok:
                print(f"    ✓ Closed Sandbox Issue #{new_number} to match upstream status.")

        time.sleep(1.5)  # Respect GitHub secondary rate limits

    print(f"\n🎉 Successfully synced {synced_count} issues to {TARGET_REPO}!")

if __name__ == "__main__":
    sync_issues()
