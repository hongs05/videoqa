"""El glosario del equipo se siembra desde lo ya revisado: estos tests fijan qué
palabras se proponen y cómo se añaden sin duplicar."""
from __future__ import annotations

import json
from pathlib import Path

from videoqa.glosario import agregar, candidatas


def _job(jobs: Path, nombre: str, titulos: list[str]) -> None:
    d = jobs / nombre
    d.mkdir(parents=True)
    findings = [{"check": "spelling_unknown_word", "title": t} for t in titulos]
    (d / "findings_code.json").write_text(json.dumps(findings, ensure_ascii=False))


def test_candidatas_cuenta_apariciones_y_videos(tmp_path):
    jobs = tmp_path / "jobs"
    _job(jobs, "a", ["Posible error ortográfico: canva", "Posible error ortográfico: canva, klook"])
    _job(jobs, "b", ["Posible error ortográfico: canva"])
    out = candidatas(jobs, set())
    assert out[0] == ("canva", 3, 2)
    assert ("klook", 1, 1) in out


def test_candidatas_descarta_lo_que_ya_acepta_el_glosario(tmp_path):
    jobs = tmp_path / "jobs"
    _job(jobs, "a", ["Posible error ortográfico: canva, corillos"])
    out = candidatas(jobs, {"canva", "corillo"})   # "corillos" entra por plural
    assert [w for w, _, _ in out] == []


def test_candidatas_ignora_hallazgos_que_no_son_de_ortografia(tmp_path):
    jobs = tmp_path / "jobs"
    d = jobs / "a"
    d.mkdir(parents=True)
    (d / "findings_code.json").write_text(json.dumps(
        [{"check": "brand_color", "title": "Color de texto fuera de marca: #FFF"}]))
    assert candidatas(jobs, set()) == []


def test_candidatas_sin_carpeta_de_trabajos(tmp_path):
    assert candidatas(tmp_path / "no_existe", set()) == []


def test_candidatas_solo_de_unknown_word_no_de_puntuacion_ni_pegadas(tmp_path):
    """spelling_punctuation y spelling_glued_words también empiezan por "spelling", pero
    su título no es una lista de palabras aceptables para el glosario: el de puntuación
    es una frase ("falta el signo de apertura ¿") y el de pegadas es una lectura de OCR
    con los espacios perdidos, no una palabra que valga la pena aceptar."""
    jobs = tmp_path / "jobs"
    d = jobs / "a"
    d.mkdir(parents=True)
    (d / "findings_code.json").write_text(json.dumps([
        {"check": "spelling_unknown_word", "title": "Posible error ortográfico: canva"},
        {"check": "spelling_punctuation", "title": "Puntuación: falta el signo de apertura ¿"},
        {"check": "spelling_glued_words", "title": "Palabras juntas: yasiescomo"},
    ], ensure_ascii=False))
    assert [w for w, _, _ in candidatas(jobs, set())] == ["canva"]


def test_candidatas_descarta_lo_que_ya_conoce_el_corrector(tmp_path):
    """Con el corrector multiidioma activo, candidatas ya vistas en revisiones pasadas
    pueden ser palabras inglesas normales ("earnings", "moment"...) que el checker
    aceptaría hoy: no deben proponerse, o entierran a las candidatas reales bajo ruido."""
    jobs = tmp_path / "jobs"
    _job(jobs, "a", ["Posible error ortográfico: earnings, aprobecha"])

    class _Checker:
        def unknown(self, words):
            return {w for w in words if w.lower() != "earnings"}

    out = candidatas(jobs, set(), checker=_Checker())
    assert [w for w, _, _ in out] == ["aprobecha"]


def test_candidatas_conserva_lo_que_el_corrector_no_conoce(tmp_path):
    jobs = tmp_path / "jobs"
    _job(jobs, "a", ["Posible error ortográfico: aprobecha"])

    class _Checker:
        def unknown(self, words):
            return set(words)          # no conoce nada

    out = candidatas(jobs, set(), checker=_Checker())
    assert [w for w, _, _ in out] == ["aprobecha"]


def test_candidatas_consulta_el_corrector_una_vez_por_palabra_distinta(tmp_path):
    """"canva" aparece en dos hallazgos: el corrector solo debe consultarse una vez por
    ella, no una vez por aparición."""
    jobs = tmp_path / "jobs"
    _job(jobs, "a", ["Posible error ortográfico: canva",
                     "Posible error ortográfico: canva, aprobecha"])

    class _Checker:
        def __init__(self):
            self.consultas = []

        def unknown(self, words):
            self.consultas.append(list(words))
            return set(words)  # no conoce nada

    checker = _Checker()
    candidatas(jobs, set(), checker=checker)
    assert checker.consultas.count(["canva"]) == 1


def test_candidatas_sin_checker_se_comporta_como_antes(tmp_path):
    jobs = tmp_path / "jobs"
    _job(jobs, "a", ["Posible error ortográfico: earnings, aprobecha"])
    out = candidatas(jobs, set())   # checker=None por defecto
    assert [w for w, _, _ in out] == ["aprobecha", "earnings"]


def test_candidatas_salta_un_json_roto(tmp_path):
    jobs = tmp_path / "jobs"
    _job(jobs, "a", ["Posible error ortográfico: canva"])
    roto = jobs / "b"
    roto.mkdir()
    (roto / "findings_code.json").write_text("{no es json")
    assert [w for w, _, _ in candidatas(jobs, set())] == ["canva"]


def test_agregar_crea_el_archivo_con_cabecera(tmp_path):
    p = tmp_path / "glosario.txt"
    assert agregar(p, ["Canva", "klook"]) == ["canva", "klook"]
    texto = p.read_text(encoding="utf-8")
    assert texto.startswith("#")
    assert "canva" in texto.splitlines()
    assert "klook" in texto.splitlines()


def test_agregar_no_duplica(tmp_path):
    p = tmp_path / "glosario.txt"
    agregar(p, ["canva"])
    assert agregar(p, ["canva", "klook"]) == ["klook"]
    assert p.read_text(encoding="utf-8").splitlines().count("canva") == 1


def test_agregar_respeta_lo_que_ya_habia(tmp_path):
    p = tmp_path / "glosario.txt"
    p.write_text("# mis palabras\nkasa\n")
    agregar(p, ["klook"])
    lineas = p.read_text(encoding="utf-8").splitlines()
    assert "kasa" in lineas and "klook" in lineas
