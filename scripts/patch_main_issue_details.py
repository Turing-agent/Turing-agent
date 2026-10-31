import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

target = """        for comment in nodes:
            body = comment.get("body", "")
            m = re.search(r'<!-- turing-raised-issue #(\d+) (https?://\S+) -->', body)
            if m:
                return {
                    "exists": True,
                    "issue_number": int(m.group(1)),
                    "issue_url": m.group(2)
                }
        return {"exists": False, "issue_number": None, "issue_url": None}"""

replacement = """        for comment in nodes:
            body = comment.get("body", "")
            m = re.search(r'<!-- turing-raised-issue #(\d+) (https?://\S+) -->', body)
            if m:
                issue_num = int(m.group(1))
                issue_url = m.group(2)
                issue_title = ""
                issue_body = ""
                try:
                    i_res = requests.get(
                        f"https://api.github.com/repos/{payload.repository}/issues/{issue_num}",
                        headers=headers, timeout=10
                    )
                    if i_res.ok:
                        i_data = i_res.json()
                        issue_title = i_data.get("title", "")
                        issue_body = i_data.get("body", "")
                except Exception:
                    pass
                return {
                    "exists": True,
                    "issue_number": issue_num,
                    "issue_url": issue_url,
                    "issue_title": issue_title,
                    "issue_body": issue_body
                }
        return {"exists": False, "issue_number": None, "issue_url": None, "issue_title": None, "issue_body": None}"""

content_norm = content.replace("\r\n", "\n")
target_norm = target.replace("\r\n", "\n")
replacement_norm = replacement.replace("\r\n", "\n")

if target_norm in content_norm:
    content_norm = content_norm.replace(target_norm, replacement_norm, 1)
    with open("main.py", "w", encoding="utf-8") as f:
        f.write(content_norm)
    print("main.py successfully updated!")
else:
    print("Target not found in main.py!")
