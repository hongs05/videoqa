from videoqa.checks.spelling import (BASE_GLOSSARY_PATH, MacSpellChecker, _Vocab, check_spelling,
                                     in_glossary, load_base_glossary, load_glossary, unknown_words)
from videoqa.config import load_rules

CHECKER = MacSpellChecker()

def app(text, t=1.0):
    return {"text": text, "bbox": [0.1, 0.4, 0.8, 0.1], "t_start": t, "t_end": t + 2,
            "frame": "frames/sec_0003.jpg", "frames": []}

def test_load_glossary_missing_file(tmp_path):
    # Desde Task 2, load_glossary suma siempre el glosario base empaquetado; sin
    # incluir_base=False, un archivo del equipo inexistente ya no devuelve set() vacío.
    assert load_glossary(tmp_path / "no.txt", incluir_base=False) == set()

def test_load_glossary_lowercases(tmp_path):
    p = tmp_path / "g.txt"; p.write_text("VideoQA\n# comentario\n\nTikTok\n")
    # incluir_base=False para comprobar solo lo que aporta el archivo del equipo.
    assert load_glossary(p, incluir_base=False) == {"videoqa", "tiktok"}

def test_unknown_words_respects_glossary_caps_and_short():
    assert unknown_words("Aprobecha la oferta en TikTok", CHECKER, {"tiktok"}) == ["Aprobecha"]
    assert unknown_words("IVA de 21", CHECKER, set()) == []          # siglas y números
    assert unknown_words("Aprovecha la oferta", CHECKER, set()) == []

def test_unknown_words_detects_all_caps_misspelling():
    # Los rótulos de reels van en MAYÚSCULAS: saltarlas dejaba el check ciego.
    assert unknown_words("APROBECHA LA OFERTA", CHECKER, set()) == ["APROBECHA"]

def test_is_known_direct():
    assert CHECKER.is_known("aprovecha") is True
    assert CHECKER.is_known("quieres") is True
    assert CHECKER.is_known("APROVECHA") is True
    assert CHECKER.is_known("OFERTA") is True
    assert CHECKER.is_known("IVA") is True          # sigla común
    assert CHECKER.is_known("kasa") is False
    assert CHECKER.is_known("aprobecha") is False
    assert CHECKER.is_known("APROBECHA") is False

def test_check_spelling_blocker_with_suggestion():
    fs = check_spelling([app("Aprobecha la oferta")], set(), load_rules(), checker=CHECKER)
    assert len(fs) == 1 and fs[0].severity == "blocker" and fs[0].type == "ortografia"
    assert "Aprobecha" in fs[0].title and "aprovecha" in fs[0].suggestion.lower()
    assert fs[0].check == "spelling_unknown_word"

def test_punctuation_warnings():
    fs = check_spelling([app("Quieres ahorrar?"), app("Hola  mundo")], set(), load_rules(), checker=CHECKER)
    checks = sorted(f.check for f in fs)
    assert checks == ["spelling_punctuation", "spelling_punctuation"]
    assert all(f.severity == "warning" for f in fs)

def test_lowercase_after_period_is_flagged():
    fs = check_spelling([app("Hola. mundo")], set(), load_rules(), checker=CHECKER)
    puncts = [f for f in fs if f.check == "spelling_punctuation"]
    assert len(puncts) == 1 and "minúscula después de punto" in puncts[0].title

def test_decimal_number_is_not_a_punctuation_issue():
    fs = check_spelling([app("Precio 3.5 euros")], set(), load_rules(), checker=CHECKER)
    assert [f for f in fs if f.check == "spelling_punctuation"] == []

def test_low_confidence_appearance_is_not_spellchecked():
    """El OCR lee bordados del vestuario ('nka', conf 0.3): no son texto del video."""
    a = app("nka"); a["conf"] = 0.3
    assert check_spelling([a], set(), load_rules(), checker=CHECKER) == []


def test_high_confidence_appearance_is_spellchecked():
    a = app("nka"); a["conf"] = 0.9
    fs = check_spelling([a], set(), load_rules(), checker=CHECKER)
    assert len(fs) == 1 and fs[0].check == "spelling_unknown_word"


def test_appearance_without_conf_is_spellchecked():
    fs = check_spelling([app("Aprobecha la oferta")], set(), load_rules(), checker=CHECKER)
    assert [f.check for f in fs] == ["spelling_unknown_word"]


def test_unknown_words_recognizes_common_spanish_words():
    assert unknown_words("Quieres ahorrar esta semana", CHECKER, set()) == []
    assert CHECKER.correction("Aprobecha") == "Aprovecha"


class _FakeNS:
    """Imita NSSpellChecker: cada idioma conoce su propio conjunto de palabras."""

    def __init__(self, por_idioma):
        self.por_idioma = por_idioma
        self.vistas = []

    def setLanguage_(self, lang):
        pass

    def checkSpellingOfString_startingAt_language_wrap_inSpellDocumentWithTag_wordCount_(
            self, word, start, language, wrap, tag, count):
        self.vistas.append((word, language))
        conocida = word.lower() in self.por_idioma.get(language, set())

        class _R:
            location = 0x7FFFFFFFFFFFFFFF if conocida else 0
        return _R()


def _checker(por_idioma, languages=("es", "en")):
    c = MacSpellChecker.__new__(MacSpellChecker)
    c._sc = _FakeNS(por_idioma)
    c._lang = languages[0]
    c._langs = tuple(languages)
    c._range = lambda a, b: (a, b)
    return c


def test_palabra_inglesa_se_acepta_si_el_idioma_ingles_esta_activo():
    c = _checker({"es": {"hola"}, "en": {"earnings"}})
    assert c.is_known("earnings")
    assert c.unknown(["earnings"]) == set()


def test_palabra_desconocida_en_todos_los_idiomas_se_marca():
    c = _checker({"es": {"hola"}, "en": {"earnings"}})
    assert not c.is_known("aprobecha")
    assert c.unknown(["aprobecha"]) == {"aprobecha"}


def test_solo_espanol_vuelve_a_marcar_el_ingles():
    c = _checker({"es": {"hola"}, "en": {"earnings"}}, languages=("es",))
    assert c.unknown(["earnings"]) == {"earnings"}


def test_no_consulta_el_segundo_idioma_si_el_primero_ya_la_conoce():
    c = _checker({"es": {"hola"}, "en": {"hola"}})
    c.is_known("hola")
    assert [l for _, l in c._sc.vistas] == ["es"]


def test_is_known_primary_solo_consulta_el_primer_idioma():
    c = _checker({"es": {"hola"}, "en": {"earnings"}})
    assert c.is_known_primary("hola") is True
    assert c.is_known_primary("earnings") is False   # solo inglés la conoce; primario es "es"
    assert [l for _, l in c._sc.vistas] == ["es", "es"]


def test_glued_words_no_mezcla_idiomas_al_partir_una_palabra():
    """"prob" (inglés informal) + "echa" (español) explicaban el typo real "Aprobecha"
    como palabras pegadas y lo bajaban de bloqueante a info. El split solo debe usar el
    idioma principal: una palabra pegada por el OCR está pegada en UN idioma."""
    checker = _checker({"es": {"echa", "casa"}, "en": {"prob", "now"}})
    vocab = _Vocab(checker, glossary=set(), segments=[], appearances=[])
    a = {"t_start": 1.0, "t_end": 3.0}
    assert vocab.classify("aprobecha", a) == "unknown"
    # en cambio una palabra pegada de verdad, con las dos mitades en español, sí se
    # explica como "glued" ("la" es palabra corta conocida; "casa" la conoce el checker).
    assert vocab.classify("lacasa", a) == "glued"


def test_in_glossary_exacta_y_plural():
    g = {"corillo", "reel"}
    assert in_glossary("corillo", g)
    assert in_glossary("Corillo", g)
    assert in_glossary("corillos", g)   # plural en -s
    assert in_glossary("reels", g)
    assert not in_glossary("corillito", g)


def test_in_glossary_plural_en_es():
    g = {"mall"}
    assert in_glossary("malles", g)


def test_in_glossary_entrada_en_plural_acepta_singular():
    g = {"stories"}
    assert in_glossary("stories", g)


def test_in_glossary_no_recorta_por_debajo_de_min_raiz():
    """_MIN_RAIZ = 3: no se acepta como plural una raíz de menos de 3 letras, aunque
    "as" + "es" = "ases" parezca a simple vista un plural razonable de "as"."""
    assert not in_glossary("ases", {"as"})
    # con una raíz de 3+ letras sí se acepta el plural en "-es".
    assert in_glossary("panes", {"pan"})


def test_el_glosario_base_existe_y_trae_palabras():
    assert BASE_GLOSSARY_PATH.exists()
    base = load_base_glossary()
    assert {"reel", "storie", "hashtag", "canva"} <= base
    assert all(w == w.lower() for w in base)


def test_load_glossary_suma_el_base(tmp_path):
    p = tmp_path / "glosario.txt"
    p.write_text("Kasa\n# comentario\n\nMolinrocha\n")
    g = load_glossary(p)
    assert {"kasa", "molinrocha"} <= g
    assert "reel" in g                      # viene del base
    assert "# comentario" not in g


def test_load_glossary_puede_excluir_el_base(tmp_path):
    p = tmp_path / "glosario.txt"
    p.write_text("Kasa\n")
    assert load_glossary(p, incluir_base=False) == {"kasa"}


def test_load_glossary_sin_archivo_del_equipo_devuelve_el_base(tmp_path):
    g = load_glossary(tmp_path / "no_existe.txt")
    assert "reel" in g


def test_unknown_words_respeta_el_plural_del_glosario():
    class _C:
        def unknown(self, words):
            return set(words)          # el diccionario no conoce nada
    assert unknown_words("Los corillos llegaron", _C(), {"corillo"}) == ["Los", "llegaron"]
