import sys
sys.stdout.reconfigure(encoding="utf-8")
import json
import requests

TOKEN_PATH = r"C:\Users\yashk\.gemini\antigravity-ide\mcp_oauth_tokens.json"

def get_token():
    with open(TOKEN_PATH, encoding="utf-8") as f:
        data = json.load(f)
    entry = data["https://turing.app.n8n.cloud/mcp-server/http"]
    return entry["token"]["access_token"]

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

if __name__ == "__main__":
    res = call_mcp("tools/list")
    tools = res.get("result", {}).get("tools", [])
    print(f"Found {len(tools)} tools")
