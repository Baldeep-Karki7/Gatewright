import hashlib
import json
import os
from datetime import datetime, timezone
from uuid import uuid4


def data_dir(root):
    """Return the workspace's data folder under ~/.harness, creating it if needed"""

    base = os.path.expanduser('~/.harness')
    key = hashlib.sha256(root.encode()).hexdigest()[:12]
    name = os.path.basename(root)

    path = os.path.join(base, "projects", f"{name}-{key}")
    os.makedirs(path, mode = 0o700, exist_ok=True)
    return path



def create_session(project_dir):

    session_dir = os.path.join(project_dir, "sessions")

    os.makedirs(session_dir,mode=0o700 ,exist_ok=True)

    #sessions.json for storing all the sessions metadata
    metadata_path = os.path.join(project_dir, "sessions.json")
    
    #init metadata file if it doesn't exist
    if not os.path.exists(metadata_path):
        with open(metadata_path, "w") as file:
            json.dump({"sessions" : []}, file, indent = 4)

    #read existing metadata
    with open(metadata_path, "r") as file:
        metadata = json.load(file)

    session_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    #create events file
    events_path= os.path.join(session_dir, f"{session_id}.jsonl")

    with open(events_path, 'w', encoding='utf-8'):
        pass

    #Add session metadata
    metadata["sessions"].append({
        "id" : session_id,
        "created_at" : now,
        "last_accessed" : now,
        "updated_at" : now,
        "title" : "New session"   
    }) 

    # Write updated metadata
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=4)

    return session_id, events_path

def update_session_title(project_dir, session_id, user_message):
    """Update the session's metadata"""

    metadata_path = os.path.join(project_dir, "sessions.json")

    with open(metadata_path,'r', encoding="utf-8") as file:
        metadata = json.load(file)

    title = user_message if (len(user_message) <=75) else user_message[:75]
    for session in metadata["sessions"]:
        if session["id"] == session_id:
            session.update(
                {"title" : title}
            )
            break
    else:
        raise ValueError(f"Session {session_id} not found")
    
    with open(metadata_path, 'w', encoding='utf-8') as file:
        json.dump(metadata, file, indent =4)


    


#if the session's name is New Session, then update the name using user message becuase this is the first message
def update_session_metadata(project_dir, session_id):

    """Update the session's metadata"""

    metadata_path = os.path.join(project_dir, "sessions.json")

    with open(metadata_path,'r', encoding="utf-8") as file:
        metadata = json.load(file)

    for session in metadata["sessions"]:
        if session["id"] == session_id:
            session.update(
                {"updated_at" : datetime.now(timezone.utc).isoformat()}
            )
            break
    else:
        raise ValueError(f"Session {session_id} not found")
    
    with open(metadata_path, 'w', encoding='utf-8') as file:
        json.dump(metadata, file, indent =4)





def list_sessions(project_dir):
    #open the sessions_dir
    metadata_path = os.path.join(project_dir, "sessions.json")

    if not os.path.exists(metadata_path):
        return []
    
    with open(metadata_path,'r', encoding='utf-8') as file:
        metadata = json.load(file)

    sessions = metadata.get("sessions")
    return sorted(
        sessions,
        key=lambda session: session.get("updated_at", ""),
        reverse= True
    )



SYSTEM = "You are a coding agent working in the user's workspace.Inspect files before answering questions about them. After writing code, run it to verify it works. If it fails, read the error and fix it. Be concise. Make the smallest edit that works"


#the ROOT resolves to directory from which the harness is called from
ROOT = os.path.realpath(".") 

#DATA_DIR is a directory under '~/.harness' that stores the data
DATA_DIR = data_dir(ROOT)

LOG_PATH = os.path.join(DATA_DIR, 'agent.log')

SESSION_ID, EVENTS_PATH = create_session(DATA_DIR)
