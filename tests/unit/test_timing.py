from videoqa.checks.timing import best_segment, check_desync, check_occluded, check_timing, check_visible_short
from videoqa.config import load_rules

R = load_rules()

def app(text="Oferta de verano", t0=1.0, t1=3.0, bbox=(0.1, 0.4, 0.5, 0.1)):
    return {"text": text, "bbox": list(bbox), "t_start": t0, "t_end": t1, "frame": "frames/a.jpg", "frames": []}

def test_visible_short():
    fs = check_visible_short([app(t0=1.0, t1=1.5), app(t0=2.0, t1=3.0)], R)
    assert len(fs) == 1 and fs[0].check == "text_visible_short" and fs[0].severity == "warning"

def test_occluded_bottom_and_right():
    fs = check_occluded([app(bbox=(0.1, 0.85, 0.5, 0.1)), app(bbox=(0.8, 0.4, 0.15, 0.1)), app()], R)
    assert len(fs) == 2 and all(f.check == "text_occluded" for f in fs)

def test_best_segment_jaccard():
    segs = [{"start": 0.0, "end": 2.0, "text": "Hola a todos"}, {"start": 2.0, "end": 5.0, "text": "aprovecha la oferta de verano"}]
    seg, score = best_segment("Oferta de verano", segs)
    assert seg is segs[1] and score >= 0.5
    assert best_segment("xyz", segs)[1] == 0.0

def test_desync_flags_only_matching_late_text():
    segs = [{"start": 2.0, "end": 5.0, "text": "aprovecha la oferta de verano"}]
    fs = check_desync([app(t0=4.0), app(text="Precio", t0=9.0)], segs, R)
    assert len(fs) == 1 and fs[0].check == "subtitle_desync" and "2.0" in fs[0].detail

def test_check_timing_combines():
    segs = [{"start": 2.0, "end": 5.0, "text": "aprovecha la oferta de verano"}]
    fs = check_timing([app(t0=4.0, t1=4.5, bbox=(0.1, 0.9, 0.5, 0.1))], segs, R)
    assert sorted(f.check for f in fs) == ["subtitle_desync", "text_occluded", "text_visible_short"]
