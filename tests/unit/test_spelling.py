from videoqa.checks.spelling import MacSpellChecker, check_spelling, load_glossary, unknown_words
from videoqa.config import load_rules

CHECKER = MacSpellChecker()

def app(text, t=1.0):
    return {"text": text, "bbox": [0.1, 0.4, 0.8, 0.1], "t_start": t, "t_end": t + 2,
            "frame": "frames/sec_0003.jpg", "frames": []}

def test_load_glossary_missing_file(tmp_path):
    assert load_glossary(tmp_path / "no.txt") == set()

def test_load_glossary_lowercases(tmp_path):
    p = tmp_path / "g.txt"; p.write_text("VideoQA\n# comentario\n\nTikTok\n")
    assert load_glossary(p) == {"videoqa", "tiktok"}

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
