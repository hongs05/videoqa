from spellchecker import SpellChecker
from videoqa.checks.spelling import check_spelling, load_glossary, unknown_words
from videoqa.config import load_rules

CHECKER = SpellChecker(language="es")
# Ensure common Spanish words are recognized (pyspellchecker's Spanish dictionary is incomplete)
CHECKER.word_frequency.load_words(['aprovecha', 'quieres'])

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
