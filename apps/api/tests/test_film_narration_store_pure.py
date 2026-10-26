"""Narration reuse identity and bounded adaptation guards.

The current implementation lives under tools/film until the video execution
layer replaces it. These content/config identity guards remain valid; retarget
imports in that implementation batch, without preserving old timeline flex.
"""

from app.providers import voice
from app.tools.film.narration_store import (
    NarrationReuse,
    adaptation_speed,
    narration_content_hash,
    narration_synth_config,
)

_CFG = narration_synth_config()


def _hash(text="Hello world", voice_id="presenter_male", language="en", config=None):
    return narration_content_hash(
        text=text, voice_id=voice_id, language=language, config=config or _CFG
    )


# --- 复用键 = 实际合成配置 -----------------------------------------------


def test_content_hash_is_deterministic_and_hex():
    content_hash, config_hash = _hash()
    assert content_hash == _hash()[0]
    assert len(content_hash) == 64 and len(config_hash) == 64
    int(content_hash, 16)  # hex


def test_content_hash_text_participates_normalized():
    # Whitespace-collapsed: visual formatting never forks the identity.
    assert _hash(text="Hello   world\n")[0] == _hash(text="Hello world")[0]
    # …but real text moves it.
    assert _hash(text="Hello world!")[0] != _hash(text="Hello world")[0]


def test_content_hash_voice_language_config_all_participate():
    base = _hash()[0]
    assert _hash(voice_id="presenter_female")[0] != base
    assert _hash(language="zh")[0] != base
    assert _hash(config={**_CFG, "sample_rate": 24000})[0] != base


def test_content_hash_config_key_order_never_matters():
    reordered = dict(reversed(list(_CFG.items())))
    assert _hash(config=reordered) == _hash()


def test_synth_config_pins_speed_base_original_and_follows_model():
    # The store holds speed-1.0 originals only — adaptation is a runtime
    # transform and never enters the identity.
    assert _CFG["speed_base"] == 1.0
    # The model fact rides the provider seat: a model move rehashes every
    # line (old originals stop matching, never silently reused).
    assert _CFG["model"] == voice.tts_model()
    cfg_b = {**_CFG, "model": "speech-next"}
    assert _hash(config=cfg_b)[0] != _hash()[0]


# --- 适配是运行期变换 -----------------------------------------------------


def test_adaptation_fit_needs_no_transform():
    assert adaptation_speed(duration_s=4.0, window_s=4.0, speed_max=1.35) is None
    assert adaptation_speed(duration_s=3.9, window_s=4.0, speed_max=1.35) is None


def test_adaptation_unfit_returns_provider_speed_capped():
    # 5.4s into a 4.0s window = 1.35× — exactly at the cap.
    assert adaptation_speed(duration_s=5.4, window_s=4.0, speed_max=1.35) == 1.35
    # Mild overrun: the honest needed speed, under the cap.
    speed = adaptation_speed(duration_s=4.4, window_s=4.0, speed_max=1.35)
    assert speed is not None and abs(speed - 1.1) < 1e-9
    # Beyond the cap: return the cap itself — the caller's flex /
    # honest-failure law owns the terminal shape, never a silent fit claim.
    assert adaptation_speed(duration_s=8.0, window_s=4.0, speed_max=1.35) == 1.35


def test_adaptation_zero_window_is_guarded():
    # A degenerate window never divides by zero; the floor keeps the
    # decision shaped (and lands at the cap — nothing fits a zero window).
    assert adaptation_speed(duration_s=1.0, window_s=0.0, speed_max=1.35) == 1.35


# --- 复用答形态 -----------------------------------------------------------


def test_reuse_answer_shape():
    assert NarrationReuse("k", 1.0, None).reusable
    assert not NarrationReuse(None, None, "owner-token").reusable
    assert not NarrationReuse(None, None, None).reusable
