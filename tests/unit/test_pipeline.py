from videoqa.pipeline import _glossary_text_for_judge


def test_glossary_text_for_judge_suma_equipo_y_base(tmp_path):
    """El código y el juez deben ver el mismo vocabulario: si el check de código acepta
    "reel" (viene del glosario base empaquetado) pero el juez solo ve el archivo del
    equipo, las dos mitades de la revisión se contradicen."""
    p = tmp_path / "glosario.txt"
    p.write_text("# palabras del equipo\nMolinrocha\n")
    texto = _glossary_text_for_judge(p)
    assert "Molinrocha" in texto        # del archivo del equipo, tal cual
    assert "reel" in texto              # del glosario base empaquetado


def test_glossary_text_for_judge_sin_archivo_del_equipo(tmp_path):
    texto = _glossary_text_for_judge(tmp_path / "no_existe.txt")
    assert "reel" in texto
