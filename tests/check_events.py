import sys

from events.replay import build_messages, drop_aborted, load_events


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "events.jsonl"
    events = load_events(path)

    counts = {}
    for e in events:
        counts[e.type] = counts.get(e.type, 0) + 1
    print("events:", counts)

    actions = {e.id: e for e in events if e.type == "action"}
    answered = set()
    for e in events:
        if e.type == "observation":
            a = actions.get(e.action_id)
            if a is None:
                print("ORPHAN observation", e.action_id)
            elif a.tool_call_id != e.tool_call_id:
                print("MISMATCH tool_call_id", e.action_id)
            if e.action_id in answered:
                print("DUPLICATE observation for", e.action_id)
            answered.add(e.action_id)
    for aid, a in actions.items():
        if aid not in answered:
            print("UNANSWERED action:", a.tool_name, aid)

    msgs = build_messages(drop_aborted(events))
    ok, i, shape = True, 0, []
    while i < len(msgs):
        m = msgs[i]
        if m["role"] == "assistant" and m.get("tool_calls"):
            ids = {c["id"] for c in m["tool_calls"]}
            shape.append("assistant(%d calls)" % len(ids))
            j = i + 1
            while j < len(msgs) and msgs[j]["role"] == "tool":
                ids.discard(msgs[j]["tool_call_id"])
                shape.append("tool")
                j += 1
            if ids:
                ok = False
                print("MISSING tool results for", ids)
            i = j
        else:
            if m["role"] == "tool":
                ok = False
                print("STRAY tool message", m["tool_call_id"])
            shape.append(m["role"])
            i += 1
    print("shape:", " > ".join(shape))
    print("valid" if ok else "INVALID")


if __name__ == "__main__":
    main()
