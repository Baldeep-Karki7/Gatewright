import json
import logging

from openai import OpenAI

from tools import EDIT_TOOL, LIST_TOOL, READ_TOOL, SHELL_TOOL, WRITE_TOOL

#module level logger
logger = logging.getLogger(__name__)

MAX_STEPS = 20

def call_llm(client:OpenAI ,messages : list, available_functions : list) -> str:

    for _ in range(20):
        response = client.chat.completions.create(
                model="gemma4:31b",
                messages=messages,
                tools=[READ_TOOL, LIST_TOOL, WRITE_TOOL, SHELL_TOOL, EDIT_TOOL]
            )

        #Model call logs
        logger.info("MODEL call: prompt_tokens = %d completion_tokens = %d",response.usage.prompt_tokens, response.usage.completion_tokens)
    
            
        msg = response.choices[0].message
        if not msg.tool_calls:
            return msg.content or ""

        messages.append(msg.model_dump(exclude_none = True))  # assistant message containing tool_calls

        # breakpoint()
        for tool_call in msg.tool_calls:
            print(f"Calling tool: {tool_call.function.name}")
            try:
                fn = available_functions[tool_call.function.name]
                result = str(fn(**json.loads(tool_call.function.arguments)))

                ok = not result.startswith("error")
                if tool_call.function.name == "run_shell":
                    ok = ok and result.startswith("exit=0")

                #log the tool call as info if success
                logger.info("TOOL = %s args = %s ok = %s result = %s",tool_call.function.name, tool_call.function.arguments, ok, result[:300])
            except Exception as e:
                logger.exception("TOOL %s failed", tool_call.function.name)
                result = f"error: {type(e).__name__}: {e}"   # model sees it and can adapt
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
    raise RuntimeError("Agent hit 20-iteration limit")