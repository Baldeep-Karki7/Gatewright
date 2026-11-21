import json
import os
from datetime import datetime, timezone
from uuid import uuid4


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


def select_session(sessions):
    """Display available sessions and let the user select one."""

    if not sessions:
        return None

    print("\nPrevious sessions:\n")

    for i, session in enumerate(sessions, start=1):
        title = session.get("title", "New session")
        updated_at = session.get("updated_at", "Unknown")

        print(f"{i}. {title}")
        print(f"   Updated: {updated_at}")
        print(f"   ID: {session['id'][:8]}")
        print()

    while True:
        try:
            choice = input("Select a session (number): ").strip()
        except (EOFError, KeyboardInterrupt):
            return None

        try:
            index = int(choice) - 1

            if 0 <= index < len(sessions):
                return sessions[index]["id"]

            print("Invalid selection. Choose a number from the list.")

        except ValueError:
            print("Please enter a valid number.")

#I need to create a function called resume_session
def resume_session(project_dir, session_id):

    events_path = os.path.join(project_dir, "sessions", f"{session_id}.jsonl")

    return session_id, events_path
        

def get_session(args, project_dir, interactive=True):

    sessions = list_sessions(project_dir)

    # Default: create a new session
    if not args.continue_session and args.resume is None:
        return create_session(project_dir)

    # --continue
    if args.continue_session:

        if not sessions:
            return create_session(project_dir)

        # list_sessions() already sorts newest first
        session_id = sessions[0]["id"]

        return resume_session(project_dir, session_id)

    # --resume
    if args.resume is not None:

        if not sessions:
            return create_session(project_dir) #session_id, events.jsonl

        if args.resume == "interactive":
            if not interactive:
                raise ValueError(
                    "--resume needs a session ID in non-interactive mode; "
                    "use --continue or pass an ID"
                )
            session_id = select_session(sessions)
            if session_id is None:
                return create_session(project_dir)
        else:
            session_id = args.resume

        return resume_session(project_dir, session_id)
