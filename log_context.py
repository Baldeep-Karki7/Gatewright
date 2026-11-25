#Session and turn ids, added to every agent.log line

#multiple tasks can run concurrently on a single thread
#contextvars keeps the variables task specific for tasks running in the same thread

import contextvars
import logging

_session = contextvars.ContextVar("session", default = "-")
_turn = contextvars.ContextVar("turn", default = "-")

def set_session(session_id):
    _session.set(session_id)

def set_turn(turn_id):
    #mark the start of a turn. returns a token for reset_turn()
    return _turn.set(turn_id)

def reset_turn(token):
    #mark the end of a turn
    _turn.reset(token)

class ContextFilter(logging.Filter):
    """Adds record, session and record.turn. Never drops a line"""
    def filter(self, record):
        record.session = _session.get()
        record.turn = _turn.get()
        return True