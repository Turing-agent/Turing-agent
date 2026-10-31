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

def patch_and_sync():
    workflow_id = "OLD6gJWpGfDPjae2"

    with open("turing-agent-workflow.json", encoding="utf-8") as f:
        local_wf = json.load(f)

    ngrok_nodes = [
        "Check Existing Issue (RW)",
        "Call Raise Issue Only API",
        "Check Existing Issue (Approved)",
        "Consolidate Discussion Issue",
        "Call Resolve Issue API",
        "Triage Discussion with TinyFish",
        "Call Turing Chat API"
    ]

    header_params = {
        "parameters": [
            {"name": "ngrok-skip-browser-warning", "value": "true"},
            {"name": "User-Agent", "value": "Turing-agent"}
        ]
    }

    operations = []

    # 1. Update ngrok nodes with sendHeaders and headerParameters
    for node in local_wf["nodes"]:
        if node["name"] in ngrok_nodes:
            node["parameters"]["sendHeaders"] = True
            node["parameters"]["headerParameters"] = header_params
            operations.append({
                "type": "updateNodeParameters",
                "nodeName": node["name"],
                "parameters": node["parameters"],
                "replace": True
            })
            print(f"Added ngrok headers to node: {node['name']}")

    # 2. Add connection from RW Command? -> Acknowledge with Eyes Reaction
    rw_conns = local_wf["connections"].setdefault("RW Command?", {}).setdefault("main", [[]])
    existing_targets = [c["node"] for c in rw_conns[0]]
    if "Acknowledge with Eyes Reaction" not in existing_targets:
        rw_conns[0].append({"node": "Acknowledge with Eyes Reaction", "type": "main", "index": 0})
        operations.append({
            "type": "addConnection",
            "source": "RW Command?",
            "target": "Acknowledge with Eyes Reaction",
            "sourceIndex": 0,
            "targetIndex": 0,
            "connectionType": "main"
        })
        print("Added connection: RW Command? -> Acknowledge with Eyes Reaction")

    # Save local workflow
    with open("turing-agent-workflow.json", "w", encoding="utf-8") as f:
        json.dump(local_wf, f, indent=2, ensure_ascii=False)
    print("Saved local turing-agent-workflow.json")

    # Sync to n8n cloud
    print(f"Applying {len(operations)} operations to n8n cloud...")
    res = call_mcp("tools/call", {
        "name": "update_workflow",
        "arguments": {
            "workflowId": workflow_id,
            "operations": operations,
            "versionName": "Fix ngrok headers and wire Eyes reaction on RW",
            "versionDescription": "Added ngrok-skip-browser-warning header to all backend HTTP nodes and connected Eyes reaction to RW command."
        }
    })
    print("Update result:", json.dumps(res, indent=2)[:500])

    print("Publishing workflow...")
    pub_res = call_mcp("tools/call", {
        "name": "publish_workflow",
        "arguments": {
            "workflowId": workflow_id
        }
    })
    print("Publish result:", json.dumps(pub_res, indent=2))

if __name__ == "__main__":
    patch_and_sync()
