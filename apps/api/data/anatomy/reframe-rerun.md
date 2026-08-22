# craft anatomy report

## out-9abb4a6f (talking_head) md5=1fb65f26

| metric | value | prior (先验) | verdict |
|---|---|---|---|
| duration_s | 91.776 | — | info |
| integrated_loudness_lufs | -16.14 | voice (-15.0, -13.0) LUFS (-14 ±1) | info |
| lead_silence_s | 0.0 | hook ≤0.3s | ok |
| silence_runs | `{"count": 2, "total_s": 0.3}` | — | info |
| hook_delay_s | 0.0 | ≤0.3 | ok |
| cut_boundaries | `[{"seg": 0, "pre_pad_s": 0.0, "post_pad_s": 0.0, "pause_available_before_s": 0.0, "pause_available_after_s": 1.16, "in_nearest_boundary_s": 1.74, "mid_word_cut"` | in-pad (0.1, 0.15), out-pad (0.15, 0.2); edge within ±0.18s of a clause boundary | info |
| dead_air | `{"count": 4, "runs": [{"at": 262.58, "gap_s": 0.8}, {"at": 273.56, "gap_s": 1.62}, {"at": 276.46, "gap_s": 0.98}, {"at": 284.3, "gap_s": 0.74}]}` | pauses >0.6–0.8s removed | gap |
| filler_kept | `{"count": 1, "tokens": ["就是"]}` | um/uh-class fillers removed (intentional beats excepted) | gap |
| emphasis_events | `{"spec_events": 0, "audio_energy_peaks": 18}` | emphasis aligned to pitch/energy peaks | gap |
| caption_rhythm | `{"cue_level": "word", "words_per_line": 7, "line_dur_median_s": 2.31, "line_dur_max_s": 4.24, "line_chars_median": 14.5, "line_chars_p90": 16.300000000000004}` | karaoke bursts (1, 3) words / (0.2, 0.8)s; or phrase ≤2 lines 32–42 chars | info |
| cut_frequency | `{"intervals_s": [36.14, 9.86, 45.72], "max_static_s": 45.72, "sub_1s_switches": 0, "keyframe_deltas": [0.7357, 0.6713], "keyframes_perceptual": 2}` | no >2 consecutive cuts <1s; no static shot >(8.0, 10.0)s | gap |
| end_hold_s | 0.0 | ≥1.8s | gap |
| eye_line_y | `{"median": 0.4048269192377726, "p10": 0.39764601389567056, "p90": 0.41265459219614664}` | (0.35, 0.45) of frame height | ok |
| face_width | `{"median": 0.2472856874819155, "p10": 0.22911729883264612, "p90": 0.2651006458423756}` | (0.3, 0.5) of frame width | gap |

## out-c935958e (talking_head) md5=be8a7f59

| metric | value | prior (先验) | verdict |
|---|---|---|---|
| duration_s | 70.187 | — | info |
| integrated_loudness_lufs | -16.18 | voice (-15.0, -13.0) LUFS (-14 ±1) | info |
| lead_silence_s | 0.0 | hook ≤0.3s | ok |
| silence_runs | `{"count": 0, "total_s": 0}` | — | info |
| hook_delay_s | 0.0 | ≤0.3 | ok |
| cut_boundaries | `[{"seg": 0, "pre_pad_s": 0.0, "post_pad_s": 0.0, "pause_available_before_s": 0.0, "pause_available_after_s": 0.28, "in_nearest_boundary_s": 8.64, "mid_word_cut"` | in-pad (0.1, 0.15), out-pad (0.15, 0.2); edge within ±0.18s of a clause boundary | info |
| dead_air | `{"count": 3, "runs": [{"at": 48.92, "gap_s": 0.84}, {"at": 62.8, "gap_s": 0.98}, {"at": 89.68, "gap_s": 0.7}]}` | pauses >0.6–0.8s removed | gap |
| filler_kept | `{"count": 0, "tokens": []}` | um/uh-class fillers removed (intentional beats excepted) | ok |
| emphasis_events | `{"spec_events": 0, "audio_energy_peaks": 17}` | emphasis aligned to pitch/energy peaks | gap |
| caption_rhythm | `{"cue_level": "word", "words_per_line": 7, "line_dur_median_s": 2.34, "line_dur_max_s": 4.38, "line_chars_median": 14.0, "line_chars_p90": 15.400000000000002}` | karaoke bursts (1, 3) words / (0.2, 0.8)s; or phrase ≤2 lines 32–42 chars | info |
| cut_frequency | `{"intervals_s": [70.12], "max_static_s": 70.12, "sub_1s_switches": 0, "keyframe_deltas": [], "keyframes_perceptual": 0}` | no >2 consecutive cuts <1s; no static shot >(8.0, 10.0)s | gap |
| end_hold_s | 0.0 | ≥1.8s | gap |
| eye_line_y | `{"median": 0.389098072052002, "p10": 0.3842361609141032, "p90": 0.40273979504903157}` | (0.35, 0.45) of frame height | ok |
| face_width | `{"median": 0.2502381218804253, "p10": 0.2219702402750651, "p90": 0.27014244927300346}` | (0.3, 0.5) of frame width | gap |

## out-97f11cc1 (talking_head) md5=9b2e632d

| metric | value | prior (先验) | verdict |
|---|---|---|---|
| duration_s | 113.088 | — | info |
| integrated_loudness_lufs | -16.26 | voice (-15.0, -13.0) LUFS (-14 ±1) | info |
| lead_silence_s | 0.0 | hook ≤0.3s | ok |
| silence_runs | `{"count": 1, "total_s": 0.2}` | — | info |
| hook_delay_s | 0.0 | ≤0.3 | ok |
| cut_boundaries | `[{"seg": 0, "pre_pad_s": 0.0, "post_pad_s": 0.0, "pause_available_before_s": 1.66, "pause_available_after_s": 0.82, "in_nearest_boundary_s": 1.66, "mid_word_cut` | in-pad (0.1, 0.15), out-pad (0.15, 0.2); edge within ±0.18s of a clause boundary | info |
| dead_air | `{"count": 4, "runs": [{"at": 144.7, "gap_s": 0.68}, {"at": 163.24, "gap_s": 1.62}, {"at": 178.3, "gap_s": 0.78}, {"at": 185.22, "gap_s": 2.32}]}` | pauses >0.6–0.8s removed | gap |
| filler_kept | `{"count": 0, "tokens": []}` | um/uh-class fillers removed (intentional beats excepted) | ok |
| emphasis_events | `{"spec_events": 0, "audio_energy_peaks": 29}` | emphasis aligned to pitch/energy peaks | gap |
| caption_rhythm | `{"cue_level": "word", "words_per_line": 7, "line_dur_median_s": 2.35, "line_dur_max_s": 6.2, "line_chars_median": 14.0, "line_chars_p90": 16.0}` | karaoke bursts (1, 3) words / (0.2, 0.8)s; or phrase ≤2 lines 32–42 chars | info |
| cut_frequency | `{"intervals_s": [62.54, 14.22, 8.46, 27.82], "max_static_s": 62.54, "sub_1s_switches": 0, "keyframe_deltas": [0.7357, 0.6713, 0.7357], "keyframes_perceptual": 3` | no >2 consecutive cuts <1s; no static shot >(8.0, 10.0)s | gap |
| end_hold_s | 0.0 | ≥1.8s | gap |
| eye_line_y | `{"median": 0.39432226022084554, "p10": 0.3814689286549886, "p90": 0.40758179187774657}` | (0.35, 0.45) of frame height | ok |
| face_width | `{"median": 0.25232880203812214, "p10": 0.2232670748675311, "p90": 0.26984514024522566}` | (0.3, 0.5) of frame width | gap |
