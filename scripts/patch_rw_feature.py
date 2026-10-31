import sys
sys.stdout.reconfigure(encoding="utf-8")
"""
patch_rw_feature.py
====================
Patches main.py and turing-agent-workflow.json to add:
  1. /check-discussion-issue  — check if an issue was already raised for a discussion
  2. /raise-issue-only        — RW command: create issue only, no PR
  3. Workflow updates:
       - New "RW Command" route in Route by Event switch
       - RW command branch: check existing → raise issue only  (or "already raised")
       - Approved branch: check existing issue first → skip consolidate if already exists,
         post "issue already raised, raising PR..." and jump to branch/commit flow
"""
import json, re, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PY = os.path.join(ROOT, "main.py")
WORKFLOW = os.path.join(ROOT, "turing-agent-workflow.json")

# ---------------------------------------------------------------------------
# 1. Append two new endpoints to main.py
# ---------------------------------------------------------------------------
NEW_ENDPOINTS = r'''

# ---------------------------------------------------------------------------
# /check-discussion-issue — Check if an issue was already raised for a discussion
# ---------------------------------------------------------------------------

class CheckDiscussionIssuePayload(BaseModel):
    repository: str
    discussion_node_id: str   # GraphQL node ID of the discussion

@app.post("/check-discussion-issue")
def check_discussion_issue(payload: CheckDiscussionIssuePayload):
    """
    Scans all comments on a discussion for the <!-- turing-raised-issue #N URL --> marker.
    Returns {exists: bool, issue_number: int|None, issue_url: str|None}
    """
    github_token = os.getenv("GITHUB_TOKEN")
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Turing-agent"
    }
    query = """
    query($id: ID!) {
      node(id: $id) {
        ... on Discussion {
          comments(first: 50) {
            nodes { body author { login } }
          }
        }
      }
    }
    """
    try:
        res = requests.post(
            "https://api.github.com/graphql",
            json={"query": query, "variables": {"id": payload.discussion_node_id}},
            headers=headers, timeout=15
        )
        data = res.json()
        nodes = (
            data.get("data", {})
                .get("node", {})
                .get("comments", {})
                .get("nodes", [])
        )
        for comment in nodes:
            body = comment.get("body", "")
            m = re.search(r'<!-- turing-raised-issue #(\d+) (https?://\S+) -->', body)
            if m:
                return {
                    "exists": True,
                    "issue_number": int(m.group(1)),
                    "issue_url": m.group(2)
                }
        return {"exists": False, "issue_number": None, "issue_url": None}
    except Exception as e:
        logger.error(f"[check-discussion-issue] Error: {e}", exc_info=True)
        return {"exists": False, "issue_number": None, "issue_url": None}


# ---------------------------------------------------------------------------
# /raise-issue-only — RW command: consolidate discussion → create issue → comment
# ---------------------------------------------------------------------------

class RaiseIssueOnlyPayload(BaseModel):
    repository: str
    discussion_number: int
    discussion_title: str
    discussion_body: str
    discussion_node_id: str   # GraphQL node ID for posting the marker comment
    discussion_url: Optional[str] = None
    requester: str            # maintainer who typed RW

@app.post("/raise-issue-only")
def raise_issue_only(payload: RaiseIssueOnlyPayload):
    """
    RW command handler:
    1. Consolidates discussion into clean issue spec (via Groq)
    2. Creates GitHub issue via REST API
    3. Posts <!-- turing-raised-issue #N URL --> marker comment on discussion
    4. Returns issue_number and issue_url
    """
    github_token = os.getenv("GITHUB_TOKEN")
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Turing-agent"
    }
    disc_url = payload.discussion_url or \
        f"https://github.com/{payload.repository}/discussions/{payload.discussion_number}"

    try:
        # Step 1 — Consolidate discussion → clean issue spec
        result = consolidate_discussion_to_issue(
            repo=payload.repository,
            discussion_number=payload.discussion_number,
            discussion_title=payload.discussion_title,
            discussion_body=payload.discussion_body,
            approver=payload.requester,
            discussion_url=disc_url,
            token=github_token
        )

        # Step 2 — Create the GitHub issue via REST
        issue_res = requests.post(
            f"https://api.github.com/repos/{payload.repository}/issues",
            headers=headers,
            json={
                "title": result["title"],
                "body": result["body"],
                "labels": result.get("labels", ["ready-for-work"])
            },
            timeout=20
        )
        if not issue_res.ok:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": issue_res.text}
            )

        issue = issue_res.json()
        issue_number = issue["number"]
        issue_url = issue["html_url"]

        # Step 3 — Post marker comment on discussion (invisible HTML comment + visible message)
        comment_body = (
            f"<!-- turing-raised-issue #{issue_number} {issue_url} -->\n\n"
            f"<!-- turing-bot -->\n\n"
            f"### 📋 Issue Raised — Ready for Work\n\n"
            f"Issue [#{issue_number}]({issue_url}) has been raised and is ready to be worked upon. "
            f"The discussion has been consolidated into a structured issue specification.\n\n"
            f"> To trigger an **automated PR** with a code fix, comment `approved`."
        )

        gql_mutation = """
        mutation($id: ID!, $body: String!) {
          addDiscussionComment(input: {discussionId: $id, body: $body}) {
            comment { id url }
          }
        }
        """
        requests.post(
            "https://api.github.com/graphql",
            json={"query": gql_mutation, "variables": {
                "id": payload.discussion_node_id,
                "body": comment_body
            }},
            headers=headers, timeout=15
        )

        logger.info(
            f"[raise-issue-only] Issue #{issue_number} created for "
            f"discussion #{payload.discussion_number}"
        )
        return {
            "status": "success",
            "issue_number": issue_number,
            "issue_url": issue_url,
            "issue_title": result["title"],
            "files_to_modify": result.get("files_to_modify", [])
        }

    except Exception as e:
        logger.error(f"[raise-issue-only] Error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e), "traceback": traceback.format_exc()}
        )
'''

ANCHOR = 'if __name__ == "__main__":'

with open(MAIN_PY, "r", encoding="utf-8") as f:
    src = f.read()

if "/raise-issue-only" in src:
    print("[main.py] New endpoints already present — skipping.")
else:
    idx = src.index(ANCHOR)
    src = src[:idx] + NEW_ENDPOINTS + "\n\n" + src[idx:]
    # Also add `import re` near top if not present
    if "import re\n" not in src and "import re " not in src:
        src = src.replace("import traceback\n", "import re\nimport traceback\n", 1)
    with open(MAIN_PY, "w", encoding="utf-8") as f:
        f.write(src)
    print("[main.py] New endpoints appended ✓")

# ---------------------------------------------------------------------------
# 2. Patch the workflow JSON
# ---------------------------------------------------------------------------

with open(WORKFLOW, "r", encoding="utf-8") as f:
    wf = json.load(f)

# Helper — shorthand for trigger expression
T = "($('GitHub Discussion Events').isExecuted ? $('GitHub Discussion Events') : $('GitHub Webhook (Direct URL)')).item.json"

# ---- 2a. Add new route in "Route by Event" switch -------------------------
route_node = next(n for n in wf["nodes"] if n["name"] == "Route by Event")
existing_outputs = route_node["parameters"]["rules"]["values"]
rw_route_name = "RW Command"
already_has_rw = any(v.get("outputKey") == rw_route_name for v in existing_outputs)

if not already_has_rw:
    existing_outputs.append({
        "conditions": {
            "options": {
                "caseSensitive": True,
                "leftValue": "",
                "typeValidation": "strict",
                "version": 1
            },
            "conditions": [
                {
                    "leftValue": "={{ $json.headers[\"x-github-event\"] }}",
                    "rightValue": "discussion_comment",
                    "operator": {"type": "string", "operation": "equals"}
                },
                {
                    "leftValue": "={{ $json.body.action }}",
                    "rightValue": "created",
                    "operator": {"type": "string", "operation": "equals"}
                }
            ],
            "combinator": "and"
        },
        "renameOutput": True,
        "outputKey": rw_route_name
    })
    print("[workflow] Added 'RW Command' route in 'Route by Event' ✓")
else:
    print("[workflow] 'RW Command' route already present — skipping.")

# ---- 2b. Add new nodes ----------------------------------------------------

existing_node_names = {n["name"] for n in wf["nodes"]}

NEW_NODES = [
    # ── RW Command? (IF) ───────────────────────────────────────────────────
    {
        "id": "node-rw-command-check",
        "name": "RW Command?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [336, 950],
        "parameters": {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "strict",
                    "version": 2
                },
                "conditions": [
                    {
                        "leftValue": f"={{{{ Boolean(({T}.body.comment.body || '').match(/\\bRW\\b/) && ['OWNER','MEMBER','COLLABORATOR'].includes({T}.body.comment.author_association) && !({T}.body.comment.body || '').includes('<!-- turing-bot') && {T}.body.comment.user.type !== 'Bot') }}}}",
                        "operator": {"operation": "equals", "type": "boolean"},
                        "rightValue": True
                    }
                ],
                "combinator": "and"
            },
            "options": {}
        }
    },

    # ── Check Existing Issue (RW) (HTTP POST) ──────────────────────────────
    {
        "id": "node-check-issue-rw",
        "name": "Check Existing Issue (RW)",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.3,
        "position": [560, 950],
        "parameters": {
            "method": "POST",
            "url": "https://pretended-extinct-antirust.ngrok-free.dev/check-discussion-issue",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": f"={{{{ JSON.stringify({{ repository: {T}.body.repository.full_name, discussion_node_id: {T}.body.discussion.node_id }}) }}}}",
            "options": {"timeout": 15000}
        },
        "retryOnFail": True,
        "maxTries": 3,
        "waitBetweenTries": 2000
    },

    # ── Issue Already Raised? (RW) (IF) ───────────────────────────────────
    {
        "id": "node-rw-already-raised-check",
        "name": "Issue Already Raised? (RW)",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [784, 950],
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                "conditions": [
                    {
                        "leftValue": "={{ $json.exists }}",
                        "operator": {"operation": "equals", "type": "boolean"},
                        "rightValue": True
                    }
                ],
                "combinator": "and"
            },
            "options": {}
        }
    },

    # ── Post "Already Raised" comment (RW path) ────────────────────────────
    {
        "id": "node-rw-already-raised-comment",
        "name": "Post RW Already Raised Comment",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.3,
        "position": [1008, 850],
        "parameters": {
            "method": "POST",
            "url": "https://api.github.com/graphql",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Authorization", "value": "=Bearer {{ $env.GITHUB_TOKEN }}"},
                    {"name": "User-Agent", "value": "Turing-agent"}
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            # We reference the check node output for issue_number/issue_url
            "jsonBody": f"={{{{ JSON.stringify({{ query: \"mutation($id: ID!, $body: String!) {{ addDiscussionComment(input: {{discussionId: $id, body: $body}}) {{ comment {{ id url }} }} }}\", variables: {{ id: {T}.body.discussion.node_id, body: '<!-- turing-bot -->\\n\\n⚠️ **Issue already raised.** Issue [#' + $('Check Existing Issue (RW)').item.json.issue_number + '](' + $('Check Existing Issue (RW)').item.json.issue_url + ') was previously created from this discussion. To trigger an automated PR, comment `approved`.' }} }}) }}}}",
            "options": {}
        },
        "onError": "continueRegularOutput"
    },

    # ── Call Raise Issue Only API ──────────────────────────────────────────
    {
        "id": "node-call-raise-issue-only",
        "name": "Call Raise Issue Only API",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.3,
        "position": [1008, 1050],
        "parameters": {
            "method": "POST",
            "url": "https://pretended-extinct-antirust.ngrok-free.dev/raise-issue-only",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": f"={{{{ JSON.stringify({{ repository: {T}.body.repository.full_name, discussion_number: {T}.body.discussion.number, discussion_title: {T}.body.discussion.title, discussion_body: {T}.body.discussion.body, discussion_node_id: {T}.body.discussion.node_id, discussion_url: {T}.body.discussion.html_url, requester: {T}.body.comment.user.login }}) }}}}",
            "options": {"timeout": 120000}
        },
        "retryOnFail": True,
        "maxTries": 2,
        "waitBetweenTries": 5000
    },

    # ── Check Existing Issue (Approved) ────────────────────────────────────
    {
        "id": "node-check-issue-approved",
        "name": "Check Existing Issue (Approved)",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.3,
        "position": [480, 656],
        "parameters": {
            "method": "POST",
            "url": "https://pretended-extinct-antirust.ngrok-free.dev/check-discussion-issue",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": f"={{{{ JSON.stringify({{ repository: {T}.body.repository.full_name, discussion_node_id: {T}.body.discussion.node_id }}) }}}}",
            "options": {"timeout": 15000}
        },
        "retryOnFail": True,
        "maxTries": 3,
        "waitBetweenTries": 2000
    },

    # ── Issue Already Raised? (Approved) ──────────────────────────────────
    {
        "id": "node-approved-already-raised-check",
        "name": "Issue Already Raised? (Approved)",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [672, 656],
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                "conditions": [
                    {
                        "leftValue": "={{ $json.exists }}",
                        "operator": {"operation": "equals", "type": "boolean"},
                        "rightValue": True
                    }
                ],
                "combinator": "and"
            },
            "options": {}
        }
    },

    # ── Post "Already Raised — Raising PR" comment ─────────────────────────
    {
        "id": "node-approved-already-raised-comment",
        "name": "Post Approved Already Raised Comment",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.3,
        "position": [864, 560],
        "parameters": {
            "method": "POST",
            "url": "https://api.github.com/graphql",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Authorization", "value": "=Bearer {{ $env.GITHUB_TOKEN }}"},
                    {"name": "User-Agent", "value": "Turing-agent"}
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": f"={{{{ JSON.stringify({{ query: \"mutation($id: ID!, $body: String!) {{ addDiscussionComment(input: {{discussionId: $id, body: $body}}) {{ comment {{ id url }} }} }}\", variables: {{ id: {T}.body.discussion.node_id, body: '<!-- turing-bot-progress -->\\n\\n### ⚡ Turing-agent Fix in Progress...\\n- [x] Issue [#' + $('Check Existing Issue (Approved)').item.json.issue_number + '](' + $('Check Existing Issue (Approved)').item.json.issue_url + ') was already raised from this discussion.\\n- [x] Maintainer approval verified (@' + {T}.body.comment.user.login + ')\\n- [⏳] Initializing codebase analysis & ephemeral environment...\\n- [ ] Synthesizing solution & patch with Groq AI\\n- [ ] Committing file changes to branch\\n- [ ] Opening Pull Request' }} }}) }}}}",
            "options": {}
        },
        "retryOnFail": True,
        "maxTries": 3,
        "waitBetweenTries": 3000
    },

    # ── Merge Issue Data (so Get Default Branch Ref can continue) ──────────
    # When issue exists: we need to inject a fake "Create Repository Issue"-like item
    # We use a Set node to create {number, html_url, title} from the check result
    {
        "id": "node-set-existing-issue-data",
        "name": "Set Existing Issue Data",
        "type": "n8n-nodes-base.set",
        "typeVersion": 3.4,
        "position": [1056, 560],
        "parameters": {
            "mode": "manual",
            "duplicateItem": False,
            "assignments": {
                "assignments": [
                    {"id": "issue-number", "name": "number",   "type": "number",  "value": "={{ $('Check Existing Issue (Approved)').item.json.issue_number }}"},
                    {"id": "issue-url",    "name": "html_url", "type": "string",  "value": "={{ $('Check Existing Issue (Approved)').item.json.issue_url }}"},
                    {"id": "issue-title",  "name": "title",    "type": "string",  "value": "={{ $('Check Existing Issue (Approved)').item.json.issue_url.split('/').pop() }}"},
                    {"id": "issue-body",   "name": "body",     "type": "string",  "value": "=(issue already raised — PR path)"}
                ]
            },
            "options": {}
        }
    },
]

for node in NEW_NODES:
    if node["name"] not in existing_node_names:
        wf["nodes"].append(node)
        existing_node_names.add(node["name"])
        print(f"[workflow] Added node '{node['name']}' ✓")
    else:
        print(f"[workflow] Node '{node['name']}' already exists — skipping.")

# ---- 2c. Wire up connections ----------------------------------------------

conns = wf["connections"]

# Route by Event → RW Command? (output index 3, since 0=New Bug Report, 1=Turing Chat, 2=Maintainer Approval)
# Find route by event output index for RW
rw_output_index = next(
    i for i, v in enumerate(route_node["parameters"]["rules"]["values"])
    if v.get("outputKey") == rw_route_name
)
route_conns = conns.setdefault("Route by Event", {}).setdefault("main", [])
# Extend list to at least rw_output_index + 1
while len(route_conns) <= rw_output_index:
    route_conns.append([])
# Add RW Command? if not already wired
rw_targets = [c["node"] for c in route_conns[rw_output_index]]
if "RW Command?" not in rw_targets:
    route_conns[rw_output_index].append({"node": "RW Command?", "type": "main", "index": 0})
    print("[workflow] Wired Route by Event → RW Command? ✓")

def wire(src_name, dst_name, src_out=0, dst_in=0):
    """Add a directed edge src → dst if not already present."""
    src_conns = conns.setdefault(src_name, {}).setdefault("main", [])
    while len(src_conns) <= src_out:
        src_conns.append([])
    existing = [c["node"] for c in src_conns[src_out]]
    if dst_name not in existing:
        src_conns[src_out].append({"node": dst_name, "type": "main", "index": dst_in})
        print(f"[workflow] Wired {src_name} → {dst_name} ✓")

# RW branch
wire("RW Command?",            "Check Existing Issue (RW)")    # true  → check
wire("Check Existing Issue (RW)", "Issue Already Raised? (RW)")
wire("Issue Already Raised? (RW)", "Post RW Already Raised Comment", src_out=0)  # true  → already raised
wire("Issue Already Raised? (RW)", "Call Raise Issue Only API",       src_out=1)  # false → create

# Approved branch — reroute Maintainer Approved? true → Check Existing Issue (Approved)
# Remove old direct wire from Maintainer Approved? → Consolidate Discussion Issue
approved_true_conns = conns.get("Maintainer Approved?", {}).get("main", [[]])[0]
old_wire = next((c for c in approved_true_conns if c["node"] == "Consolidate Discussion Issue"), None)
if old_wire:
    approved_true_conns.remove(old_wire)
    print("[workflow] Removed direct Maintainer Approved? → Consolidate Discussion Issue wire ✓")

wire("Maintainer Approved?",       "Check Existing Issue (Approved)")
wire("Check Existing Issue (Approved)", "Issue Already Raised? (Approved)")

# Issue Already Raised? (Approved) = true → post comment → Set Existing Issue Data → Get Default Branch Ref
wire("Issue Already Raised? (Approved)", "Post Approved Already Raised Comment", src_out=0)
wire("Post Approved Already Raised Comment", "Set Existing Issue Data")
wire("Set Existing Issue Data",    "Get Default Branch Ref")

# Issue Already Raised? (Approved) = false → Consolidate Discussion Issue (original path)
wire("Issue Already Raised? (Approved)", "Consolidate Discussion Issue", src_out=1)

# Make sure Post Initial Progress Comment still flows from both Create Repository Issue
# and Set Existing Issue Data
wire("Set Existing Issue Data",    "Post Initial Progress Comment")

# ---- 2d. Save patched workflow --------------------------------------------
with open(WORKFLOW, "w", encoding="utf-8") as f:
    json.dump(wf, f, indent=2, ensure_ascii=False)

print("\n[workflow] Saved patched turing-agent-workflow.json ✓")
print("\n✅  All patches applied successfully.")
