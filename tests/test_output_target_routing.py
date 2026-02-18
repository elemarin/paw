from paw.channels.manager import _parse_output_target


def test_parse_output_target_accepts_shorthand_channel() -> None:
    assert _parse_output_target("telegram") == "telegram"


def test_parse_output_target_ignores_qualifier() -> None:
    assert _parse_output_target("telegram:default") == "telegram"
    assert _parse_output_target("telegram:123456/77") == "telegram"


def test_parse_output_target_rejects_empty() -> None:
    assert _parse_output_target("") is None
    assert _parse_output_target("   ") is None
