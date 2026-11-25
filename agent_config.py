import hashlib
import os
import sys

from dotenv import load_dotenv

load_dotenv()  # must run before any os.environ read below

INTERACTIVE = sys.stdin.isatty()



def data_dir(root):
    """Return the workspace's data folder under ~/.harness, creating it if needed"""

    base = os.path.expanduser('~/.harness')
    key = hashlib.sha256(root.encode()).hexdigest()[:12]
    name = os.path.basename(root)

    path = os.path.join(base, "projects", f"{name}-{key}")
    os.makedirs(path, mode = 0o700, exist_ok=True)
    return path


def env_int(name, default, minimum = 1):
    raw = os.environ.get(name)
    if raw is None:
        return default

    try:
        value = int(raw)
    except ValueError:
        raise SystemExit(f"{name} must be a whole number, got {raw!r}")
    return max(minimum, value)



SYSTEM = "You are a coding agent working in the user's workspace.Inspect files before answering questions about them. Do only what the user asked. Don’t read/inspect extra files or take extra actions unless necessary to fulfill the request. Be concise. Make the smallest edit that works. For a task with three or more steps, first call todo_write with the plan. Keep exactly one item in_progress, update the list as you finish each step, and mark an item completed only after you have checked the work. Skip the list for a single simple step."


#the ROOT resolves to directory from which the harness is called from
ROOT = os.path.realpath(".") 

#DATA_DIR is a directory under '~/.harness' that stores the data
DATA_DIR = data_dir(ROOT)

LOG_PATH = os.path.join(DATA_DIR, 'agent.log')

READ_MAX_CHARS = env_int("HARNESS_READ_MAX_CHARS", 16000, 1000)

#the budget of the provider
#Max tokens sent per request. Groq on-demand allows 8000 tokens/min
#2000 for system promopt overhead
CONTEXT_BUDGET = env_int("HARNESS_CONTEXT_BUDGET", 6000, minimum=2000)

#for rotating file handler, maxBytes for each file
LOG_MAX_BYTES = env_int("HARNESS_LOG_MAX_BYTES", 5 * 1024 * 1024, minimum = 10 * 1024)

#minimum 1 backup, maximum 3 backups
LOG_BACKUPS = env_int("HARNESS_LOG_BACKUPS", 3, minimum=1)



