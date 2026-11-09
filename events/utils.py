#create an abort turn fucntion that appends a TurnAbortedEvent to EventLog
#delete the in-memory messages to the checkpoint in case of TrunAbortedEvent
import logging

from .event_log import EventLog
from .types import TurnAbortedEvent

logger = logging.getLogger(__name__)

# class TurnAbortedEvent(Event):
#     """Used when an ongoing event is aborted due to expections. This allows rollback for messages"""
#     source : Literal["environment"] = "environment"
#     type : Literal["turn_aborted"] = "turn_aborted"
#     turn_start_id : str #id of the userMessageEvent that began the turn
#     error_type : str
#     message : str


def abort_turn(messages: list, checkpoint: int, start_id: str, event_log: EventLog, exc: Exception):
    #delete the messages after the checkpoint
    del messages[checkpoint:] 

    try:
        event_log.append(TurnAbortedEvent(
            turn_start_id= start_id,
            error_type= type(exc).__name__,
            message= str(exc)[:500]
        ))
    except Exception:
        logger.exception("Failed to log turn abort")