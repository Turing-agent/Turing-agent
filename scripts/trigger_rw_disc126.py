import sys
sys.stdout.reconfigure(encoding="utf-8")
import requests, os, json

token = os.getenv("GITHUB_TOKEN")
# Also check .env
if not token:
    with open(".env") as f:
        for line in f:
            if line.startswith("GITHUB_TOKEN="):
                token = line.strip().split("=", 1)[1]

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "Turing-agent"
}

query = """
query {
  repository(owner: "YASHK-arch", name: "eventyay_Sandbox") {
    discussion(number: 126) {
      id
      number
      title
      body
      url
      comments(last: 10) {
        nodes {
          id
          body
          author { login }
        }
      }
    }
  }
}
"""

res = requests.post("https://api.github.com/graphql", json={"query": query}, headers=headers)
data = res.json()
disc = data.get("data", {}).get("repository", {}).get("discussion")
print(f"Discussion #{disc['number']}: {disc['title']}")
print(f"Node ID: {disc['id']}")
print(f"Comments count: {len(disc['comments']['nodes'])}")

rw_comment = None
for c in disc['comments']['nodes']:
    print(f"  Comment by {c['author']['login']}: {repr(c['body'][:60])}")
    if c['body'].strip() == "RW":
        rw_comment = c

if rw_comment:
    print(f"\nFound RW comment: ID={rw_comment['id']}")
    # 1. Add eyes reaction
    eye_mut = """
    mutation($id: ID!) {
      addReaction(input: {subjectId: $id, content: EYES}) {
        reaction { content }
      }
    }
    """
    eye_res = requests.post("https://api.github.com/graphql", json={"query": eye_mut, "variables": {"id": rw_comment['id']}}, headers=headers)
    print("Eyes reaction result:", eye_res.json())

    # 2. Call /raise-issue-only
    payload = {
        "repository": "YASHK-arch/eventyay_Sandbox",
        "discussion_number": disc['number'],
        "discussion_title": disc['title'],
        "discussion_body": disc['body'],
        "discussion_node_id": disc['id'],
        "discussion_url": disc['url'],
        "requester": rw_comment['author']['login']
    }
    print("\nCalling /raise-issue-only...")
    r = requests.post("http://localhost:8000/raise-issue-only", json=payload, timeout=60)
    print("Status:", r.status_code)
    print("Result:", r.text)
