import logging
import os
import sys
import traceback

import openai
from dotenv import load_dotenv
from openai import OpenAI

from agent_config import EVENTS_PATH, LOG_PATH, SYSTEM
from events.display import ConsoleDisplay
from events.event_log import EventLog
from events.replay import load_events, rebuild_messages
from events.types import MessageEvent
from events.utils import abort_turn
from llm import call_llm
from utils import (
    change_report,
    edit_file,
    initialize_git,
    list_dir,
    read_file,
    run_shell,
    snapshot,
    trim_messages,
    write_file,
)

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

load_dotenv()
client = OpenAI(
    base_url="https://ollama.com/v1",
    api_key=os.environ["OLLAMA_API_KEY"],
    max_retries=4,
    timeout=120.0,
)

available_functions = {
    "read_file": read_file,
    "list_dir": list_dir,
    "write_file": write_file,
    "run_shell": run_shell,
    "edit_file": edit_file,
}

event_log = EventLog(EVENTS_PATH)


def run_turn(messages, start_id, checkpoint):
    """Run the model on the current messages. On failure, undo the turn and record it."""
    before = snapshot()
    logger.info("CHANGES before = %s", before)

    try:
        reply = call_llm(client, messages, available_functions, event_log=event_log)
        messages.append({"role": "assistant", "content": reply})
        print(f"Assistant : {reply}")

    except openai.AuthenticationError as e:
        logger.exception("Auth failed")
        print("API key rejected. Check Ollama API key")
        abort_turn(messages, checkpoint, start_id, event_log, e)
    except openai.RateLimitError as e:
        logger.exception("Rate limited after retries")
        print("Too many requests. Wait a minute and retry")
        abort_turn(messages, checkpoint, start_id, event_log, e)
    except (openai.APIConnectionError, openai.APITimeoutError) as e:
        logger.exception("Could not reach the API")
        print("Network failure after retries. Check the connection and try again")
        abort_turn(messages, checkpoint, start_id, event_log, e)
    except Exception as e:
        logger.exception("turn failed")
        traceback.print_exc()
        abort_turn(messages, checkpoint, start_id, event_log, e)
    finally:
        after = snapshot()
        logger.info("CHANGES before = %s after = %s", before, after)
        if before is not None and after is not None and after != before:
            report = change_report(before, after)
            if report:
                print(report)


def last_user_event_id():
    """Return the id of the most recent user message in the event file."""
    for e in reversed(load_events(EVENTS_PATH)):
        if e.type == "message" and e.source == "user":
            return e.id
    return None


if __name__ == "__main__":
    if not initialize_git():
        print("IMPORTANT : Git must be installed. Cannot observe file changes without git")
        sys.exit(1)

    # Rebuild the conversation from the event file, then start showing events.
    messages = rebuild_messages(EVENTS_PATH, SYSTEM, event_log)
    event_log.subscribe(ConsoleDisplay())
    messages = trim_messages(messages, max_messages=10)

    # If the last turn was cut off, offer to continue it.
    if messages[-1]["role"] in ("user", "tool"):
        print("The last turn was interrupted.")
        if input("Continue it? (y/n): ").lower() == "y":
            start_id = last_user_event_id()
            checkpoint = max(
                (i for i, m in enumerate(messages) if m["role"] == "user"),
                default=len(messages),
            )
            run_turn(messages, start_id, checkpoint)

    while True:
        try:
            user_input = input("User : ")
        except (EOFError, KeyboardInterrupt):
            break

        user_event = event_log.append(MessageEvent(source="user", content=user_input))
        checkpoint = len(messages)
        messages.append({"role": "user", "content": user_input})

        run_turn(messages, user_event.id, checkpoint)