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

def refresh_oauth_token():
    with open(TOKEN_PATH, encoding="utf-8") as f:
        data = json.load(f)
    entry = data["https://turing.app.n8n.cloud/mcp-server/http"]
    refresh_tok = entry["token"]["refresh_token"]
    client_id = entry["client_id"]
    token_url = entry["token_url"]
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_tok,
        "client_id": client_id
    }
    resp = requests.post(token_url, data=payload, timeout=15)
    if resp.ok:
        entry["token"] = resp.json()
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print("[mcp_client] Token refreshed successfully ✓")
        return entry["token"]["access_token"]
    else:
        print("[mcp_client] Failed to refresh token:", resp.text)
        return None

def call_mcp(method, params=None, req_id=1, allow_retry=True):
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

    if "JWT Verification Failed" in text or resp.status_code == 401:
        if allow_retry:
            print("[mcp_client] Access token expired. Auto-refreshing...")
            new_tok = refresh_oauth_token()
            if new_tok:
                return call_mcp(method, params, req_id, allow_retry=False)

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
