import sys
sys.stdout.reconfigure(encoding="utf-8")
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.n8n_mcp_client import call_mcp
import json

for eid in ['416', '417', '418', '419']:
    res = call_mcp('tools/call', {'name': 'get_workflow_execution', 'arguments': {'workflowId': 'OLD6gJWpGfDPjae2', 'executionId': eid, 'includeData': True}})
    text = res.get('result', {}).get('content', [{}])[0].get('text', '')
    data = json.loads(text)
    err = data.get('data', {}).get('resultData', {}).get('error', {})
    run_data = data.get('data', {}).get('resultData', {}).get('runData', {})
    status = data.get('execution', {}).get('status')
    print(f"\n=== EXECUTION {eid} (status: {status}) ===")
    print('Nodes executed:', list(run_data.keys()))
    if err:
        print('Error message:', err.get('message'))
        print('Error node:', err.get('node', {}).get('name'))
        print('Description:', repr(err.get('description', ''))[:400])
