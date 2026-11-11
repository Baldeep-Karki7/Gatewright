import logging

from events.sessions import update_session_metadata

from .base import Event

logger = logging.getLogger(__name__)

#events are appened to a jsonl using this class
class EventLog:
    def __init__(self, path):
        self.path = path
        self.events = []
        self.handlers = []

    def subscribe(self, handler):
        self.handlers.append(handler)

    # def append(self, type, payload, tool)
    def append(self, event: Event, project_dir, session_id):
        line = event.model_dump_json() + "\n"
        with open(self.path,'a') as file:
            file.write(line)
        self.events.append(event)

        update_session_metadata(project_dir, session_id)

        #have the handler handle the new event
        for handler in self.handlers:
            try:
                handler(event)
            except Exception:
                logger.exception("event handler exception")

        return event

    def all(self):
        return list(self.events)