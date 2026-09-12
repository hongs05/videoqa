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


PAL2 = {"palette": [{"name": "Blanco", "hex": "#FFFFFF"}, {"name": "Negro", "hex": "#1A1A1A"}]}


def test_outlined_text_passes_when_any_candidate_is_in_palette():
    """Relleno blanco + contorno: basta con que UNA de las tintas esté en paleta."""
    a = app("¡Era mi almuerzo!", "#847C6E")
    a["color_candidates"] = ["#847C6E", "#FFFFFF"]
    assert check_brand_colors([a], PAL2, load_rules()) == []


def test_all_candidates_off_palette_is_still_a_blocker():
    a = app("¡Era mi almuerzo!", "#FF3B30")
    a["color_candidates"] = ["#FF3B30"]
    fs = check_brand_colors([a], PAL2, load_rules())
    assert len(fs) == 1 and fs[0].severity == "blocker"
    assert "#FF3B30" in fs[0].detail


def test_detail_lists_every_candidate():
    a = app("x", "#FF3B30")
    a["color_candidates"] = ["#FF3B30", "#00A000"]
    fs = check_brand_colors([a], PAL2, load_rules())
    assert "#FF3B30" in fs[0].detail and "#00A000" in fs[0].detail


def test_low_confidence_appearance_is_skipped():
    """'nka' (escudo bordado leído por el OCR con conf 0.3) no es un rótulo."""
    a = app("nka", "#FF3B30"); a["conf"] = 0.3
    assert check_brand_colors([a], BRAND, load_rules()) == []
    b = app("nka", "#FF3B30"); b["conf"] = 0.9
    assert len(check_brand_colors([b], BRAND, load_rules())) == 1
