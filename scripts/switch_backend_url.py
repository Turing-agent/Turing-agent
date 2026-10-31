"""
switch_backend_url.py
=====================
Switches the backend URL in both local turing-agent-workflow.json
and n8n Cloud (via MCP) from ngrok to your production deployed URL.

Usage:
    python scripts/switch_backend_url.py https://turing-agent-backend.onrender.com
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")
import os
import json
from scripts.n8n_mcp_client import call_mcp

OLD_DOMAIN = "https://pretended-extinct-antirust.ngrok-free.dev"

def switch_url(new_url: str):
    new_url = new_url.rstrip("/")
    workflow_id = "OLD6gJWpGfDPjae2"

    print(f"Switching backend URL from {OLD_DOMAIN} to {new_url}...")

    # 1. Update local file
    with open("turing-agent-workflow.json", "r", encoding="utf-8") as f:
        wf = json.load(f)

    nodes_to_update = []
    for node in wf["nodes"]:
        url = node.get("parameters", {}).get("url", "")
        if OLD_DOMAIN in url:
            node["parameters"]["url"] = url.replace(OLD_DOMAIN, new_url)
            nodes_to_update.append(node["name"])

    with open("turing-agent-workflow.json", "w", encoding="utf-8") as f:
        json.dump(wf, f, indent=2, ensure_ascii=False)
    print(f"Updated {len(nodes_to_update)} nodes in local turing-agent-workflow.json ✓")

    # 2. Update cloud workflow via MCP
    res = call_mcp("tools/call", {"name": "get_workflow_details", "arguments": {"workflowId": workflow_id}})
    cloud_wf = json.loads(res["result"]["content"][0]["text"])["workflow"]
    cloud_nodes = {n["name"]: n for n in cloud_wf["nodes"]}

    operations = []
    for name in nodes_to_update:
        if name in cloud_nodes:
            cn = cloud_nodes[name]
            url = cn.get("parameters", {}).get("url", "")
            if OLD_DOMAIN in url:
                cn["parameters"]["url"] = url.replace(OLD_DOMAIN, new_url)
                operations.append({
                    "type": "updateNodeParameters",
                    "nodeName": name,
                    "parameters": cn["parameters"],
                    "replace": True
                })

    if operations:
        print(f"Submitting {len(operations)} updates to n8n Cloud...")
        upd_res = call_mcp("tools/call", {
            "name": "update_workflow",
            "arguments": {
                "workflowId": workflow_id,
                "operations": operations,
                "versionName": f"Switch backend to {new_url}",
                "versionDescription": f"Switched all 7 backend HTTP nodes from ngrok tunnel to production deployment {new_url}"
            }
        })
        print("Update result:", json.dumps(upd_res, indent=2)[:400])

        print("Publishing workflow on n8n Cloud...")
        pub_res = call_mcp("tools/call", {
            "name": "publish_workflow",
            "arguments": {"workflowId": workflow_id}
        })
        print("Publish result:", json.dumps(pub_res, indent=2))
        print(f"\n🎉 Success! n8n Cloud is now connected to {new_url} 24/7!")
    else:
        print("No cloud nodes matched old ngrok URL.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/switch_backend_url.py <NEW_PRODUCTION_URL>")
        sys.exit(1)
    switch_url(sys.argv[1])
