import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
import json
import requests

TOKEN_PATH = r"C:\Users\yashk\.gemini\antigravity-ide\mcp_oauth_tokens.json"
TURING_TOKEN = os.getenv("GITHUB_TOKEN")

def get_mcp_token():
    with open(TOKEN_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["https://turing.app.n8n.cloud/mcp-server/http"]["token"]["access_token"]

def call_mcp(method, params=None, req_id=1):
    token = get_mcp_token()
    url = "https://turing.app.n8n.cloud/mcp-server/http"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    payload = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params or {}
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    text = resp.text
    events = text.split("\n\n")
    for ev in events:
        data_lines = [l[5:].strip() if l.startswith("data:") else l for l in ev.split("\n") if l.startswith("data:") or l.startswith(" ")]
        if data_lines:
            combined = "\n".join(data_lines)
            try:
                return json.loads(combined)
            except Exception:
                pass
    try:
        return resp.json()
    except Exception:
        return {"raw": text}

def apply_full_fix():
    workflow_id = "OLD6gJWpGfDPjae2"

    with open("turing-agent-workflow.json", encoding="utf-8") as f:
        wf = json.load(f)

    nodes_by_name = {n["name"]: n for n in wf["nodes"]}
    operations = []

    # 1. Fix Post RW Already Raised Comment - use Turing-agent PAT
    rw_comment_node = nodes_by_name["Post RW Already Raised Comment"]
    rw_comment_node["parameters"]["headerParameters"] = {
        "parameters": [
            {"name": "Authorization", "value": f"Bearer {TURING_TOKEN}"},
            {"name": "User-Agent", "value": "Turing-agent"}
        ]
    }
    operations.append({
        "type": "updateNodeParameters",
        "nodeName": "Post RW Already Raised Comment",
        "parameters": rw_comment_node["parameters"],
        "replace": True
    })

    # 2. Fix Post Approved Already Raised Comment - use Turing-agent PAT
    appr_comment_node = nodes_by_name["Post Approved Already Raised Comment"]
    appr_comment_node["parameters"]["headerParameters"] = {
        "parameters": [
            {"name": "Authorization", "value": f"Bearer {TURING_TOKEN}"},
            {"name": "User-Agent", "value": "Turing-agent"}
        ]
    }
    operations.append({
        "type": "updateNodeParameters",
        "nodeName": "Post Approved Already Raised Comment",
        "parameters": appr_comment_node["parameters"],
        "replace": True
    })

    # 3. Fix Set Existing Issue Data assignments
    set_node = nodes_by_name["Set Existing Issue Data"]
    set_node["parameters"]["assignments"]["assignments"] = [
        {
            "id": "issue-number",
            "name": "number",
            "type": "number",
            "value": "={{ $('Check Existing Issue (Approved)').item.json.issue_number }}"
        },
        {
            "id": "issue-url",
            "name": "html_url",
            "type": "string",
            "value": "={{ $('Check Existing Issue (Approved)').item.json.issue_url }}"
        },
        {
            "id": "issue-title",
            "name": "title",
            "type": "string",
            "value": "={{ $('Check Existing Issue (Approved)').item.json.issue_title || ('Issue #' + $('Check Existing Issue (Approved)').item.json.issue_number) }}"
        },
        {
            "id": "issue-body",
            "name": "body",
            "type": "string",
            "value": "={{ $('Check Existing Issue (Approved)').item.json.issue_body || '' }}"
        }
    ]
    operations.append({
        "type": "updateNodeParameters",
        "nodeName": "Set Existing Issue Data",
        "parameters": set_node["parameters"],
        "replace": True
    })

    # 4. Fix Call Resolve Issue API - support existing issue path
    resolve_node = nodes_by_name["Call Resolve Issue API"]
    resolve_body_code = """={{ (() => {
  const trigger = ($('GitHub Discussion Events').isExecuted ? $('GitHub Discussion Events') : $('GitHub Webhook (Direct URL)')).item.json;
  const issue = $('Create Repository Issue').isExecuted ? $('Create Repository Issue').item.json : $('Set Existing Issue Data').item.json;
  const progressComment = $('Post Initial Progress Comment').isExecuted ? $('Post Initial Progress Comment').item.json : $('Post Approved Already Raised Comment').item.json;
  const commentId = progressComment && progressComment.data && progressComment.data.addDiscussionComment && progressComment.data.addDiscussionComment.comment ? progressComment.data.addDiscussionComment.comment.id : null;
  const filesToModify = $('Consolidate Discussion Issue').isExecuted ? ($('Consolidate Discussion Issue').item.json.files_to_modify || []) : [];
  return JSON.stringify({
    issue_title: issue.title,
    issue_body: issue.body,
    issue_number: issue.number,
    repo_full_name: trigger.body.repository.full_name,
    base_tree_sha: $('Get Base Commit').item.json.tree.sha,
    base_commit_sha: $('Get Base Commit').item.json.sha,
    discussion_url: trigger.body.discussion.html_url,
    author: trigger.body.discussion.user.login,
    issue_url: issue.html_url,
    progress_comment_id: commentId,
    files_to_modify: filesToModify
  });
})() }}"""
    resolve_node["parameters"]["jsonBody"] = resolve_body_code
    operations.append({
        "type": "updateNodeParameters",
        "nodeName": "Call Resolve Issue API",
        "parameters": resolve_node["parameters"],
        "replace": True
    })

    # 5. Fix Open Pull Request - support existing issue path
    pr_node = nodes_by_name["Open Pull Request"]
    pr_body_code = pr_node["parameters"]["jsonBody"]
    # Replace const issueNode = $('Create Repository Issue').item.json;
    old_pr_line = "const issueNode = $('Create Repository Issue').item.json;"
    new_pr_line = "const issueNode = $('Create Repository Issue').isExecuted ? $('Create Repository Issue').item.json : $('Set Existing Issue Data').item.json;"
    if old_pr_line in pr_body_code:
        pr_node["parameters"]["jsonBody"] = pr_body_code.replace(old_pr_line, new_pr_line)
        operations.append({
            "type": "updateNodeParameters",
            "nodeName": "Open Pull Request",
            "parameters": pr_node["parameters"],
            "replace": True
        })
        print("Updated Open Pull Request code to support both paths ✓")

    # 6. Fix Update Final Progress Comment - support existing issue path
    final_node = nodes_by_name["Update Final Progress Comment"]
    final_body_code = final_node["parameters"]["jsonBody"]
    old_final_snippet = """  const issue = $('Create Repository Issue').item.json;
  const trigger = ($('GitHub Discussion Events').isExecuted ? $('GitHub Discussion Events') : $('GitHub Webhook (Direct URL)')).item.json;
  const author = trigger.body.discussion.user.login;
  const commentId = $('Post Initial Progress Comment').item.json.data.addDiscussionComment.comment.id;"""
    new_final_snippet = """  const issue = $('Create Repository Issue').isExecuted ? $('Create Repository Issue').item.json : $('Set Existing Issue Data').item.json;
  const trigger = ($('GitHub Discussion Events').isExecuted ? $('GitHub Discussion Events') : $('GitHub Webhook (Direct URL)')).item.json;
  const author = trigger.body.discussion.user.login;
  const progressNode = $('Post Initial Progress Comment').isExecuted ? $('Post Initial Progress Comment').item.json : $('Post Approved Already Raised Comment').item.json;
  const commentId = progressNode && progressNode.data && progressNode.data.addDiscussionComment && progressNode.data.addDiscussionComment.comment ? progressNode.data.addDiscussionComment.comment.id : null;"""
    if old_final_snippet in final_body_code:
        final_node["parameters"]["jsonBody"] = final_body_code.replace(old_final_snippet, new_final_snippet)
        operations.append({
            "type": "updateNodeParameters",
            "nodeName": "Update Final Progress Comment",
            "parameters": final_node["parameters"],
            "replace": True
        })
        print("Updated Update Final Progress Comment code to support both paths ✓")

    # 7. Disconnect Set Existing Issue Data -> Post Initial Progress Comment if present
    set_conns = wf["connections"].get("Set Existing Issue Data", {}).get("main", [[]])[0]
    bad_wire = next((c for c in set_conns if c["node"] == "Post Initial Progress Comment"), None)
    if bad_wire:
        set_conns.remove(bad_wire)
        operations.append({
            "type": "removeConnection",
            "source": "Set Existing Issue Data",
            "target": "Post Initial Progress Comment",
            "sourceIndex": 0,
            "targetIndex": 0,
            "connectionType": "main"
        })
        print("Removed unwanted wire: Set Existing Issue Data -> Post Initial Progress Comment ✓")

    # Save to local workflow file
    with open("turing-agent-workflow.json", "w", encoding="utf-8") as f:
        json.dump(wf, f, indent=2, ensure_ascii=False)
    print("Saved local turing-agent-workflow.json ✓")

    # Send operations to n8n Cloud via MCP
    print(f"\nSubmitting {len(operations)} operations to n8n Cloud...")
    res = call_mcp("tools/call", {
        "name": "update_workflow",
        "arguments": {
            "workflowId": workflow_id,
            "operations": operations,
            "versionName": "Fix Turing bot token and PR execution path for existing issues",
            "versionDescription": "Updated Authorization to use Turing-agent PAT in all comments and updated expressions in Call Resolve Issue API, Open Pull Request, and Update Final Progress Comment to support the existing issue path."
        }
    })
    print("Update result:", json.dumps(res, indent=2)[:600])

    print("\nPublishing workflow...")
    pub_res = call_mcp("tools/call", {
        "name": "publish_workflow",
        "arguments": {
            "workflowId": workflow_id
        }
    })
    print("Publish result:", json.dumps(pub_res, indent=2))

if __name__ == "__main__":
    apply_full_fix()
