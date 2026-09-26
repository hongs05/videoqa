from videoqa.pipeline import _glossary_text_for_judge


def test_glossary_text_for_judge_suma_equipo_y_base():
    """El código y el juez deben ver el mismo vocabulario: si el check de código acepta
    "reel" (viene del glosario base empaquetado) pero el juez solo ve el archivo del
    equipo, las dos mitades de la revisión se contradicen."""
    texto = _glossary_text_for_judge("# palabras del equipo\nMolinrocha\n")
    assert "Molinrocha" in texto        # del archivo del equipo, tal cual
    assert "reel" in texto              # del glosario base empaquetado


def test_glossary_text_for_judge_sin_glosario_del_equipo():
    texto = _glossary_text_for_judge("")
    assert "reel" in texto
