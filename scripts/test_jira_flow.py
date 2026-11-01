"""
test_jira_flow.py
=================
Verifies Jira triage (Internal Note) and Jira RW command (source: Jira label on GitHub).
"""

import os
import sys

# Ensure utf-8 stdout on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Ensure repository root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from tasks.jira_integration import triage_jira_ticket, handle_jira_comment, scrape_jira_open_queue
from tasks.discussion_consolidator import consolidate_discussion_to_issue


def test_jira_queue():
    print("1. Testing Jira Queue Scraping...")
    tickets = scrape_jira_open_queue(limit=2)
    assert len(tickets) > 0, "Expected at least 1 ticket"
    print(f"  ✓ Found {len(tickets)} queue tickets: {[t['key'] for t in tickets]}")


def test_jira_triage():
    print("2. Testing Jira Triage (Internal Note)...")
    res = triage_jira_ticket(
        ticket_key="EVY-104",
        summary="Actions dropdown menu in Users table is clipped by container overflow",
        description="Container has overflow: hidden so actions menu is clipped.",
        reporter="test.user",
        repository="eventyaysandbox/eventyay_Sandbox"
    )
    assert res["status"] == "success"
    assert res["is_internal"] is True
    assert "🔒 **[Turing Internal Maintainer Review" in res["internal_note"]
    print("  ✓ Triage generated Internal Note successfully.")


def test_jira_rw_command():
    print("3. Testing Jira RW command (Issue creation with 'source: Jira' label)...")
    old_token = os.environ.get("GITHUB_TOKEN")
    try:
        # Avoid creating duplicate test issues on remote repo during test suite runs
        os.environ["GITHUB_TOKEN"] = ""
        res = handle_jira_comment(
            ticket_key="EVY-104",
            comment_body="RW",
            comment_author="lead.maintainer",
            ticket_summary="Actions dropdown menu in Users table is clipped by container overflow",
            ticket_description="Container has overflow: hidden so actions menu is clipped.",
            repository="eventyaysandbox/eventyay_Sandbox"
        )
        assert res["status"] == "success"
        assert res["action"] == "issue_created"
        assert "source: Jira" in res["labels"]
        assert "ready-for-work" in res["labels"]
        print(f"  ✓ Issue created with labels: {res['labels']}")
    finally:
        if old_token is not None:
            os.environ["GITHUB_TOKEN"] = old_token


def test_discussion_source_label():
    print("4. Testing standard GitHub Discussion consolidation (label: 'source: GitHub Discussion')...")
    res = consolidate_discussion_to_issue(
        repo="eventyaysandbox/eventyay_Sandbox",
        discussion_number=77,
        discussion_title="Creating question without products returns 500",
        discussion_body="Missing products array causes TypeError",
        approver="maintainer",
        source="GitHub Discussion"
    )
    assert "source: GitHub Discussion" in res["labels"]
    print(f"  ✓ Discussion labels: {res['labels']}")


if __name__ == "__main__":
    test_jira_queue()
    test_jira_triage()
    test_jira_rw_command()
    test_discussion_source_label()
    print("\n🎉 ALL JIRA & DISCUSSION WORKFLOW TESTS PASSED!")
