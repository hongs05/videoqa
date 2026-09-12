from videoqa.job import Job
from videoqa.stages.frames import extract_frames
from videoqa.stages.ocr import dedupe, iou, norm_text, ocr_frame, ocr_frames

def item(text, t, bbox=(0.2, 0.45, 0.6, 0.1), conf=0.9):
    return {"file": f"frames/{t}.jpg", "t": t, "items": [{"text": text, "conf": conf, "bbox": list(bbox)}]}

def test_iou_and_norm():
    assert iou([0, 0, 1, 1], [0, 0, 1, 1]) == 1.0
    assert iou([0, 0, 1, 1], [2, 2, 1, 1]) == 0.0
    assert norm_text("  Hola   MUNDO ") == "hola mundo"

def test_dedupe_merges_consecutive_frames_same_text():
    raw = [item("Oferta", 1.0), item("Oferta", 1.5), item("Oferta", 2.0), item("Otra", 3.0)]
    apps = dedupe(raw, period=0.5)
    assert len(apps) == 2
    assert apps[0]["text"] == "Oferta" and apps[0]["t_start"] == 1.0 and apps[0]["t_end"] == 2.5
    assert apps[0]["frame"] == "frames/1.0.jpg" and len(apps[0]["frames"]) == 3
    assert apps[1]["t_start"] == 3.0 and apps[1]["t_end"] == 3.5

def test_dedupe_splits_after_gap():
    raw = [item("Oferta", 1.0), item("Oferta", 5.0)]
    assert len(dedupe(raw, period=0.5)) == 2

def test_dedupe_keeps_highest_confidence_text():
    raw = [item("0ferta", 1.0, conf=0.5), item("Oferta", 1.5, conf=0.95)]
    assert dedupe(raw, period=0.5)[0]["text"] == "Oferta"

def test_dedupe_does_not_merge_differing_digits_in_percentage():
    raw = [item("descuento del 20%", 1.0), item("descuento del 25%", 1.5)]
    assert len(dedupe(raw, period=0.5)) == 2

def test_dedupe_does_not_merge_differing_digits_in_date():
    raw = [item("martes 12", 1.0), item("martes 13", 1.5)]
    assert len(dedupe(raw, period=0.5)) == 2

def test_dedupe_does_not_merge_differing_digits_in_step_counter():
    raw = [item("paso 2 de 5", 1.0), item("paso 3 de 5", 1.5)]
    assert len(dedupe(raw, period=0.5)) == 2

def test_ocr_frame_reads_fixture_text(fixture_videos, tmp_path):
    job = Job(fixture_videos["clean"], tmp_path)
    fr = extract_frames(job, scene_cuts=[], fps=2)
    frame_at_5s = next(f for f in fr["frames"] if f["t"] == 5.0)
    items = ocr_frame(job.path(frame_at_5s["file"]))
    texts = " ".join(norm_text(i["text"]) for i in items)
    assert "oferta de verano" in texts
    target = next(i for i in items if "oferta" in norm_text(i["text"]))
    x, y, w, h = target["bbox"]
    assert 0.3 < y < 0.6 and 0 < w <= 1 and 0 < h < 0.2  # centrado verticalmente, origen arriba

def test_ocr_frames_builds_appearances(fixture_videos, tmp_path):
    job = Job(fixture_videos["clean"], tmp_path)
    fr = extract_frames(job, scene_cuts=[], fps=2)
    out = ocr_frames(job, fr["frames"], period=fr["period"])
    apps = [a for a in out["appearances"] if "oferta" in norm_text(a["text"])]
    assert len(apps) == 1
    assert 0.5 <= apps[0]["t_start"] <= 1.5 and 9.5 <= apps[0]["t_end"] <= 10.5
