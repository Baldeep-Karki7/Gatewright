import json
import logging
import os
from uuid import uuid4

from openai import OpenAI

from agent_config import DATA_DIR, SESSION_ID
from events.event_log import EventLog
from events.types import ActionEvent, MessageEvent, ObservationEvent
from tools import EDIT_TOOL, LIST_TOOL, READ_TOOL, SHELL_TOOL, WRITE_TOOL

#module level logger
logger = logging.getLogger(__name__)

MAX_STEPS = 20
MODEL_NAME = "openai/gpt-oss-20b"

def call_llm(client:OpenAI ,messages : list, available_functions : list, event_log : EventLog) -> str:

    for _ in range(MAX_STEPS):
        response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=[READ_TOOL, LIST_TOOL, WRITE_TOOL, SHELL_TOOL, EDIT_TOOL]
            )

        #Model call logs
        logger.info("MODEL call: prompt_tokens = %d completion_tokens = %d",response.usage.prompt_tokens, response.usage.completion_tokens)
    
            
        msg = response.choices[0].message
        response_id = uuid4().hex

        #The agents text that wants to call the tools
        if msg.content or not msg.tool_calls:
            event_log.append(MessageEvent(
                response_id= response_id,
                content= msg.content or "",
                source = "agent",
                type= "message"
            ), project_dir=DATA_DIR, session_id=SESSION_ID)

        if not msg.tool_calls:
            return msg.content or ""

        messages.append(msg.model_dump(exclude_none = True))  # assistant message containing tool_calls


        # breakpoint()
        for tool_call in msg.tool_calls:

            name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}

             #log the ActionEvent to the event_log BEFORE the tool runs
            action_event = event_log.append(ActionEvent(
                source = "agent",
                type= "action",
                response_id=response_id,
                tool_name= tool_call.function.name,
                tool_call_id= tool_call.id,
                arguments= args
            ), project_dir=DATA_DIR, session_id=SESSION_ID)

            try:
                fn = available_functions[name]
                result = str(fn(**args))

            except Exception as e:
                logger.exception("TOOL %s failed", tool_call.function.name)
                result = f"error: {type(e).__name__}: {e}"   # model sees it and can adapt

            ok = not result.startswith("error")
            if name == "run_shell":
                ok = ok and result.startswith("exit=0")
            logger.info("TOOL = %s args = %s ok = %s result = %s",
                        name, args, ok, result[:300])

            #Append the Result AFTER the tool call even if the tool call failed
            event_log.append(ObservationEvent(
                source= "environment",
                type="observation",
                action_id=action_event.id,
                tool_call_id= tool_call.id,
                tool_name=tool_call.function.name,
                content= result
            ), project_dir=DATA_DIR, session_id=SESSION_ID)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
    raise RuntimeError(f"Agent hit {MAX_STEPS}-iteration limit")