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
