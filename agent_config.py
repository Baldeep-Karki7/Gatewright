import hashlib
import os


def data_dir(root):
    """Return the workspace's data folder under ~/.harness, creating it if needed"""

    base = os.path.expanduser('~/.harness')
    key = hashlib.sha256(root.encode()).hexdigest()[:12]
    name = os.path.basename(root)

    path = os.path.join(base, "projects", f"{name}-{key}")
    os.makedirs(path, mode = 0o700, exist_ok=True)
    return path


SYSTEM = "You are a coding agent working in the user's workspace.Inspect files before answering questions about them. After writing code, run it to verify it works. If it fails, read the error and fix it. Be concise. Make the smallest edit that works"


#the ROOT resolves to directory from which the harness is called from
ROOT = os.path.realpath(".") 

#DATA_DIR is a directory under '~/.harness' that stores the data
DATA_DIR = data_dir(ROOT)

LOG_PATH = os.path.join(DATA_DIR, 'agent.log')

