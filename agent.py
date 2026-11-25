import logging
import os
import sys
import traceback

import openai
from dotenv import load_dotenv
from openai import OpenAI


from log_context import set_session, set_turn, reset_turn, ContextFilter

from agent_config import DATA_DIR, INTERACTIVE, LOG_PATH, SYSTEM
from events.display import ConsoleDisplay
from events.event_log import EventLog
from events.replay import drop_aborted, load_events, rebuild_messages
from events.sessions import get_session, update_session_title
from events.todos import CANCELLED, TERMINAL, TodoStore, latest_todos, resume_note
from events.types import MessageEvent
from events.utils import abort_turn
from llm import call_llm, RequestTooLarge
from parseArgs import parse_args
from permissions.approver import build_gate
from permissions.gate import Gate
from utils import (
    change_report,
    edit_file,
    initialize_git,
    list_dir,
    read_file,
    run_shell,
    snapshot,
    write_file,
)

#create a handler for logs for more control
handler = logging.FileHandler(LOG_PATH)
handler.addFilter(ContextFilter()) #always returns True so all messages are passed and written
handler.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)s session=%(session)s turn=%(turn)s %(name)s %(message)s"
))

logging.basicConfig(level=logging.INFO, handlers= [handler])

logger = logging.getLogger(__name__)

load_dotenv()
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ["GROQ_API_KEY"],
    max_retries=4,
    timeout=120.0,)



available_functions = {
    "read_file": read_file,
    "list_dir": list_dir,
    "write_file": write_file,
    "run_shell": run_shell,
    "edit_file": edit_file,
}

MAX_TODO_NUDGES = 2

BATCH_YES = False  # set from --yes in __main__

def plan_state(todo_store):
    """A comparable copy of the current plan, used to see if this turn changed it."""
    return [i.model_dump() for i in todo_store.items]


def run_turn(messages, start_id, checkpoint, event_log,project_dir, session_id, todo_store, tool_profile, gate: Gate):
    """Run the model on the current messages. On failure, undo the turn and record it."""

    turn_token = set_turn(start_id)
    before = snapshot()
    logger.info("CHANGES before = %s", before)
    plan_before = plan_state(todo_store)
    nudge_at = None          # position of the temporary nudge message, if any


    try:
        for attempt in range(MAX_TODO_NUDGES + 1):
            reply = call_llm(client, messages, available_functions, event_log=event_log, session_id = session_id, tool_profile = tool_profile, gate=gate)

            if nudge_at is not None:
                del messages[nudge_at]
                nudge_at = None

            messages.append({"role" : "assistant", "content" : reply})

            plan_open = todo_store.active and plan_state(todo_store) != plan_before

            if not plan_open or attempt == MAX_TODO_NUDGES:
                print(f"Assistant : {reply}")
                if plan_open:
                    print("\nNote: the todo list is still unfinished:\n"
                          + todo_store.render())
                break

            logger.info("TODO nudge %d/%d", attempt + 1, MAX_TODO_NUDGES)
            nudge_at = len(messages)
            messages.append({
                "role": "user",
                "content": (
                    "Your todo list is not finished yet:\n"
                    f"{todo_store.render()}\n"
                    "Continue with the in_progress item. Mark an item completed "
                    "only after a tool result shows it worked. If something cannot "
                    "be done, or a command was denied, set it to cancelled and "
                    "tell the user what is unverified."
                ),
            })
    except RequestTooLarge as e:
        logger.warning("turn aborted, request too large: %s", e.kind)
        if e.kind == "rate_limit_tokens":
            print("This request is bigger thatn your provider's per-minute token limit", "so it cant be sent/ Aks about a smaller part of the file, lower HARNESS_READ_MAX_CHARS, or use a higher provider tier.")
        else:
            print("The conversation no longer fits in the model's context window. Start a new session or ask about a smaller part of the code")
        abort_turn(messages, checkpoint, start_id, event_log, e, project_dir, session_id)
    except openai.AuthenticationError as e:
        logger.exception("Auth failed")
        print("API key rejected. Check Ollama API key")
        abort_turn(messages, checkpoint, start_id, event_log, e, project_dir, session_id)
    except openai.RateLimitError as e:
        logger.exception("Rate limited after retries")
        print("Too many requests. Wait a minute and retry")
        abort_turn(messages, checkpoint, start_id, event_log, e, project_dir, session_id)
    except (openai.APIConnectionError, openai.APITimeoutError) as e:
        logger.exception("Could not reach the API")
        print("Network failure after retries. Check the connection and try again")
        abort_turn(messages, checkpoint, start_id, event_log, e, project_dir, session_id)
    except Exception as e:
        logger.exception("turn failed")
        traceback.print_exc()
        abort_turn(messages, checkpoint, start_id, event_log, e, project_dir, session_id)
    finally:
        after = snapshot()
        logger.info("CHANGES before = %s after = %s", before, after)
        if before is not None and after is not None and after != before:
            report = change_report(before, after)
            if report:
                print(report)
        reset_turn(turn_token) #reset the turn

def last_user_event_id(events_path):
    """Return the id of the most recent user message in the event file."""
    for e in reversed(load_events(path = events_path)):
        if e.type == "message" and e.source == "user":
            return e.id
    return None

def ask(question, default=False):
    """Ask a yes/no question. Batch mode never blocks on input()."""
    if not INTERACTIVE:
        return BATCH_YES or default
    try:
        return input(f"{question} (y/n): ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return default

def reset_in_progress(todo_store):
    """An interrupted in_progress step goes back to pending (live list only)."""
    todo_store.items = [
        i.model_copy(update={"status": "pending"}) if i.status == "in_progress" else i
        for i in todo_store.items
    ]

def cancel_open_todos(todo_store, stored_events):
    """Mark every unfinished item cancelled, log it, and empty the live list."""
    last = latest_todos(stored_events)
    cancelled = [
        i if i.status in TERMINAL else i.model_copy(update={"status": CANCELLED})
        for i in todo_store.items
    ]
    todo_store.write(cancelled, turn_start_id=last.turn_start_id)
    todo_store.items = []
    todo_store.turn_start_id = None

def restore_system_prompt(messages, todo_store):
    """Drop the carry-over note once the plan is no longer open."""
    if not todo_store.active and messages[0]["content"] != SYSTEM:
        messages[0] = {"role": "system", "content": SYSTEM}

def run_agent(session_id, events_path, project_dir, gate, tool_profile, one_shot_prompt=None,):
    # Initialize the event log for this session here.
    # Adapt this to your EventLog constructor.

    event_log = EventLog(events_path)

    #create the todostore
    todo_store = TodoStore(event_log, project_dir, session_id)
    stored_events = drop_aborted(load_events(events_path))
    todo_store.load(stored_events)
    available_functions["todo_write"] = todo_store.write

    messages = rebuild_messages(
        events_path,
        SYSTEM ,
        event_log, project_dir, session_id
    )

    interrupted = messages[-1]["role"] in ("user", "tool")
    plan_open = todo_store.active
    resume_turn = False
    keep_plan = False
    
    if interrupted and plan_open:
        print("The last turn was interrupted, and the todo list is unfinished:")
        print(todo_store.render())
        if ask("Continue it?"):
            resume_turn = keep_plan = True
        else:
            cancel_open_todos(todo_store, stored_events)

    elif interrupted:
        print(f"The last turn was interrupted (last message: {messages[-1]['role']}).")
        resume_turn = ask("Continue it?")

    elif plan_open:
        print("Unfinished todo list:")
        print(todo_store.render())
        if ask("Carry these todos over?"):
            keep_plan = True
        else:
            cancel_open_todos(todo_store, stored_events)

    if keep_plan:
        reset_in_progress(todo_store)
        note = resume_note(latest_todos(stored_events))
        messages[0] = {"role": "system", "content": SYSTEM + "\n\n" + note}

    event_log.subscribe(ConsoleDisplay())

    if resume_turn:
        start_id = last_user_event_id(events_path)
        todo_store.turn_start_id = start_id
        checkpoint = max(
            (i for i, m in enumerate(messages) if m["role"] == "user"),
            default=len(messages),
        )
        run_turn(messages, start_id, checkpoint, event_log,
                 project_dir, session_id, todo_store, tool_profile, gate)
        restore_system_prompt(messages, todo_store)


    # With a positional prompt, run exactly one turn and exit.
    one_shot = one_shot_prompt is not None
    user_input = one_shot_prompt

    while True:
        if not one_shot:
            try:
                user_input = input("User : " if INTERACTIVE else "")
            except (EOFError, KeyboardInterrupt):
                break

        if len(messages) == 1:
            update_session_title(
                DATA_DIR,
                session_id=session_id,
                user_message=user_input
            )

        user_event = event_log.append(
            MessageEvent(source="user", content=user_input),
            project_dir=DATA_DIR,
            session_id=session_id
        )

        todo_store.turn_start_id = user_event.id

        checkpoint = len(messages)
        messages.append({
            "role": "user",
            "content": user_input
        })

        run_turn(messages, user_event.id, checkpoint, event_log, project_dir, session_id, todo_store, tool_profile, gate)
        restore_system_prompt(messages, todo_store)

        if one_shot:
            break


if __name__ == "__main__":
    args = parse_args()

    BATCH_YES = args.yes

    if not initialize_git():
        print("IMPORTANT: Git must be installed.")
        sys.exit(1)

    session_id, events_path = get_session(args, DATA_DIR, interactive=INTERACTIVE)

    set_session(session_id= session_id)

    #build the gate
    gate = build_gate(args)

    run_agent(session_id, events_path=events_path, project_dir=DATA_DIR, tool_profile=args.profile, one_shot_prompt=args.prompt, gate=gate)