"""Correcciones del equipo: se guardan, se eligen las parecidas y llegan al juez."""
import json
from datetime import datetime

from videoqa import cli, learning
from videoqa.config import load_settings
from videoqa.findings import Finding, save_findings

SUSHI = {"id": "spell-3", "type": "ortografia", "severity": "blocker", "t_start": 19.0, "t_end": 19.5,
         "title": "Posible error ortográfico: SUSHICD", "detail": 'Texto en pantalla: "SUSHICD.".',
         "check": "spelling_unknown_word"}


def test_guardar_y_leer(tmp_path):
    learning.add_correction(tmp_path, tipo="falso_positivo", video="REEL 3", motivo="logo de la camiseta",
                            finding=SUSHI, now=datetime(2026, 9, 22, 20, 0))
    learning.add_correction(tmp_path, tipo="no_detectado", video="REEL 1", motivo="precio distinto", segundo=12)
    c = learning.load_corrections(tmp_path)
    assert [e["tipo"] for e in c] == ["falso_positivo", "no_detectado"]
    assert c[0]["palabras"] == ["SUSHICD"] and c[0]["check"] == "spelling_unknown_word"
    assert c[1]["segundo"] == 12


def test_lineas_rotas_se_ignoran(tmp_path):
    learning.path_for(tmp_path).write_text('{"tipo": "falso_positivo", "motivo": "ok"}\nbasura\n{"sin": "motivo"}\n')
    assert len(learning.load_corrections(tmp_path)) == 1


def test_motivo_obligatorio(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        learning.add_correction(tmp_path, tipo="falso_positivo", video="v", motivo="  ")


def test_palabra_corregida_dos_veces_se_sugiere_al_glosario(tmp_path):
    for _ in range(2):
        learning.add_correction(tmp_path, tipo="falso_positivo", video="v", motivo="logo", finding=SUSHI)
    assert learning.repeated_words(learning.load_corrections(tmp_path), ["SUSHICD", "otra"]) == ["SUSHICD"]


def _fnd(check, title, typ="ortografia"):
    return Finding(id="x", type=typ, severity="blocker", t_start=0, t_end=1, title=title, detail="d", check=check)


def test_relevantes_prioriza_lo_parecido():
    ruido = [{"tipo": "falso_positivo", "motivo": f"silencio intencional {i}", "check": "silence",
              "categoria": "tecnico"} for i in range(30)]
    logo = {"tipo": "falso_positivo", "motivo": "logo de la camiseta", "check": "spelling_unknown_word",
            "palabras": ["SUSHICD"]}
    elegidas = learning.relevant([logo, *ruido], [_fnd("spelling_unknown_word", "Posible error ortográfico: SUSHICD")],
                                 [], {"text": ""}, limit=5)
    assert elegidas[0] is logo and len(elegidas) == 5


def test_con_pocas_correcciones_van_todas_las_recientes_primero():
    c = [{"tipo": "falso_positivo", "motivo": "a"}, {"tipo": "no_detectado", "motivo": "b"}]
    assert learning.relevant(c, [], [], {"text": ""}) == [c[1], c[0]]


# --- Llegan al juez ------------------------------------------------------------------------

def test_el_juez_recibe_las_correcciones(tmp_path):
    from tests.unit.test_judge import R, frames_list, make_job
    from videoqa.judge import prepare_judge
    job = make_job(tmp_path)
    corr = [{"tipo": "falso_positivo", "motivo": "logo de la camiseta", "palabras": ["SUSHICD"], "fecha": "x"}]
    prompt = prepare_judge(job, {}, "", {"segments": []}, {"appearances": []}, {"scene_cuts": []}, [],
                           frames_list(), R, corrections=corr)
    data = json.loads(job.path("judge_input/aprendizaje.json").read_text())
    assert data == [{"tipo": "falso_positivo", "motivo": "logo de la camiseta", "palabras": ["SUSHICD"]}]
    assert "## Criterio aprendido del equipo\n- [no era error] logo de la camiseta (palabras: SUSHICD)" in prompt


def test_sin_correcciones_no_hay_archivo(tmp_path):
    from tests.unit.test_judge import R, frames_list, make_job
    from videoqa.judge import prepare_judge
    job = make_job(tmp_path)
    prompt = prepare_judge(job, {}, "", {"segments": []}, {"appearances": []}, {"scene_cuts": []}, [],
                           frames_list(), R)
    assert not job.path("judge_input/aprendizaje.json").exists()
    assert "## Criterio aprendido del equipo" not in prompt


# --- CLI -----------------------------------------------------------------------------------

def _job_revisado(tmp_path):
    drive = tmp_path / "drive"
    cli.main(["init", "--drive-root", str(drive)])
    s = load_settings()
    job = s.jobs_dir / "REEL #3 El behind de una campaña"
    job.mkdir(parents=True)
    save_findings(job / "findings_final.json", [Finding.from_dict(SUSHI)])
    return s


def test_hallazgos_lista_por_trozo_del_nombre(tmp_path, capsys):
    _job_revisado(tmp_path)
    assert cli.main(["hallazgos", "reel #3"]) == 0
    out = capsys.readouterr().out
    assert "[spell-3] 0:19 BLOQUEA · Posible error ortográfico: SUSHICD" in out


def test_hallazgos_video_desconocido(tmp_path, capsys):
    _job_revisado(tmp_path)
    assert cli.main(["hallazgos", "reel #9"]) == 1
    assert "NO_ENCONTRADO" in capsys.readouterr().out


def test_corregir_guarda_y_sugiere_glosario(tmp_path, capsys):
    s = _job_revisado(tmp_path)
    for _ in range(2):
        assert cli.main(["corregir", "reel #3", "--hallazgo", "spell-3", "--motivo", "logo de la camiseta"]) == 0
    out = capsys.readouterr().out
    assert "GUARDADO (falso_positivo)" in out and "SUGERIR_GLOSARIO: SUSHICD" in out
    c = learning.load_corrections(s.config_dir)
    assert len(c) == 2 and c[0]["video"] == "REEL #3 El behind de una campaña"


def test_corregir_no_detectado(tmp_path, capsys):
    s = _job_revisado(tmp_path)
    assert cli.main(["corregir", "reel #3", "--no-detectado", "--motivo", "precio distinto al dicho",
                     "--segundo", "12"]) == 0
    assert learning.load_corrections(s.config_dir)[0]["tipo"] == "no_detectado"


def test_corregir_hallazgo_inexistente(tmp_path, capsys):
    _job_revisado(tmp_path)
    assert cli.main(["corregir", "reel #3", "--hallazgo", "nope", "--motivo", "x"]) == 1
