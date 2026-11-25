import json
import logging
import os
from typing import Any, Optional
from uuid import uuid4

import openai
from dotenv import load_dotenv
from openai import OpenAI

from agent_config import DATA_DIR
from events.event_log import EventLog
from events.types import ActionEvent, MessageEvent, ObservationEvent
from tool_profiles import TOOL_PROFILES
from tools import EDIT_TOOL, LIST_TOOL, READ_TOOL, SHELL_TOOL, TODO_TOOL, WRITE_TOOL

logger = logging.getLogger(__name__)

load_dotenv()

MAX_STEPS = 20
MODEL_NAME = os.environ["GROQ_MODEL_NAME"]

TOOLS = [READ_TOOL, LIST_TOOL, WRITE_TOOL, SHELL_TOOL, EDIT_TOOL, TODO_TOOL]


class RequestTooLarge(Exception):
    """when a request is too large for the model, it has to be made smaller first
    
    Retrying the same request is pointless, so this RequestTooLarge Exception is raised, instead of feeding the error back to the model
    """

    def __init__(self, kind, detail):
        super().__init__(f"{kind} : {detail}")
        self.kind = kind #rate_limit_tokens or context_length
        self.detail = detail

def get_tools_for_profile(profile):
    if profile not in TOOL_PROFILES:
        raise ValueError(f"Unknown tool profile: {profile}")

    allowed = TOOL_PROFILES[profile]

    return [
        tool for tool in TOOLS
        if tool["function"]["name"] in allowed
    ]


def too_large_kind(exc):
    """Why the request is too big or None if it'ssome other error"""

    status = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    text = str(getattr(exc, "message", exc)).lower()

    #413 : one:request is bigger thatn per-minute token limit (Groq)
    if status == 413:
       return "rate_limit_tokens"

   #400: messages list doens't fit in the models' context window
    if status == 400 and (
        code == "context_length_exceeded"
        or "context length" in text
        or "maximum context" in text
    ):
       return "context_length"

    return None
   

def call_llm(client: OpenAI, messages: list, available_functions: dict,
             event_log: EventLog, session_id: str, tool_profile:str, gate) -> str:
    """Run the model until it answers, executing tool calls along the way.

    Malformed calls are reported back to the model as tool results instead of
    crashing the turn. An API-level 400 (the provider rejects a bad tool call
    before returning it) is also fed back so the model can correct and retry.
    """

    allowed_tools = TOOL_PROFILES[tool_profile]
    selected_tools = get_tools_for_profile(tool_profile)

    for step in range(MAX_STEPS):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=selected_tools,
            )
        except openai.APIStatusError as exc:
            # The whole completion was rejected, so there is no message to
            # append and no tool call to answer. Give the model the reason and
            # let it try again; MAX_STEPS bounds the retries.
            detail = getattr(exc, "message", str(exc))[:800]

            #if req too large, retrying the same req can never work
            kind = too_large_kind(exc)
            if kind:
                logger.warning("Request too large (%s, step %d): %s", kind, step, detail)
                raise RequestTooLarge(kind, detail) from exc

            #401, 429, 5xx: agent.py handles these:
            if not isinstance(exc, openai.BadRequestError):
                raise

            #400 about the models' tool calls
            logger.warning("API rejected the request (step %d): %s", step, detail)
            messages.append({
                "role": "user",
                "content": (
                    "Your previous response was rejected before any tool ran:\n"
                    f"{detail}\n"
                    "Call one of the declared tools with every required argument "
                    "present and correctly typed, then try again."
                ),
            })
            continue

        logger.info(
            "MODEL call: prompt_tokens = %d completion_tokens = %d",
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
        )

        msg = response.choices[0].message
        response_id = uuid4().hex

        if msg.content or not msg.tool_calls:
            event_log.append(MessageEvent(
                response_id=response_id,
                content=msg.content or "",
                source="agent",
                type="message",
            ), project_dir=DATA_DIR, session_id=session_id)

        if not msg.tool_calls:
            return msg.content or ""

        # Assistant message carrying the tool_calls, required by the API.
        messages.append(msg.model_dump(exclude_none=True))

        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            raw_args = tool_call.function.arguments

            try:
                args = json.loads(raw_args)
            except (json.JSONDecodeError, TypeError):
                args = None

            # Log the action first, even when the call is malformed, so the
            # event log keeps a faithful record of what the model attempted.
            action_event = event_log.append(ActionEvent(
                source="agent",
                type="action",
                response_id=response_id,
                tool_name=name,
                tool_call_id=tool_call.id,
                arguments=args if isinstance(args, dict) else {},
            ), project_dir=DATA_DIR, session_id=session_id)

            if not isinstance(args, dict):
                result = (
                    "error: tool arguments must be a JSON object; got "
                    f"{raw_args!r}"
                )
            elif name not in allowed_tools:
                result = (
                    f"error: tool '{name}' is not available "
                    f"under the current {tool_profile} profile."
                )
            elif name not in available_functions:
                result = f"error: unknown tool '{name}'."
            else:
                verdict = gate.check(name, args) #function name and args

                #if tool call is not allowed return the message else call the tool
                if not verdict.allowed:
                    result = verdict.message
                else:
                    try:
                        result = str(available_functions[name](**args))
                    except Exception as e:
                        logger.exception("TOOL %s failed", name)
                        result = f"error: {type(e).__name__}: {e}"

            ok = not result.startswith("error")
            if name == "run_shell":
                ok = ok and result.startswith("exit=0")
            logger.info(
                "TOOL = %s args = %s ok = %s result = %s",
                name, args, ok, result[:300],
            )

            # Every tool_call must get a matching tool result message.
            event_log.append(ObservationEvent(
                source="environment",
                type="observation",
                action_id=action_event.id,
                tool_call_id=tool_call.id,
                tool_name=name,
                content=result,
            ), project_dir=DATA_DIR, session_id=session_id)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    raise RuntimeError(f"Agent hit {MAX_STEPS}-iteration limit")
