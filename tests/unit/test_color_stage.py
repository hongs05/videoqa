from PIL import Image, ImageDraw
from videoqa.checks.colors import hex_delta_e
from videoqa.stages.color import dominant_text_color, add_colors, text_colors

def synthetic(bg, fg):
    img = Image.new("RGB", (400, 200), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([120, 80, 280, 120], fill=fg)  # "texto" = barra central
    return img

def outlined(bg, fill, outline, width=4):
    """Barra de 'texto' con contorno, como un subtítulo blanco con borde negro."""
    img = Image.new("RGB", (400, 200), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([120 - width, 80 - width, 280 + width, 120 + width], fill=outline)
    d.rectangle([120, 80, 280, 120], fill=fill)
    return img

def test_white_on_black():
    assert dominant_text_color(synthetic((0, 0, 0), (255, 255, 255)), [0.25, 0.35, 0.5, 0.3]) == "#FFFFFF"

def test_red_on_dark():
    assert dominant_text_color(synthetic((26, 26, 26), (255, 59, 48)), [0.25, 0.35, 0.5, 0.3]) == "#FF3B30"

def test_uniform_box_returns_none():
    assert dominant_text_color(Image.new("RGB", (100, 100), (10, 10, 10)), [0, 0, 1, 1]) is None
    assert text_colors(Image.new("RGB", (100, 100), (10, 10, 10)), [0, 0, 1, 1]) == []

def test_text_colors_single_ink():
    assert text_colors(synthetic((0, 0, 0), (255, 255, 255)), [0.25, 0.35, 0.5, 0.3]) == ["#FFFFFF"]

def test_text_colors_detects_fill_and_outline():
    """Subtítulo blanco con borde negro sobre azul: dos tintas, no un gris inventado."""
    img = outlined((0, 0, 200), (255, 255, 255), (0, 0, 0))
    colors = text_colors(img, [0.25, 0.33, 0.5, 0.35])
    assert len(colors) == 2
    assert hex_delta_e(colors[0], "#FFFFFF") < 5      # el relleno es el más poblado
    assert hex_delta_e(colors[1], "#000000") < 5

def test_add_colors_exposes_candidates(tmp_path):
    from videoqa.job import Job
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    (job.dir / "frames").mkdir()
    outlined((0, 0, 200), (255, 255, 255), (0, 0, 0)).save(job.path("frames/o.png"))
    ocr = {"raw": [], "appearances": [{"text": "x", "bbox": [0.25, 0.33, 0.5, 0.35], "t_start": 0, "t_end": 1,
                                        "frame": "frames/o.png", "frames": ["frames/o.png"]}]}
    app = add_colors(job, ocr)["appearances"][0]
    assert len(app["color_candidates"]) == 2
    assert app["color_hex"] == app["color_candidates"][0]
    assert hex_delta_e(app["color_hex"], "#FFFFFF") < 5

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
