import sys
sys.stdout.reconfigure(encoding="utf-8")
import json

with open("turing-agent-workflow.json", encoding="utf-8") as f:
    wf = json.load(f)

print(f"Total nodes: {len(wf['nodes'])}")
print(f"\nAll node names:")
for n in wf["nodes"]:
    print(f"  - {n['name']}")

route = next(n for n in wf["nodes"] if n["name"] == "Route by Event")
outputs = [v["outputKey"] for v in route["parameters"]["rules"]["values"]]
print(f"\nRoute by Event outputs: {outputs}")

print(f"\nConnections:")
for src, v in wf["connections"].items():
    for i, targets in enumerate(v.get("main", [])):
        for t in targets:
            print(f"  [{i}] {src} -> {t['node']}")
