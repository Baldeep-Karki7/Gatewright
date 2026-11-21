import logging
from typing import Optional

from pydantic import ValidationError

from events.event_log import EventLog
from events.types import TodoEvent, TodoItem

logger = logging.getLogger(__name__)

PENDING = "pending"
IN_PROGRESS = "in_progress"
COMPLETED = "completed"
CANCELLED = "cancelled"
TERMINAL = {COMPLETED, CANCELLED}

MAX_ITEMS = 12
MAX_CONTENT = 120

MARKS = {
    PENDING: "[ ]",
    IN_PROGRESS: "[~]",
    COMPLETED: "[x]",
    CANCELLED: "[-]",
}

def render(items: list[TodoItem]) ->str:
    """Compact text to show """
    return "\n".join(
        f"{MARKS.get(i.status, '[?]')}{i.id} {i.content}" for i in items
    )
def latest_todos(events):
    """Return the most recent TodoEvent in an event list or None"""
    for event in reversed(events):
         if event.type == "todo_update":
              return event
    return None

def active_todos(events, turn_start_id = None):
    """Current list only if it belongs to 'turn_start_id' and still has work'"""
    event = latest_todos(events)
    if event  is None:
        return None
    if turn_start_id is not None and turn_start_id != event.turn_start_id:
        return None
    if not any(i.status not in TERMINAL for i in event.todos):
        return None
    return event


def resume_note(event, reset_in_progress = True):
    """Short text for the model when carrying a list over after an interruption"""

    if event is None:
        return ""
    items = []
    for item in event.todos:
        if reset_in_progress and item.status == IN_PROGRESS:
            item = item.model_copy(update={"status" : PENDING})
        items.append(item)
    return "\n".join([
        "An unfinished todo list exists from an earlier turn.",
        "The interrupted step may or may not have run — check files before repeating it.",
        render(items),
        "Keep exactly one item in_progress and finish the list before answering.",
    ])



def _coerce_item(raw, index):
    """Check if the item follows the TodoItem schema"""
    if isinstance(raw, TodoItem):
        return raw
    if not isinstance(raw, dict):
        raise TypeError(f"item {index} must be an object")
    data = dict(raw)
    content = data.get("content")

    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"item {index}: content must be a non-empty string")
    content = content.strip()
    if len(content) > MAX_CONTENT:
        raise ValueError(f"item {index}: content must be <= {MAX_CONTENT} chars")
    data["content"] = content
    if not data.get("id"):
        data["id"] = f"t{index + 1}"

    try:
        return TodoItem.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"item {index}: invalid field(s): {exc}") from exc

    

def validate_todos(payload, previous = None):
    """Validate whole list update. Raises ValueError with model-readable text"""

    if not isinstance(payload, list) or not payload:
        raise ValueError("todos must be a non-empty list")
    if len(payload) > MAX_ITEMS:
        raise ValueError(f"todos must have at most {MAX_ITEMS} items")

    items = [_coerce_item(raw, i) for i, raw in enumerate(payload)] 

    ids = [i.id for i in items]
    if len(ids) != len(set(ids)):
        raise ValueError("todo ids must be unique")
    
    old = {i.id: i for i in (previous or [])}
    for item in items:
        prior = old.get(item.id)
        if prior is None:
            continue
        if prior.status in TERMINAL and item.status != prior.status:
            raise ValueError(
                f"{item.id} is already {prior.status}; start a new turn to reopen it"
            )
        if prior.status == IN_PROGRESS and item.status == PENDING:
            raise ValueError(f"{item.id} cannot go from in_progress back to pending")

    unfinished = [i for i in items if i.status not in TERMINAL]

    if unfinished:
        active = [i for i in unfinished if i.status == IN_PROGRESS]
        if len(active) != 1:
            raise ValueError(
            "keep exactly one item in_progress while work remains; "
            "mark finished items completed"
        )
    return items




class TodoStore:
    """In-memory mirror of event-sourced todo list"""

    def __init__(self, event_log :EventLog, project_dir:str, session_id:str, turn_start_id: Optional[str]= None):
        self.event_log = event_log
        self.project_dir = project_dir
        self.session_id = session_id
        self.turn_start_id = turn_start_id
        self.items: list[TodoItem] = []

    @property
    def active(self)->bool:
        return any(i.status not in TERMINAL for i in self.items)

    def load(self, events):
        """Rebuild from the last TodoEvent in an already-filtered event list"""
        event = latest_todos(events)
        if event is None:
            self.items = []
            return
        self.items = list(event.todos)
        self.turn_start_id = event.turn_start_id
        
    
    def render(self)->str:
        return render(self.items)

    def write(self, todos, turn_start_id: Optional[str]= None):
        """Registered as the todo_write tool. Replaces the whole list"""
        try:
            items = validate_todos(todos, previous = self.items)
        except ValueError as exc:
            return f"error: {exc}"

        start = turn_start_id or self.turn_start_id
        event = self.event_log.append(
            TodoEvent( todos = items, turn_start_id = start),
            project_dir= self.project_dir,
            session_id= self.session_id
        )

        self.items = list(items)
        self.turn_start_id = event.turn_start_id
        return render(items)
             


         