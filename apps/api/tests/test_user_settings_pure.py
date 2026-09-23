"""Pure tests for the confirm_strategy settings law (ADR-092 §1, E5 — S4).

No DB, no LLM, no HTTP. The matrix locks the read tolerance (absent /
missing / unknown → the default) and the one-key merge write (the rest of
the settings block survives).
"""

from app.platform.user_settings import (
    CONFIRM_STRATEGIES,
    DEFAULT_CONFIRM_STRATEGY,
    merge_confirm_strategy,
    read_confirm_strategy,
)


class TestReadConfirmStrategy:
    def test_none_settings_reads_default(self):
        assert read_confirm_strategy(None) == DEFAULT_CONFIRM_STRATEGY

    def test_empty_settings_reads_default(self):
        assert read_confirm_strategy({}) == DEFAULT_CONFIRM_STRATEGY

    def test_unknown_value_reads_default(self):
        assert read_confirm_strategy({"confirm_strategy": "sometimes"}) == DEFAULT_CONFIRM_STRATEGY

    def test_each_valid_value_round_trips(self):
        for v in CONFIRM_STRATEGIES:
            assert read_confirm_strategy({"confirm_strategy": v}) == v


class TestMergeConfirmStrategy:
    def test_merge_into_none(self):
        assert merge_confirm_strategy(None, "always") == {"confirm_strategy": "always"}

    def test_other_keys_survive(self):
        merged = merge_confirm_strategy({"theme": "dark", "confirm_strategy": "never"}, "large")
        assert merged == {"theme": "dark", "confirm_strategy": "large"}

    def test_input_dict_not_mutated(self):
        src = {"confirm_strategy": "never"}
        merge_confirm_strategy(src, "always")
        assert src == {"confirm_strategy": "never"}
