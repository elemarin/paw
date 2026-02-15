from paw.agent.memory import MemoryTool


class _DummyDB:
    def __init__(self, data_dir):
        self.data_dir = data_dir


async def test_memory_tool_uses_memsearch_store(tmp_path):
    db = _DummyDB(tmp_path)
    tool = MemoryTool(db)

    await tool.load_from_db()
    assert await tool.execute(action="list") == "Memory is empty."

    assert (
        await tool.execute(action="remember", key="name", value="Chips")
        == "Remembered: name = Chips"
    )
    assert await tool.execute(action="recall", key="name") == "name = Chips"
    assert "name: Chips" in await tool.execute(action="list")

    assert await tool.execute(action="forget", key="name") == "Forgot: name"
    assert await tool.execute(action="recall", key="name") == "No memory found for key 'name'."
