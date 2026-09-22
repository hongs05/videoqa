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


class Diccionario:
    """Diccionario pequeño de español: lo que no está aquí es 'desconocido'."""
    WORDS = {"así", "es", "como", "cómo", "vamos", "en", "un", "día", "mes", "el", "itinerario",
             "la", "cocina", "para", "nuestro", "negocio", "de", "mejor", "momento", "cacao", "con", "café"}

    def unknown(self, words):
        return {w for w in words if w.lower() not in self.WORDS}

    def correction(self, word):
        return None


D = Diccionario()


def seg(text, start=0.0, end=60.0):
    return {"start": start, "end": end, "text": text}


def test_palabras_pegadas_por_el_ocr_no_bloquean():
    """Casos reales: el OCR de Vision pierde los espacios en subtítulos apretados."""
    for texto in ("Yasíescomo", "¿Cómovamosa", "unmesenundía.", "para lacocina", "nuestronegocio.", "Elmejor momento."):
        fs = check_spelling([app(texto)], set(), R, checker=D)
        assert [f.check for f in fs if f.severity == "blocker"] == [], texto
        assert any(f.check == "spelling_glued_words" and f.severity == "info" for f in fs), texto


def test_palabras_pegadas_sugieren_la_separacion():
    fs = check_spelling([app("Yasíescomo")], set(), R, checker=D)
    assert '"y así es como"' in fs[0].suggestion


def test_palabra_que_whisper_transcribe_igual_es_valida():
    """'Mojito', 'backdrops', 'Stay': el talento lo dice y Whisper lo escribe igual."""
    fs = check_spelling([app("Mojito"), app("backdrops, después"), app("Stay tu")], set(), R, checker=D,
                        segments=[seg("un mojito con backdrops, stay tuned")])
    assert [f for f in fs if f.check == "spelling_unknown_word" and ("Mojito" in f.title or "backdrops" in f.title
                                                                        or "Stay" in f.title)] == []


def test_trozo_de_subtitulo_animado_no_es_falta():
    """El frame cazó 'cocktails' a medio aparecer: 'ocktails', 'tails'."""
    fs = check_spelling([app("ocktails", t=10.0), app("tails", t=10.5), app("cocktails", t=11.0, dur=1.0)],
                        {"cocktails"}, R, checker=D)
    assert fs == []


def test_trozo_de_una_palabra_dicha_en_ese_momento():
    fs = check_spelling([app("ocktails", t=10.0)], set(), R, checker=D, segments=[seg("unos cocktails", 9.5, 11.0)])
    assert fs == []


def test_la_tilde_que_falta_sigue_bloqueando_aunque_se_diga_la_palabra():
    """'cafe' no está en el transcript ('café'): no se confunde con un trozo ni se da por buena."""
    fs = check_spelling([app("con cacao + cafe")], set(), R, checker=D, segments=[seg("con cacao y café")])
    assert [f.title for f in fs] == ["Posible error ortográfico: cafe"] and fs[0].severity == "blocker"


def test_falta_real_sigue_bloqueando():
    fs = check_spelling([app("IMPORTANTI")], set(), R, checker=D)
    assert fs[0].severity == "blocker"


def test_falta_real_no_se_confunde_con_palabras_pegadas():
    class Permisivo:  # como NSSpellChecker: acepta abreviaturas y trozos raros de 2-3 letras
        KNOWN = {"la", "casa", "ka", "sa", "kas", "yo", "no", "se", "si", "a", "otros", "importan", "ti", "tan"}

        def unknown(self, words):
            return {w for w in words if w.lower() not in self.KNOWN}

        def correction(self, word):
            return None

    for texto in ("la kasa", "Yo no se sia otros", "IMPORTANTI", "la casaa"):
        fs = check_spelling([app(texto)], set(), R, checker=Permisivo())
        assert [f.severity for f in fs if f.check == "spelling_unknown_word"] == ["blocker"], texto
