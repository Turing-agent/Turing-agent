import sys
sys.path.insert(0, '.')
from scripts.n8n_mcp_client import call_mcp
import json

res = call_mcp('tools/call', {'name': 'get_workflow_details', 'arguments': {'workflowId': 'OLD6gJWpGfDPjae2'}})
text = res.get('result', {}).get('content', [{}])[0].get('text', '')
wf = json.loads(text)['workflow']

for n in wf['nodes']:
    params = n.get('parameters', {})
    headers = params.get('headerParameters', {}).get('parameters', [])
    for h in headers:
        if h.get('name') == 'Authorization':
            val = h.get('value', '')
            print(f"{n['name']}: {val[:30]}")

