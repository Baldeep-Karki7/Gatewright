import os

SYSTEM = "You are a coding agent working in the user's workspace.Inspect files before answering questions about them. After writing code, run it to verify it works. If it fails, read the error and fix it. Be concise. Make the smallest edit that works"
ROOT = os.path.realpath('.')
HISTORY = 'history.json'

GIT_IGNORE_CONTENT = """# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# Environments
.venv/
venv/
ENV/

# IDEs
.vscode/
.idea/
.ruff_cache/

# FILE
.history.json
.agent.log
"""