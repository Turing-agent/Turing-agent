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
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    text = resp.text
    for line in text.splitlines():
        if line.startswith("data:"):
            data_str = line[len("data:"):].strip()
            return json.loads(data_str)
    try:
        return resp.json()
    except Exception:
        return {"raw": text}

if __name__ == "__main__":
    res = call_mcp("tools/list")
    tools = res.get("result", {}).get("tools", [])
    print(f"Found {len(tools)} tools:")
    for t in tools:
        print(f"  - {t['name']}: {t.get('description', '')[:80]}")
