from typing import Any, Literal, Optional
from pydantic import BaseModel

from .base import Event


class MessageEvent(Event):
    """Messages by user or agent"""
    source : Literal['agent', 'user']
    content : str
    type : Literal['message'] = "message"
    response_id : Optional[str] = None


class ActionEvent(Event):
    """ Tool calls or actions taken by agent"""
    source : Literal["agent"] = 'agent' #must be agent
    type: Literal["action"] = "action"
    response_id : str
    tool_name : str
    tool_call_id : str
    arguments: dict[str, Any]


class ObservationEvent(Event):
    """Observations in the environment"""
    source : Literal['environment'] = 'environment'
    type: Literal["observation"] = "observation"
    action_id : str #the action_id is the actionevent that observation refers to
    tool_call_id : str
    tool_name : str
    content : Any


class TurnAbortedEvent(Event):
    """Used when an ongoing event is aborted due to expections. This allows rollback for messages"""
    source : Literal["environment"] = "environment"
    type : Literal["turn_aborted"] = "turn_aborted"
    turn_start_id : str #id of the userMessageEvent that began the turn
    error_type : str
    message : str

class TodoItem(BaseModel):
    id : str
    content : str
    status : Literal["pending", "in_progress", "completed", "cancelled"]


class TodoEvent(Event):
    """List of todoitems in the log"""
    source : Literal["agent"] = "agent"
    type : Literal["todo_update"] = "todo_update"
    todos: list[TodoItem]
    turn_start_id : str #the id of the user message tha started this turn
