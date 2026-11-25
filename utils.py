import logging
import os
import subprocess

from agent_config import ROOT, READ_MAX_CHARS  # READ_MAX_CHARS comes from .env

logger = logging.getLogger(__name__)

READ_MAX_LINES = 2000      # default lines returned per call
READ_MAX_LINE_CHARS = 2000 # longer lines (minified files) are cut



def safe_path(p):
    full = os.path.realpath(os.path.join(ROOT, p))
    if full != ROOT and not full.startswith(ROOT + os.sep):
        raise ValueError(f"path outside workspace {p}")
    return full

def list_dir(path):
    full = safe_path(path.strip())
    return '\n'.join(os.listdir(full))

def write_file(file_name, text):
    with open(safe_path(file_name), 'w') as file:
        file.write(text)
    return f"wrote the contents in the file {file_name}\n"

def read_file(file_name, offset=1, limit=READ_MAX_LINES):
    """Return lines offset..offset+limit-1 (1-based), capped in size.

    The text is returned exactly as stored (no line numbers) so it can be
    copied straight into edit_file. A note at the end says when anything was
    left out and how to read the rest.
    """
    offset = max(1, int(offset))
    limit = max(1, min(int(limit), READ_MAX_LINES))

    with open(safe_path(file_name), 'r') as file:
        lines = file.readlines()

    total = len(lines)
    if total == 0:
        return "[empty file]"
    if offset > total:
        return f"error: offset {offset} is past the end of the file ({total} lines)"

    out, size, cut_lines = [], 0, False
    end = offset - 1
    for line in lines[offset - 1 : offset - 1 + limit]:
        if len(line) > READ_MAX_LINE_CHARS:
            line = line[:READ_MAX_LINE_CHARS] + " [line truncated]\n"
            cut_lines = True
        if size + len(line) > READ_MAX_CHARS:
            break
        out.append(line)
        size += len(line)
        end += 1

    text = ''.join(out)
    notes = []
    if end < total:
        notes.append(f"showing lines {offset}-{end} of {total}. "
                     f"Call read_file again with offset={end + 1} to see more")
    if cut_lines:
        notes.append("some long lines were cut")
    if notes:
        text += f"\n[truncated: {'; '.join(notes)}]"
    return text
    
def edit_file(file_name, old, new, multiple_replace = False):
    with open(safe_path(file_name),'r') as file:
        content = file.read()

    count = content.count(old)

    if count == 0:
        old_s, new_s = old.strip('\n'), new.strip('\n')
        count = content.count(old_s) if old_s else 0
        if count == 0:
            first = old_s.splitlines()[0] if old_s else ""
            hint = ("first line of old exists in the file"
                    if first and first in content
                    else "first line of old not found either")
            return f"error: old text not found ({hint}). Re-read the file and copy the lines exactly."
        old, new = old_s, new_s

    if count > 1 and not multiple_replace: 
        return f"error: text matches {count} time. Include more surrounding texts so it matches exactly once"
   

    with open(safe_path(file_name), 'w') as file:
        file.write(content.replace(old, new))
    return "ok"

#The only environment variables shell command get. Everything else including API kets loaded from the .env is left out
SHELL_ENV_KEYS = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM", "TMPDIR", "SHELL")

def shell_env():
    """A minimal environment for run_shell"""
    env = {k:os.environ[k] for k in SHELL_ENV_KEYS if k in os.environ}
    env.setdefault("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    return env

def run_shell(command):

    # The gate (permissions/gate.py) has already asked the user when needed.
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True,
                           timeout=30, check=False,env= shell_env())
    except subprocess.TimeoutExpired:
        return "error: command timed out after 30s"

    return f"exit={r.returncode}\nstdout:\n{r.stdout[:5000]}\nstderr:\n{r.stderr[:5000]}"



AGENT_FILES = ["agent.log", "events.jsonl", "history.json", ".agent/"]

def hide_agent_files(root):
    """Make sure .gitignore lists the agent's own files, creating the file if needed.

    Returns True if it added anything.
    """
    path = os.path.join(root, ".gitignore")
    text = ""
    if os.path.exists(path):
        with open(path) as f:
            text = f.read()

    listed = {line.strip().lstrip("/") for line in text.splitlines()}
    missing = [name for name in AGENT_FILES if name not in listed]
    if not missing:
        return False

    with open(path, "a") as f:
        if text and not text.endswith("\n"):
            f.write("\n")                  # don't glue onto the last existing line
        f.write("# agent files\n" + "\n".join(missing) + "\n")
    return True


def initialize_git():
    """Make sure ROOT is its own git repo and hides the agent's files.

    Returns True if git is usable, False otherwise.
    """
    try:
        # Is ROOT itself the top of a repo? (A parent folder's repo doesn't count.)
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, cwd=ROOT, check=False)
        own_repo = r.returncode == 0 and os.path.realpath(r.stdout.strip()) == ROOT

        if not own_repo:
            subprocess.run(["git", "init"], check=True, capture_output=True,
                           text=True, cwd=ROOT)

        # If the ignore rules changed, drop the snapshot index so it is rebuilt with them.
        if hide_agent_files(ROOT):
            index = os.path.join(ROOT, ".git", "agent-index")
            if os.path.exists(index):
                os.remove(index)

        return True

    except FileNotFoundError:
        logger.error("git is not installed; change reports disabled")
        return False
    except (subprocess.CalledProcessError, OSError) as e:
        logger.error("git setup failed: %s", e)
        return False

def snapshot():
    """Take a snapshot before and after the iteration in a .git/agent-index file"""
    env = {**os.environ, "GIT_INDEX_FILE": os.path.join(ROOT, ".git", "agent-index")}

    #no use using try except in snapshot
    stage_status = subprocess.run(["git", "add", "-A"], capture_output=True, check=True, env=env)

    if stage_status.returncode == 0:
        write_tree_status = subprocess.run(["git", "write-tree"],capture_output=True,text =True, env=env, check=True)
        return write_tree_status.stdout.strip()
    
    return None

def change_report(before, after):
    status = subprocess.run(["git", "diff", "--numstat","--no-renames", before, after], capture_output=True, text=True, check=False)

    if status.returncode != 0:
        logger.error("git diff failed %s", status.stderr)
        return None
    return status.stdout.strip()
    


        