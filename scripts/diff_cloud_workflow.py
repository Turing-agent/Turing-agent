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

def get_current_cloud_workflow(workflow_id="OLD6gJWpGfDPjae2"):
    res = call_mcp("tools/call", {"name": "get_workflow_details", "arguments": {"workflowId": workflow_id}})
    content = res["result"]["content"][0]["text"]
    return json.loads(content)["workflow"]

if __name__ == "__main__":
    cloud_wf = get_current_cloud_workflow()
    print("Cloud workflow:", cloud_wf["name"], f"({cloud_wf['id']})")
    print(f"Cloud nodes ({len(cloud_wf['nodes'])}):")
    cloud_node_names = {n["name"] for n in cloud_wf["nodes"]}
    for name in sorted(cloud_node_names):
        print("  -", name)

    with open("turing-agent-workflow.json", encoding="utf-8") as f:
        local_wf = json.load(f)

    local_node_names = {n["name"] for n in local_wf["nodes"]}
    print(f"\nLocal nodes ({len(local_wf['nodes'])}):")
    for name in sorted(local_node_names):
        print("  -", name)

    missing_in_cloud = local_node_names - cloud_node_names
    extra_in_cloud = cloud_node_names - local_node_names
    print(f"\nNodes to add to cloud ({len(missing_in_cloud)}):", missing_in_cloud)
    print(f"Extra nodes in cloud ({len(extra_in_cloud)}):", extra_in_cloud)
