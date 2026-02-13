from paw.agent.conversation import Conversation


def test_to_messages_keeps_tool_message_with_matching_tool_call() -> None:
    conv = Conversation(id="conv-1")
    conv.add_message(
        "assistant",
        "",
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "hello", "arguments": "{}"},
            }
        ],
    )
    conv.add_tool_result("call_1", "ok")

    messages = conv.to_messages()

    assert len(messages) == 2
    assert messages[0]["role"] == "assistant"
    assert messages[1]["role"] == "tool"
    assert messages[1]["tool_call_id"] == "call_1"


def test_to_messages_drops_orphan_tool_message() -> None:
    conv = Conversation(id="conv-2")
    conv.add_message("assistant", "no tools here")
    conv.add_tool_result("missing_call", "orphan")

    messages = conv.to_messages()

    assert len(messages) == 1
    assert messages[0]["role"] == "assistant"
