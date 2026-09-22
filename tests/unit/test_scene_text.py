"""Texto de la escena (ropa, carteles) frente a rótulos de edición."""
from videoqa.checks.brand_color import check_brand_colors
from videoqa.checks.scene_text import is_scene_text
from videoqa.checks.spelling import check_spelling
from videoqa.checks.timing import check_timing
from videoqa.config import load_rules

R = load_rules()


class Todo_desconocido:
    def unknown(self, words):
        return set(words)

    def correction(self, word):
        return None


def app(text, motion=0.0, scale=1.0, bbox=(0.3, 0.9, 0.2, 0.03), t=19.0, dur=0.5):
    return {"text": text, "conf": 1.0, "bbox": list(bbox), "t_start": t, "t_end": t + dur,
            "frame": "frames/sec_0039.jpg", "frames": [], "color_hex": "#FF3B30",
            "motion": motion, "scale": scale}


def test_rotulo_fijo_no_es_texto_de_escena():
    assert not is_scene_text(app("Oferta"), R)
    assert not is_scene_text({"text": "sin campos de versiones viejas"}, R)


def test_texto_que_se_mueve_o_cambia_de_tamano_es_de_la_escena():
    assert is_scene_text(app("SUSHICD.", motion=0.08), R)
    assert is_scene_text(app("SUSHICD.", scale=1.6), R)


def test_ortografia_en_la_ropa_no_bloquea():
    fs = check_spelling([app("SUSHICD.", motion=0.08)], set(), R, checker=Todo_desconocido())
    assert len(fs) == 1 and fs[0].severity == "info"
    assert fs[0].detail.startswith("Texto de la escena")


def test_ortografia_en_rotulo_sigue_bloqueando():
    fs = check_spelling([app("SUSHICD.")], set(), R, checker=Todo_desconocido())
    assert fs[0].severity == "blocker"


def test_color_y_timing_ignoran_el_texto_de_la_escena():
    brand = {"palette": [{"hex": "#FFFFFF"}]}
    assert check_brand_colors([app("SUSHI CD", motion=0.08)], brand, R) == []
    assert check_timing([app("SUSHI CD", motion=0.08)], [], R) == []
    assert check_timing([app("SUSHI CD")], [], R) != []  # el mismo texto fijo sí se revisa
