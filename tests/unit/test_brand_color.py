from videoqa.checks.brand_color import check_brand_colors
from videoqa.config import load_rules

BRAND = {"palette": [{"name": "Negro", "hex": "#1A1A1A"}, {"name": "Blanco", "hex": "#FFFFFF"},
                     {"name": "Amarillo", "hex": "#F5C518"}]}

def app(text, color, t=2.0):
    return {"text": text, "bbox": [0.1, 0.4, 0.8, 0.1], "t_start": t, "t_end": t + 3,
            "frame": "frames/sec_0005.jpg", "frames": [], "color_hex": color}

def test_off_palette_color_is_blocker():
    fs = check_brand_colors([app("Aprobecha", "#FF3B30")], BRAND, load_rules())
    assert len(fs) == 1
    f = fs[0]
    assert f.severity == "blocker" and f.type == "marca" and f.check == "brand_color"
    assert "#FF3B30" in f.title and "#F5C518" in f.detail
    assert f.frame == "frames/sec_0005.jpg" and f.bbox == [0.1, 0.4, 0.8, 0.1] and f.t_start == 2.0

def test_near_palette_color_passes():
    assert check_brand_colors([app("Oferta", "#F4C41A")], BRAND, load_rules()) == []

def test_missing_color_or_palette_is_skipped():
    assert check_brand_colors([app("x", None)], BRAND, load_rules()) == []
    assert check_brand_colors([app("x", "#FF0000")], {"palette": []}, load_rules()) == []
