import json
import logging
import os
import subprocess

from agent_config import GIT_IGNORE_CONTENT, HISTORY, ROOT, SYSTEM

logger = logging.getLogger(__name__)

def safe_path(p):
    full = os.path.realpath(os.path.join(ROOT, p))
    if full != ROOT and not full.startswith(ROOT + os.sep):
        raise ValueError(f"path outside workspace {p}")
    return full


def list_dir():
    return '\n'.join(os.listdir())

def write_file(file_name, text):
    with open(safe_path(file_name), 'w') as file:
        file.write(text)
    return f"wrote the contents in the file {file_name}\n"

def read_file(file_name):
    with open(safe_path(file_name),'r') as file:
        data = file.read()
    return ''.join(data)

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
        return f"error : text matches {count} time. Include more surrounding texts so it matches exactly once"

   

    with open(safe_path(file_name), 'w') as file:
        file.write(content.replace(old, new))
    return "ok"
    

def run_shell(command):
    print(f'\n Agent wants to run {command}')
    if input("Allow ? (y/n)").lower() != "y":
        return "error: user denied this command"

    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True,timeout=30, check=False) #doesnt cause exception
    except subprocess.TimeoutExpired:
        return "error: command timed out after 30s"
    
    return f"exit={r.returncode}\nstdout:\n{r.stdout[:5000]}\nstderr:\n{r.stderr[:5000]}"


def save_history(messages):
    try:
        with open(safe_path(HISTORY), 'w') as fp:
            json.dump(messages, fp)
            print(f'HISTORY saved... to {HISTORY}')
    except Exception as e:
        logger.exception("Exception in opening history.json file")
        print(e)

def load_history():
    if os.path.exists(safe_path(HISTORY)):
        try:
            with open(safe_path(HISTORY), 'r', encoding='utf-8') as file:
                history = json.load(file)
                if history:
                    print(f'HISTORY LOADED.... from {HISTORY}\n')
                    return history
        except json.JSONDecodeError:
            #using logger.exception here causes traceback into the log but it is not needed
            logger.info('%s file decoding fail', HISTORY)

    return [{"role" : "system", "content" : SYSTEM}] 


def trim_messages(messages, max_messages = 10):
    """ Trim the messages to the most recent 10 and make sure it starts with user message"""

    if len(messages) <= max_messages:
        return messages

    #get the last 10
    new_messages = messages[- max_messages:]

    for i, m in enumerate(new_messages):
        if m["role"] == "user":
            return [messages[0]] + new_messages[i:]
    return new_messages

def initialize_git():
    """Ensure ROOT is its own git repo. Returns True if usable, False otherwise."""
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, cwd=ROOT, check=False)
        if r.returncode == 0 and os.path.realpath(r.stdout.strip()) == ROOT:
            return True
        subprocess.run(["git", "init"], check=True, capture_output=True,
                       text=True, cwd=ROOT)

        with open(os.path.join(ROOT,'.gitignore'),'w') as file:
            file.write(GIT_IGNORE_CONTENT)
            logger.info('.gitignore created')
            
        return True
    except FileNotFoundError:
        logger.error("git is not installed; change reports disabled")
        return False
    except subprocess.CalledProcessError as e:
        logger.error("git init failed: %s", e.stderr)
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
    


        