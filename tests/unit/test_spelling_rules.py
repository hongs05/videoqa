"""Reglas de ortografía que no dependen del diccionario de macOS (corrector falso)."""
from videoqa.checks.spelling import check_spelling, unknown_words
from videoqa.config import load_rules

R = load_rules()


class FakeChecker:
    KNOWN = {"sabías", "que", "esto", "funciona", "espera", "luego", "síguenos", "visita",
             "hola", "mundo", "oferta", "vienes", "preguntó"}

    def unknown(self, words):
        return {w for w in words if w.lower() not in self.KNOWN}

    def correction(self, word):
        return None


C = FakeChecker()


def app(text, t=1.0, dur=2.0):
    return {"text": text, "bbox": [0.1, 0.4, 0.8, 0.1], "t_start": t, "t_end": t + dur,
            "frame": "frames/sec_0003.jpg", "frames": []}


def test_urls_usuarios_y_hashtags_no_se_revisan():
    assert unknown_words("Síguenos @tiendamx #ofertazo visita www.tiendamx.com", C, set()) == []
    assert unknown_words("visita tiendamx.com/promo o hola@tiendamx.com", C, set()) == []


def test_signo_de_apertura_en_otra_linea_simultanea():
    fs = check_spelling([app("¿Sabías que"), app("esto funciona?")], set(), R, checker=C)
    assert fs == []


def test_signo_de_apertura_ausente_se_sigue_marcando():
    fs = check_spelling([app("esto funciona?")], set(), R, checker=C)
    assert [f.title for f in fs] == ["Puntuación: falta el signo de apertura ¿"]


def test_puntos_suspensivos_no_son_minuscula_tras_punto():
    assert check_spelling([app("Espera... luego")], set(), R, checker=C) == []
    fs = check_spelling([app("Hola. mundo")], set(), R, checker=C)
    assert [f.title for f in fs] == ["Puntuación: minúscula después de punto"]


def test_mismo_error_repetido_da_un_solo_hallazgo():
    fs = check_spelling([app("Ofrta", 1.0), app("Ofrta", 5.0), app("OFRTA hola", 9.0)], set(), R, checker=C)
    assert len(fs) == 1 and fs[0].t_start == 1.0
    assert "5.0 s" in fs[0].detail and "9.0 s" in fs[0].detail
