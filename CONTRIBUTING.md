# Contributing to Turing-Agent 🐟

Welcome to the **Turing-Agent** community! We are thrilled to have you here, especially if you are joining us during an **Open Source Community (OSC) event, hackathon, or contributor sprint**.

**Our Mission:** Automate the entire journey from **raw end-user complaints (e.g. in Jira) to validated, discussed, and implementation-ready GitHub issues**.

This guide provides everything you need to get set up, explore the codebase, pick up a task, and submit your first pull request.

---

## 📑 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can You Contribute?](#how-can-you-contribute)
- [Zero-Barrier Local Setup (Mock Mode)](#zero-barrier-local-setup-mock-mode)
- [Development Workflow](#development-workflow)
- [Commit Message Guidelines](#commit-message-guidelines)
- [Pull Request Checklist](#pull-request-checklist)
- [Community & Getting Help](#community--getting-help)

---

## Code of Conduct

We are committed to providing a welcoming, inclusive, and harassment-free experience for everyone. Please be kind, constructive, respectful, and supportive to fellow contributors and maintainers.

---

## How Can You Contribute?

Whether you are an AI engineer, backend developer, frontend enthusiast, or technical writer, there is a place for you:

### 1. 📋 Issue Synthesis & Template Intelligence
- **Issue Templates**: Teach `tasks/discussion_consolidator.py` to parse repository `.github/ISSUE_TEMPLATE/*.md` files and output issues strictly conforming to the project's format.
- **Scope Extraction**: Improve prompts in `discussion_consolidator.py` to accurately capture `files_to_modify`, acceptance criteria checklists, and agreed technical decisions.
- **Patch Proposals**: Improve suggested code snippets and unified diff generation for proposed solutions.

### 2. 🌉 Multi-Platform Complaint Intake & Scraping
- **Platform Adapters**: Help expand beyond Jira by building adapters for **Linear**, **Zendesk**, **GitLab**, or **GitHub Discussions**.
- **TinyFish Ingestion**: Refine queue scraping logic in `tasks/jira_integration.py` and `tasks/tinyfish_correlator.py` to extract raw customer complaints cleanly.

### 3. 🔍 Codebase Correlation & Deduplication
- **AST Component Mapping**: Correlate user symptoms to exact repository files, components, and line ranges in `tasks/analyzer.py`.
- **Duplicate Detection**: Enhance cross-issue semantic search in `tasks/tinyfish_correlator.py` to check whether open issues or merged PRs already address the complaint.

### 4. 📊 QA Dashboard & Visual Interface
- **React Frontend**: Enhance `frontend/src/components/GitTimeSeriesDashboard.jsx` with a dedicated "Complaint Intake Queue" view.
- **Interactive QA**: Allow maintainers to review triage notes and click "Approve & Raise GitHub Issue" directly from the dashboard.
- **Git DAG**: Improve swimlane visualization and incident timeline mapping.

### 5. 🧪 Testing, DevOps & Documentation
- **Test Suite**: Add test cases to `scripts/test_jira_flow.py` and unit tests covering malformed complaints or edge cases.
- **Documentation**: Write maintainer guides, create demo walkthroughs, and improve installation guides.

---

## Zero-Barrier Local Setup (Mock Mode)

You do **not** need paid API keys or cloud accounts to develop on Turing-Agent!

### 1. Fork & Clone
```bash
git clone https://github.com/YOUR_USERNAME/Turing-agent.git
cd Turing-agent
```

### 2. Python Environment
```bash
python -m venv .venv

# On Linux / macOS:
source .venv/bin/activate

# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 3. Configure `.env` for Mock Mode
Create a `.env` file in the root directory:
```dotenv
# Groq LLM (Free instant key from https://console.groq.com)
GROQ_API_KEY=gsk_your_free_groq_key
GROQ_MODEL=openai/gpt-oss-120b

# TinyFish (Enable mock mode for zero-cost local development)
TINYFISH_MOCK=true
TINYFISH_API_KEY=mock-dev-key

# GitHub Token (Optional for read-only local testing; required for live issue creation)
GITHUB_TOKEN=ghp_your_github_token
```

### 4. Start the Backend
```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
Open **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)** to test any endpoint interactively!

### 5. Start the React Frontend
```bash
npm install
npm run dev
```
Open **[http://localhost:5173](http://localhost:5173)** to explore the Git DAG dashboard.

### 6. Run the Test Suite
```bash
python scripts/test_jira_flow.py
```

---

## Development Workflow

1. **Pick or create an issue**: Check open issues or discuss your idea with a maintainer.
2. **Create a topic branch**:
   ```bash
   git checkout -b feat/your-feature-name
   ```
3. **Write clean, surgical code**:
   - Keep changes focused on the task at hand.
   - Follow PEP 8 for Python and standard ES6+ / JSX conventions for React.
4. **Test your changes**:
   - Verify Python endpoints via `/docs` or by running `python scripts/test_jira_flow.py`.
   - Build the frontend to verify there are no compilation errors:
     ```bash
     npm run build
     ```

---

## Commit Message Guidelines

We follow standard Conventional Commits:
- `feat: add support for parsing issue templates in consolidator`
- `fix: handle empty description in raw complaint triage`
- `docs: update setup guide for hackathon contributors`
- `refactor: modularize Jira ticket scraper`
- `test: add test for duplicate issue detection`

---

## Pull Request Checklist

Before submitting your PR:
- [ ] My code follows the repository's coding style.
- [ ] I have tested my changes locally using mock mode or real APIs.
- [ ] If I added new endpoints or options, I updated the relevant documentation.
- [ ] My commits are clear and well-scoped.
- [ ] The PR description clearly explains the **motivation**, **changes made**, and **how to test**.

---

## Community & Getting Help

- 💬 Have questions or stuck on a setup issue during the event? Ask a maintainer directly or open an issue.
- 🐛 Found a bug? Open an issue with clear steps to reproduce.

Thank you for helping bridge the gap between user complaints and engineering backlogs! Happy hacking! 🐟
