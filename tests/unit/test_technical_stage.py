from videoqa.job import Job
from videoqa.stages.technical import (analyze, parse_astats, parse_black, parse_freeze,
                                       parse_scene, parse_silence)

BLACK = "[blackdetect @ 0x1] black_start:5 black_end:6.033 black_duration:1.033\n"
FREEZE = ("[freezedetect @ 0x1] lavfi.freezedetect.freeze_start: 5.0\n"
          "[freezedetect @ 0x1] lavfi.freezedetect.freeze_duration: 1.0\n"
          "[freezedetect @ 0x1] lavfi.freezedetect.freeze_end: 6.0\n")
SCENE = "[Parsed_showinfo_1 @ 0x1] n:   0 pts:  151 pts_time:5.033   pos: 1 fmt:yuv420p\n"
SILENCE = ("[silencedetect @ 0x1] silence_start: 2.1\n"
           "[silencedetect @ 0x1] silence_end: 4.6 | silence_duration: 2.5\n")
ASTATS = ("[Parsed_astats_1 @ 0x1] Channel: 1\n[Parsed_astats_1 @ 0x1] Peak level dB: -3.0\n"
          "[Parsed_astats_1 @ 0x1] Overall\n[Parsed_astats_1 @ 0x1] Peak level dB: -0.05\n"
          "[Parsed_astats_1 @ 0x1] Peak count: 250\n")


def test_parsers():
    assert parse_black(BLACK) == [{"start": 5.0, "end": 6.033}]
    assert parse_freeze(FREEZE) == [{"start": 5.0, "end": 6.0}]
    assert parse_scene(SCENE) == [5.033]
    assert parse_silence(SILENCE) == [{"start": 2.1, "end": 4.6}]
    assert parse_astats(ASTATS) == {"peak_db": -0.05, "peak_count": 250}


def test_analyze_black_screen_fixture(fixture_videos, tmp_path):
    t = analyze(Job(fixture_videos["black_screen"], tmp_path), has_audio=True, scene_threshold=0.2)
    assert any(4.8 <= b["start"] <= 5.2 and 5.8 <= b["end"] <= 6.2 for b in t["black"])
    assert t["audio"] is not None and "peak_db" in t["audio"]
    assert any(4.8 <= c <= 6.2 for c in t["scene_cuts"])


def test_analyze_no_audio_fixture(fixture_videos, tmp_path):
    t = analyze(Job(fixture_videos["no_audio"], tmp_path), has_audio=False, scene_threshold=0.3)
    assert t["audio"] is None and t["silence"] == []
