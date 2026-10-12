"""Pure tests for the confirmation-prefs settings law (ADR-117 §1, D1).

No DB, no LLM, no HTTP. The matrix locks the read tolerance (absent /
missing / unknown → ``auto``) and the one-key merge write (the rest of the
settings block survives).
"""

from app.platform.user_settings import (
    CONFIRM_MODES,
    DEFAULT_CONFIRM_MODE,
    merge_confirmation_pref,
    read_confirmation_prefs,
)


class TestReadConfirmationPrefs:
    def test_none_settings_reads_default(self):
        assert read_confirmation_prefs(None) == (DEFAULT_CONFIRM_MODE,) * 2

    def test_empty_settings_reads_default(self):
        assert read_confirmation_prefs({}) == ("auto", "auto")

    def test_unknown_value_reads_default(self):
        assert read_confirmation_prefs(
            {"confirm_execution": "sometimes", "confirm_credits": "never"}
        ) == ("auto", "auto")

    def test_each_valid_value_round_trips(self):
        for v in CONFIRM_MODES:
            assert read_confirmation_prefs(
                {"confirm_execution": v, "confirm_credits": v}
            ) == (v, v)

    def test_partial_keys_read_independently(self):
        assert read_confirmation_prefs({"confirm_execution": "ask"}) == ("ask", "auto")
        assert read_confirmation_prefs({"confirm_credits": "ask"}) == ("auto", "ask")

    def test_legacy_confirm_strategy_key_is_inert(self):
        # D7: the retired key is never read — it neither errors nor leaks.
        assert read_confirmation_prefs({"confirm_strategy": "never"}) == ("auto", "auto")


class TestMergeConfirmationPref:
    def test_merge_into_none(self):
        assert merge_confirmation_pref(None, "confirm_execution", "ask") == {
            "confirm_execution": "ask"
        }

    def test_other_keys_survive(self):
        merged = merge_confirmation_pref(
            {"theme": "dark", "confirm_credits": "ask"}, "confirm_execution", "ask"
        )
        assert merged == {
            "theme": "dark",
            "confirm_credits": "ask",
            "confirm_execution": "ask",
        }

    def test_input_dict_not_mutated(self):
        src = {"confirm_execution": "ask"}
        merge_confirmation_pref(src, "confirm_execution", "auto")
        assert src == {"confirm_execution": "ask"}
