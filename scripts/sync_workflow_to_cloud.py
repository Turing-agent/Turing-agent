import sys
sys.stdout.reconfigure(encoding="utf-8")
import requests, json

TOKEN_PATH = r"C:\Users\yashk\.gemini\antigravity-ide\mcp_oauth_tokens.json"

def get_token():
    with open(TOKEN_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["https://turing.app.n8n.cloud/mcp-server/http"]["token"]["access_token"]

def call_mcp(method, params=None, req_id=1):
    token = get_token()
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

def sync_workflow():
    workflow_id = "OLD6gJWpGfDPjae2"

    with open("turing-agent-workflow.json", encoding="utf-8") as f:
        local_wf = json.load(f)

    local_nodes_by_name = {n["name"]: n for n in local_wf["nodes"]}
    route_node = local_nodes_by_name["Route by Event"]

    nodes_to_add = [
        "RW Command?",
        "Check Existing Issue (RW)",
        "Issue Already Raised? (RW)",
        "Post RW Already Raised Comment",
        "Call Raise Issue Only API",
        "Check Existing Issue (Approved)",
        "Issue Already Raised? (Approved)",
        "Post Approved Already Raised Comment",
        "Set Existing Issue Data"
    ]

    operations = []

    # 1. Update Route by Event parameters to include 4th branch (RW Command)
    operations.append({
        "type": "updateNodeParameters",
        "nodeName": "Route by Event",
        "parameters": route_node["parameters"],
        "replace": True
    })

    # 2. Add the 9 new nodes
    for name in nodes_to_add:
        n = local_nodes_by_name[name]
        node_payload = {
            "name": n["name"],
            "type": n["type"],
            "typeVersion": n["typeVersion"],
            "position": n["position"],
            "parameters": n.get("parameters", {})
        }
        if "credentials" in n:
            node_payload["credentials"] = n["credentials"]
        operations.append({
            "type": "addNode",
            "node": node_payload
        })

    # 3. Settings for nodes if any (onError)
    operations.append({
        "type": "setNodeSettings",
        "nodeName": "Post RW Already Raised Comment",
        "settings": {
            "onError": "continueRegularOutput"
        }
    })

    # 4. Remove old direct wire Maintainer Approved? -> Consolidate Discussion Issue
    operations.append({
        "type": "removeConnection",
        "source": "Maintainer Approved?",
        "target": "Consolidate Discussion Issue",
        "sourceIndex": 0,
        "targetIndex": 0,
        "connectionType": "main"
    })

    # 5. Add new connections
    new_connections = [
        # Route by Event -> RW Command? (output index 3)
        ("Route by Event", "RW Command?", 3, 0),
        # RW branch
        ("RW Command?", "Check Existing Issue (RW)", 0, 0),
        ("Check Existing Issue (RW)", "Issue Already Raised? (RW)", 0, 0),
        ("Issue Already Raised? (RW)", "Post RW Already Raised Comment", 0, 0),
        ("Issue Already Raised? (RW)", "Call Raise Issue Only API", 1, 0),
        # Approved branch
        ("Maintainer Approved?", "Check Existing Issue (Approved)", 0, 0),
        ("Check Existing Issue (Approved)", "Issue Already Raised? (Approved)", 0, 0),
        ("Issue Already Raised? (Approved)", "Post Approved Already Raised Comment", 0, 0),
        ("Issue Already Raised? (Approved)", "Consolidate Discussion Issue", 1, 0),
        ("Post Approved Already Raised Comment", "Set Existing Issue Data", 0, 0),
        ("Set Existing Issue Data", "Get Default Branch Ref", 0, 0),
        ("Set Existing Issue Data", "Post Initial Progress Comment", 0, 0)
    ]

    for src, tgt, s_idx, t_idx in new_connections:
        operations.append({
            "type": "addConnection",
            "source": src,
            "target": tgt,
            "sourceIndex": s_idx,
            "targetIndex": t_idx,
            "connectionType": "main"
        })

    print(f"Submitting {len(operations)} operations to update workflow {workflow_id}...")
    res = call_mcp("tools/call", {
        "name": "update_workflow",
        "arguments": {
            "workflowId": workflow_id,
            "operations": operations,
            "versionName": "Add RW Command and Duplicate Prevention",
            "versionDescription": "Added RW command branch with duplicate check, and duplicate check on approved maintainer command."
        }
    })

    print("Result:", json.dumps(res, indent=2))

    # Next, publish the workflow to make sure it's active
    print("\nPublishing workflow...")
    pub_res = call_mcp("tools/call", {
        "name": "publish_workflow",
        "arguments": {
            "workflowId": workflow_id
        }
    })
    print("Publish Result:", json.dumps(pub_res, indent=2))

if __name__ == "__main__":
    sync_workflow()
