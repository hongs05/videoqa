from videoqa.checks.technical import check_technical
from videoqa.config import load_rules

R = load_rules()
PROBE = {"duration": 12.0, "width": 1080, "height": 1920, "fps": 30.0, "has_audio": True}
EMPTY = {"black": [], "freeze": [], "scene_cuts": [], "silence": [], "audio": {"peak_db": -3.0, "peak_count": 0}}

def test_clean_has_no_findings():
    assert check_technical(PROBE, EMPTY, R) == []

def test_black_in_middle_is_blocker_but_edges_ignored():
    t = dict(EMPTY, black=[{"start": 5.0, "end": 6.0}, {"start": 0.0, "end": 0.3}, {"start": 11.7, "end": 12.0}])
    fs = check_technical(PROBE, t, R)
    assert [f.check for f in fs] == ["black_frame"] and fs[0].severity == "blocker" and fs[0].t_start == 5.0

def test_freeze_overlapping_black_is_deduped():
    t = dict(EMPTY, black=[{"start": 5.0, "end": 6.0}], freeze=[{"start": 5.0, "end": 6.0}, {"start": 8.0, "end": 9.0}])
    assert sorted(f.check for f in check_technical(PROBE, t, R)) == ["black_frame", "frozen_frame"]

def test_silence_clipping_aspect_no_audio():
    t = dict(EMPTY, silence=[{"start": 3.0, "end": 6.0}], audio={"peak_db": 0.0, "peak_count": 500})
    p = dict(PROBE, width=1920, height=1080, has_audio=False)
    checks = sorted(f.check for f in check_technical(p, t, R))
    assert checks == ["aspect_ratio", "audio_clipping", "no_audio", "silence"]
