#Fit the conversation into a token budget before each API call

import json

CHARS_PER_TOKEN = 3 #code is ~3 chars/token
CLEARED = "[old tool output removed to save space; call the tool again if you need it]"

def estimate_tokens(obj):
    #Rough token count of any JSON-able object
    return len(json.dumps(obj, ensure_ascii=False)) // CHARS_PER_TOKEN + 1

def split_turns(messages):
    """Return (system message, groups). Each group starts at a user message, so an assistant tool_call message and it's tool results are never split"""

    head, groups = messages[:1],[]
    for m in messages[1:]:
        #if user message create a new group
        if m["role"] == "user" or not groups:
            groups.append([m])
        else:
        #if not user message, append to the last group
            groups[-1].append(m)
    return head, groups


def fit_to_budget(messages, tools, budget):
    """Return (messages_to_send, estimated_tokens). Doesn't modifies messgaes"""

    head, groups = split_turns(messages)
    if not groups:
        return list(head), estimate_tokens(head)+ estimate_tokens(tools)

    fixed = estimate_tokens(head) + estimate_tokens(tools)
    sizes = [estimate_tokens(g) for g in groups]


    #drop the oldest whole turns. ALways keep the latest one
    while len(groups) > 1 and fixed + sum(sizes) > budget:
        groups.pop(0)
        sizes.pop(0)

    #if the list is still above budget then blank the old tool outputs in the current turn
    current = [dict(m) for m in groups[-1]] #copies
    tool_positions = [i for i, m in enumerate(current) if m["role"] == "tool"]

    for i in tool_positions[:-1]:
        if fixed + sum(sizes[:-1]) + estimate_tokens(current) <= budget:
            break
        current[i]["content"] = CLEARED
    groups[-1] = current

    to_send = head + [m for g in groups for m in g]
    return to_send, fixed + sum(estimate_tokens(g) for g in groups)

    
