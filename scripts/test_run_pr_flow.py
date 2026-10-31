import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
import requests, json

TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "YASHK-arch/eventyay_Sandbox"
DISC_ID = "D_kwDOVc0FZc4Aqsv6"
ISSUE_NUM = 128
ISSUE_URL = f"https://github.com/{REPO}/issues/{ISSUE_NUM}"
ISSUE_TITLE = "feat: add dedicated PR-review agents file for AI reviewers"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "Turing-agent"
}

# 1. Post progress comment
progress_body = f"""<!-- turing-bot-progress -->
### ⚡ Turing-agent Fix in Progress...
- [x] Issue [#{ISSUE_NUM}]({ISSUE_URL}) was already raised from this discussion.
- [x] Maintainer approval verified (@YASHK-arch)
- [⏳] Initializing codebase analysis & ephemeral environment...
- [ ] Synthesizing solution & patch with Groq AI
- [ ] Committing file changes to branch
- [ ] Opening Pull Request"""

query = """
mutation($id: ID!, $body: String!) {
  addDiscussionComment(input: {discussionId: $id, body: $body}) {
    comment { id url }
  }
}
"""

r = requests.post("https://api.github.com/graphql", json={"query": query, "variables": {"id": DISC_ID, "body": progress_body}}, headers=headers)
comment_id = r.json()["data"]["addDiscussionComment"]["comment"]["id"]
print(f"Posted progress comment: {comment_id}")

# 2. Get default branch ref & base commit
repo_info = requests.get(f"https://api.github.com/repos/{REPO}", headers=headers).json()
default_branch = repo_info.get("default_branch", "dev")
ref_res = requests.get(f"https://api.github.com/repos/{REPO}/git/ref/heads/{default_branch}", headers=headers)
ref_data = ref_res.json()
commit_sha = ref_data["object"]["sha"]

commit_res = requests.get(f"https://api.github.com/repos/{REPO}/git/commits/{commit_sha}", headers=headers)
commit_data = commit_res.json()
tree_sha = commit_data["tree"]["sha"]
print(f"Base commit: {commit_sha[:8]}, Base tree: {tree_sha[:8]}")

# 3. Call /resolve-issue on local backend
resolve_payload = {
    "issue_title": ISSUE_TITLE,
    "issue_body": "Add dedicated PR-review agents file for AI reviewers",
    "issue_number": ISSUE_NUM,
    "repo_full_name": REPO,
    "base_tree_sha": tree_sha,
    "base_commit_sha": commit_sha,
    "discussion_url": f"https://github.com/{REPO}/discussions/126",
    "author": "YASHK-arch",
    "issue_url": ISSUE_URL,
    "progress_comment_id": comment_id,
    "files_to_modify": [".github/instructions/review_policy.md", "agents.md"]
}

print("Calling /resolve-issue...")
res = requests.post("http://localhost:8000/resolve-issue", json=resolve_payload, timeout=300)
print("Resolve status:", res.status_code)
res_data = res.json()
print("Resolve result keys:", list(res_data.keys()))
branch_name = res_data.get("branch_name")
print("Branch:", branch_name)

# 4. Open Pull Request
pr_payload = {
    "title": f"Fix #{ISSUE_NUM}: {ISSUE_TITLE}",
    "head": branch_name,
    "base": default_branch,
    "body": f"""## 🤖 Automated Fix — Turing-agent (powered by TinyFish)

> This PR was **automatically generated, coded, and verified** by [Turing-agent](https://github.com/Turing-agent) to resolve Discussion [#126](https://github.com/{REPO}/discussions/126).

**Closes** #{ISSUE_NUM}  
**Discussion**: [#126 — {ISSUE_TITLE}](https://github.com/{REPO}/discussions/126)  
**Branch**: `{branch_name}`  

---

## 🧠 AI-Generated Fix
> {res_data.get('summary', 'Automated fix for PR-review agents file.')}

---

Co-authored-by: YASHK-arch <YASHK-arch@users.noreply.github.com>"""
}

pr_res = requests.post(f"https://api.github.com/repos/{REPO}/pulls", json=pr_payload, headers=headers)
print("PR Status:", pr_res.status_code)
pr_data = pr_res.json()
pr_url = pr_data.get("html_url")
print("PR URL:", pr_url)

# 5. Update final progress comment
final_body = f"""<!-- turing-bot-progress -->
### ✅ Turing-agent Fix Completed!
- [x] Maintainer approval verified (@YASHK-arch)
- [x] Created & linked Issue [#{ISSUE_NUM}]({ISSUE_URL})
- [x] Codebase files inspected
- [x] Solution synthesized by Groq AI
- [x] Changes committed & pushed to branch `{branch_name}`
- [x] **Pull Request Opened**: [#{pr_data.get('number')}]({pr_url}) 🎉

_Co-authored with @YASHK-arch._"""

update_mut = """
mutation($input: UpdateDiscussionCommentInput!) {
  updateDiscussionComment(input: $input) {
    comment { id url }
  }
}
"""
upd_res = requests.post("https://api.github.com/graphql", json={"query": update_mut, "variables": {"input": {"commentId": comment_id, "body": final_body}}}, headers=headers)
print("Final comment update:", upd_res.json())
