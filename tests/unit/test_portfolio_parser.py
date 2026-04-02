"""Unit tests for trade action email parser."""
from __future__ import annotations


from packages.portfolio.parser import parse_action


class TestParseAction:
    def test_buy_basic(self):
        parsed = parse_action("BUY 10 AAPL")
        assert parsed.action_type == "BUY"
        assert parsed.instrument == "AAPL"
        assert parsed.quantity == 10.0
        assert parsed.price is None

    def test_buy_with_price(self):
        parsed = parse_action("BUY 10 AAPL @ 180.50")
        assert parsed.action_type == "BUY"
        assert parsed.instrument == "AAPL"
        assert parsed.quantity == 10.0
        assert parsed.price == 180.50

    def test_sell_basic(self):
        parsed = parse_action("SELL 5 NVDA")
        assert parsed.action_type == "SELL"
        assert parsed.instrument == "NVDA"
        assert parsed.quantity == 5.0

    def test_sell_with_price(self):
        parsed = parse_action("SELL 5 NVDA @ 950.00")
        assert parsed.action_type == "SELL"
        assert parsed.price == 950.0

    def test_case_insensitive(self):
        parsed = parse_action("buy 10 tsla @ 200")
        assert parsed.action_type == "BUY"
        assert parsed.instrument == "TSLA"

    def test_note_command(self):
        parsed = parse_action("NOTE: watching energy sector due to OPEC meeting")
        assert parsed.action_type == "NOTE"
        assert "energy sector" in parsed.notes

    def test_position_command(self):
        parsed = parse_action("POSITION")
        assert parsed.action_type == "POSITION"

    def test_help_command(self):
        parsed = parse_action("HELP")
        assert parsed.action_type == "HELP"

    def test_question_fallback(self):
        parsed = parse_action("What is the outlook for TSLA?")
        assert parsed.action_type == "QUESTION"
        assert parsed.notes

    def test_fractional_quantity(self):
        parsed = parse_action("BUY 0.5 BTC-USD @ 65000")
        assert parsed.quantity == 0.5

    def test_raw_text_preserved(self):
        raw = "BUY 10 AAPL @ 180"
        parsed = parse_action(raw)
        assert parsed.raw_text == raw

    def test_multiline_first_command_parsed(self):
        text = "BUY 10 AAPL @ 180\nsome trailing text"
        parsed = parse_action(text)
        assert parsed.action_type == "BUY"
        assert parsed.instrument == "AAPL"

    def test_buy_instrument_uppercase(self):
        parsed = parse_action("BUY 100 aapl")
        assert parsed.instrument == "AAPL"
