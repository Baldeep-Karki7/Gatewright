# from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class Event(BaseModel):

    model_config = {"frozen" : True}

    id : str = Field(default_factory=lambda : str(uuid4()))
    timestamp: str = 'Today'
    type : Literal["message", "action", "observation","turn_aborted"]
    source : Literal["agent", "user", "environment"]
