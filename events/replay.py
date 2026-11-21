#looks at the events.jsonl and creates messages that are included to the model
import json
import logging
from typing import Annotated, Union

from pydantic import Field, TypeAdapter

from .types import (
    ActionEvent,
    MessageEvent,
    ObservationEvent,
    TodoEvent,
    TurnAbortedEvent,
)

#can be any of the 4 events, validated by field
AnyEvent = Annotated[
    Union[MessageEvent, ActionEvent, ObservationEvent, TurnAbortedEvent, TodoEvent],
    Field(discriminator="type")
]

#TypeAdapter allows vlaidating a schema
_parser = TypeAdapter(AnyEvent)

logger = logging.getLogger(__name__)

def load_events(path):
    """Read the file and return a list of events"""

    events = []
    try:
        f = open(path) #file is open
    except FileNotFoundError:
        return events

    with f: #now context manager closes this automatically
        for number, line in enumerate(f, 1):
            #validate if each line is good enough through _parser
            
            line = line.strip()
            if not line:
                continue

            try:
                events.append(_parser.validate_json(line)) #throws a validation error
            except Exception:
                logger.exception("skipping bad line %d in %s", number, path)
        
    return events

def drop_aborted(events):
    """Remove every turn that failed, from its user message to the TurnAbortedEvent"""

    position = {e.id: i for i, e in enumerate(events)}
    remove = set()

    for i, e in enumerate(events):
        if e.type == "turn_aborted" and e.turn_start_id in position:
            remove.update(range(position[e.turn_start_id],i+1))

    #return only the events whose i is not in remove set
    return [e for i,e in enumerate(events) if i not in remove]

def close_unfinished(events, event_log, project_dir, session_id):
    """Give every tool call that has not result an 'interrupted' result"""

    #list the observation events recorded in the log
    answered = {e.action_id for e in events if e.type=="observation"}

    events = list(events)
    #each observation event has an action_id that refers to the action it observed after a tool is called
    interrupted = []
    
    for e in events:
        if e.type =="action" and e.id not in answered:
            #interrupted

            note = event_log.append(ObservationEvent(
                source="environment",
                type="observation",
                action_id=e.id,
                tool_call_id=e.tool_call_id,
                tool_name = e.tool_name,
                content=(
                    "error: interrupted before a result was recorded. "
                    "The command may or may not have run. "
                    "Check the files before repeating it."
                ),
            ), project_dir, session_id)
            interrupted.append(note)
    events.extend(interrupted)

    return events

def build_messages(events):
    """ Turn the events into list of messages the model expects to see"""

    messages = []
    replies = {}

    def reply_for(response_id):
        if response_id is None:
            message = {"role" : "assistant", "content" : ""}
            messages.append(message)
            return message
        if response_id not in replies:
            replies[response_id] = {"role" : "assistant", "content" : ""}
            messages.append(replies[response_id])
        return replies[response_id]

    for e in events:
        if e.type == "message" and e.source == "user":
            messages.append({"role" : "user", "content" : e.content})

        elif e.type == "message":
            reply_for(e.response_id)["content"] = e.content

        elif e.type == "action":                     # a tool call the agent made
            reply_for(e.response_id).setdefault("tool_calls", []).append({
                "id": e.tool_call_id,
                "type": "function",
                "function": {
                    "name": e.tool_name,
                    "arguments": json.dumps(e.arguments),
                },
            })

        elif e.type == "observation":                # the tool's result
            messages.append({
                "role": "tool",
                "tool_call_id": e.tool_call_id,
                "content": e.content,
            })

    return messages

def rebuild_messages(path, system_prompt, event_log, project_dir, session_id):
    """Load the saved events and return the full message list with system prompt"""

    events = load_events(path)
    events = drop_aborted(events)
    events = close_unfinished(events, event_log, project_dir, session_id)
    return [{"role" : "system", "content" : system_prompt}] + build_messages(events) 