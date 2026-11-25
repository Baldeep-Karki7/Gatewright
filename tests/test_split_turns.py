import unittest
from context import split_turns

def test_two_user_messages_make_two_groups():
    #Arrange input

    messages = [
        {"role" : "system", "content" : "sys"},
        {"role" : "user", "content" : "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "bye"},
    ]

    #act
    head, groups = split_turns(messages)

    #assert
    assert head == [{"role" : "system", "content" : "sys"}]
    assert len(groups) == 2
    assert groups[0][0]["content"] == "hi"
    assert groups[1][0]["content"] == "bye"


def test_only_system_message_gives_no_groups():
    #Arrange :  a list with only the system message

    messages = [{
        "role" : "system", "content" : "You are a coding agent"
    }]

    head, groups =split_turns(messages)

    assert head == [{"role" : "system", "content" : "You are a coding agent"}]
    assert len(groups) == 0
    assert  groups == []

def test_tool_result_stays_with_its_turn():
    # Arrange
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "read a.txt"},
        {"role": "assistant", "content": ""},          # the model asks for a tool
        {"role": "tool", "content": "file text"},      # the tool's answer
        {"role": "user", "content": "thanks"},
    ]

    # Act
    head, groups = split_turns(messages)

    # Assert
    assert len(groups) == 2
    assert [m["role"] for m in groups[0]] == ["user", "assistant", "tool"]
    assert [m["role"] for m in groups[1]] == ["user"]
