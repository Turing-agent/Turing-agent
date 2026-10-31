import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
import requests, json

token = os.getenv("GITHUB_TOKEN")
headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "Turing-agent"
}
body = "<!-- turing-bot -->\n\n⚠️ **Issue already raised.** Issue [#128](https://github.com/YASHK-arch/eventyay_Sandbox/issues/128) was previously created from this discussion. To trigger an automated PR, comment `approved`."

query = """
mutation($id: ID!, $body: String!) {
  addDiscussionComment(input: {discussionId: $id, body: $body}) {
    comment { id url author { login } }
  }
}
"""

r = requests.post("https://api.github.com/graphql", json={"query": query, "variables": {"id": "D_kwDOVc0FZc4Aqsv6", "body": body}}, headers=headers)
print("Result:", r.json())
