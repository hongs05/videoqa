from PIL import Image, ImageDraw
from videoqa.stages.color import dominant_text_color, add_colors

def synthetic(bg, fg):
    img = Image.new("RGB", (400, 200), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([120, 80, 280, 120], fill=fg)  # "texto" = barra central
    return img

def test_white_on_black():
    assert dominant_text_color(synthetic((0, 0, 0), (255, 255, 255)), [0.25, 0.35, 0.5, 0.3]) == "#FFFFFF"

def test_red_on_dark():
    assert dominant_text_color(synthetic((26, 26, 26), (255, 59, 48)), [0.25, 0.35, 0.5, 0.3]) == "#FF3B30"

def test_uniform_box_returns_none():
    assert dominant_text_color(Image.new("RGB", (100, 100), (10, 10, 10)), [0, 0, 1, 1]) is None

def test_add_colors_annotates_appearances(tmp_path):
    from videoqa.job import Job
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    (job.dir / "frames").mkdir()
    synthetic((0, 0, 0), (245, 197, 24)).save(job.path("frames/a.jpg"), quality=95)
    ocr = {"raw": [], "appearances": [{"text": "x", "bbox": [0.25, 0.35, 0.5, 0.3], "t_start": 0, "t_end": 1,
                                        "frame": "frames/a.jpg", "frames": ["frames/a.jpg"]}]}
    out = add_colors(job, ocr)
    assert out["appearances"][0]["color_hex"].startswith("#F")
