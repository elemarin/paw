from paw.config import TelegramChannelConfig


def test_allow_from_parses_comma_separated_string() -> None:
    cfg = TelegramChannelConfig(allow_from="12345678, 98765432")
    assert cfg.allow_from == ["12345678", "98765432"]


def test_allow_from_parses_json_list_string() -> None:
    cfg = TelegramChannelConfig(allow_from='["12345678", "98765432"]')
    assert cfg.allow_from == ["12345678", "98765432"]
