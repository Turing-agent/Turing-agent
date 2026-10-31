"""
Tasks package containing core modular agent capabilities for Turing-Agent:
- vision_module: Multimodal bug reproduction & visual regression inspection
- docker_provisioner: Ephemeral Docker sandbox environment provisioning
- agent_runner: Autonomous investigation pipeline & reproduction runner
- analyzer: Static codebase analysis & dependency candidate extraction
- tinyfish_correlator: Groq + TinyFish cross-issue correlation & component intelligence
- discussion_consolidator: Synthesizes discussions into clean GitHub issues
- turing_qa: Intent-driven Q&A & live TinyFish investigation endpoint
"""

import sys
from pathlib import Path

# Ensure tasks directory is in sys.path so modules can import each other seamlessly
_PKG_DIR = Path(__file__).resolve().parent
if str(_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(_PKG_DIR))

