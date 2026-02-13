from datetime import UTC, datetime

from paw.agent.soul import get_system_prompt, load_markdown_memory


def test_load_markdown_memory_loads_expected_files(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()

    now = datetime(2026, 2, 13, tzinfo=UTC)
    (memory_dir / "MEMORY.md").write_text("long term", encoding="utf-8")
    (memory_dir / "2026-02-13.md").write_text("today", encoding="utf-8")
    (memory_dir / "2026-02-12.md").write_text("yesterday", encoding="utf-8")
    (memory_dir / "2026-02-11.md").write_text("before yesterday", encoding="utf-8")
    (memory_dir / "2026-02-10.md").write_text("too old", encoding="utf-8")

    loaded = load_markdown_memory(memory_dir=memory_dir, now=now)

    assert "MEMORY.md" in loaded
    assert "2026-02-13.md" in loaded
    assert "2026-02-12.md" in loaded
    assert "2026-02-11.md" in loaded
    assert "too old" not in loaded


def test_get_system_prompt_includes_memory_block_and_rules(tmp_path):
    soul_path = tmp_path / "soul.md"
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()

    soul_path.write_text("base soul", encoding="utf-8")
    (memory_dir / "MEMORY.md").write_text("saved note", encoding="utf-8")

    prompt = get_system_prompt(soul_path=soul_path, memory_dir=memory_dir)

    assert "base soul" in prompt
    assert "MEMORY SYSTEM (STAGE 1)" in prompt
    assert '"action": "write_memory"' in prompt
    assert "<MEMORY>" in prompt and "</MEMORY>" in prompt
    assert "saved note" in prompt
