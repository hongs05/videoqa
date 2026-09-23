"""Perfiles por cliente (01_Entrada/<Cliente>/) y brief por pieza."""
import json
from pathlib import Path

from PIL import Image

from tests.unit.test_espera import _Speller
from videoqa import backends, cli
from videoqa.config import Settings, load_rules
from videoqa.job import Job
from videoqa.learning import add_correction
from videoqa.pipeline import process_video
from videoqa.profiles import (brand_dir, client_of, jobs_root, load_brief, load_profile, merged_rules,
                              MAX_BRIEF_CHARS)
from videoqa.watcher import list_videos

VEREDICTO = json.dumps({"findings": [], "guion_real_md": "## Escena 1 [0:00]\nHola"})


def _settings(tmp_path) -> Settings:
    s = Settings(drive_root=tmp_path / "drive", jobs_dir=tmp_path / "jobs")
    for d in (s.entrada, s.config_dir):
        d.mkdir(parents=True, exist_ok=True)
    return s


def _perfil(s: Settings, cliente="Sushi CD", criterios="# Criterios\n- Nunca decir barato", glosario="nibs\n",
            reglas=None, brand=None):
    d = s.config_dir / "clientes" / cliente
    d.mkdir(parents=True)
    (d / "criterios.md").write_text(criterios)
    (d / "glosario.txt").write_text(glosario)
    if reglas:
        (d / "reglas.yaml").write_text(reglas)
    if brand:
        (d / "brand.json").write_text(json.dumps(brand))
    return d


# --- Detección y carga ----------------------------------------------------------------------

def test_cliente_por_carpeta(tmp_path):
    s = _settings(tmp_path)
    assert client_of(s.entrada / "Sushi CD" / "reel.mp4", s) == "Sushi CD"
    assert client_of(s.entrada / "reel.mp4", s) is None
    assert client_of(s.con_errores / "Sushi CD" / "reel" / "reel.mp4", s) == "Sushi CD"
    assert client_of(s.con_errores / "reel" / "reel.mp4", s) is None
    assert client_of(s.entrada / "_borradores" / "reel.mp4", s) is None
    assert client_of(tmp_path / "fuera" / "x" / "reel.mp4", s) is None


def test_perfil_hereda_y_suma(tmp_path):
    s = _settings(tmp_path)
    (s.config_dir / "glosario.txt").write_text("TikTok\n")
    _perfil(s, reglas="severities:\n  silence: info\n")
    p = load_profile(s, "Sushi CD")
    assert "TikTok" in p.glossary_text and "nibs" in p.glossary_text
    assert p.criteria.startswith("# Criterios")
    r = merged_rules(load_rules(), p.rule_overrides)
    assert r["severities"]["silence"] == "info"
    assert r["severities"]["black_frame"] == "blocker", "lo demás se hereda"
    assert load_rules()["severities"]["silence"] == "warning", "no toca las reglas generales"


def test_perfil_general_y_cliente_sin_carpeta(tmp_path):
    s = _settings(tmp_path)
    assert load_profile(s, None).client is None
    p = load_profile(s, "Nuevo")  # carpeta de Entrada sin perfil: hereda todo
    assert p.criteria == "" and p.rule_overrides == {}


def test_marca_propia_solo_si_la_tiene(tmp_path):
    s = _settings(tmp_path)
    _perfil(s, "Con marca", brand={"palette": [{"hex": "#FF0000"}]})
    _perfil(s, "Sin marca")
    assert brand_dir(s, load_profile(s, "Con marca")) == s.config_dir / "clientes" / "Con marca"
    assert brand_dir(s, load_profile(s, "Sin marca")) == s.config_dir


def test_brief(tmp_path):
    v = tmp_path / "reel.mp4"
    assert load_brief(v) == ""
    (tmp_path / "reel.txt").write_text("Objetivo: vender\n")
    assert load_brief(v) == "Objetivo: vender"
    (tmp_path / "reel.txt").write_text("x" * (MAX_BRIEF_CHARS + 50))
    assert load_brief(v).endswith("[… brief recortado]")


def test_watcher_ve_las_carpetas_de_cliente(tmp_path):
    s = _settings(tmp_path)
    for rel in ("suelto.mp4", "Sushi CD/reel.mp4", "_borradores/x.mp4", ".oculta/y.mp4", "Sushi CD/reel.txt"):
        (s.entrada / rel).parent.mkdir(parents=True, exist_ok=True)
        (s.entrada / rel).write_bytes(b"1")
    assert sorted(p.name for p in list_videos(s.entrada)) == ["reel.mp4", "suelto.mp4"]


# --- Pipeline completo con cliente ------------------------------------------------------------

def _video_de_cliente(tmp_path, cliente="Sushi CD"):
    s = _settings(tmp_path)
    carpeta = s.entrada / cliente
    carpeta.mkdir()
    video = carpeta / "reel.mp4"
    video.write_bytes(b"video")
    job = Job(video, jobs_root(s, cliente))
    job.record_video()
    (job.dir / "frames").mkdir()
    Image.new("RGB", (108, 192), (30, 30, 30)).save(job.path("frames/sec_0001.jpg"))
    etapas = {
        "probe.json": {"duration": 10.0, "width": 1080, "height": 1920, "has_audio": True},
        "transcript.json": {"language": "es", "text": "hola", "segments": [{"start": 0, "end": 2, "text": "hola"}]},
        "technical.json": {"black": [], "freeze": [], "scene_cuts": [], "silence": [], "audio": None},
        "frames.json": {"fps": 2, "period": 0.5, "frames": [{"file": "frames/sec_0001.jpg", "t": 0.0, "kind": "second"}]},
        "ocr.json": {"raw": [], "appearances": []},
        "ocr_color.json": {"raw": [], "appearances": []},
    }
    for name, data in etapas.items():
        job.path(name).write_text(json.dumps(data))
    return video, s


def test_pipeline_usa_perfil_brief_y_correcciones_del_cliente(tmp_path):
    video, s = _video_de_cliente(tmp_path)
    _perfil(s)
    (video.parent / "reel.txt").write_text("CTA: pide por WhatsApp")
    add_correction(s.config_dir, tipo="falso_positivo", video="a", motivo="corillo es jerga nuestra", cliente="Sushi CD")
    add_correction(s.config_dir, tipo="falso_positivo", video="b", motivo="jerga de otro cliente", cliente="Hacienda")
    add_correction(s.config_dir, tipo="falso_positivo", video="c", motivo="logos de ropa no cuentan")
    prompts = []
    backends.register_speller(_Speller)
    try:
        res = process_video(video, s, load_rules(), lambda p, c: prompts.append(p) or VEREDICTO)
    finally:
        backends.reset()
    prompt = prompts[0]
    assert "## Cliente: Sushi CD — criterios de revisión\n# Criterios\n- Nunca decir barato" in prompt
    assert "## Brief de la pieza (lo que se planeó)\nCTA: pide por WhatsApp" in prompt
    assert "nibs" in prompt
    assert "corillo es jerga nuestra" in prompt and "logos de ropa no cuentan" in prompt
    assert "jerga de otro cliente" not in prompt
    # Se entrega en la carpeta del cliente, con el brief al lado.
    assert res.status == "approved" and res.dest == s.aprobado / "Sushi CD" / "reel"
    assert (res.dest / "reel.mp4").exists() and (res.dest / "reel.txt").exists()
    assert not (video.parent / "reel.txt").exists()
    assert (s.jobs_dir / "_clientes" / "Sushi CD" / "reel").is_dir()


def test_mismo_nombre_en_dos_clientes_no_se_pisan(tmp_path):
    s = _settings(tmp_path)
    a = Job(s.entrada / "A" / "reel.mp4", jobs_root(s, "A"))
    b = Job(s.entrada / "B" / "reel.mp4", jobs_root(s, "B"))
    assert a.dir != b.dir


# --- CLI ----------------------------------------------------------------------------------

def test_revisar_de_nuevo_vuelve_a_la_carpeta_del_cliente(tmp_path, monkeypatch, capsys):
    drive = tmp_path / "drive"
    cli.main(["init", "--drive-root", str(drive)])
    revisado = drive / "02_Con_errores" / "Sushi CD" / "reel" / "reel.mp4"
    revisado.parent.mkdir(parents=True)
    revisado.write_bytes(b"x")
    (revisado.parent / "reel.txt").write_text("brief")
    visto = {}
    from videoqa.pipeline import Result

    def fake(video, *a, **k):
        visto["video"] = video
        return Result("approved", [], drive / "03_Aprobado" / "Sushi CD" / "reel")

    monkeypatch.setattr(cli, "process_video", fake)
    assert cli.main(["run", str(revisado)]) == 0
    assert visto["video"] == drive / "01_Entrada" / "Sushi CD" / "reel.mp4"
    assert (drive / "01_Entrada" / "Sushi CD" / "reel.txt").read_text() == "brief"


def test_video_ya_en_carpeta_de_cliente_no_se_copia(tmp_path, monkeypatch):
    drive = tmp_path / "drive"
    cli.main(["init", "--drive-root", str(drive)])
    video = drive / "01_Entrada" / "Sushi CD" / "reel.mp4"
    video.parent.mkdir()
    video.write_bytes(b"x")
    from videoqa.pipeline import Result
    visto = {}
    monkeypatch.setattr(cli, "process_video", lambda v, *a, **k: visto.setdefault("v", v) and Result("approved", [], drive))
    cli.main(["run", str(video)])
    assert visto["v"] == video.resolve()
    assert not (drive / "01_Entrada" / "reel.mp4").exists()


def test_hallazgos_y_correccion_de_un_cliente(tmp_path, capsys):
    from videoqa.config import load_settings
    from videoqa.findings import Finding, save_findings
    from videoqa.learning import load_corrections
    drive = tmp_path / "drive"
    cli.main(["init", "--drive-root", str(drive)])
    s = load_settings()
    job = s.jobs_dir / "_clientes" / "Sushi CD" / "reel3"
    job.mkdir(parents=True)
    save_findings(job / "findings_final.json", [Finding(id="spell-1", type="ortografia", severity="blocker",
                                                        t_start=1, t_end=2, title="Posible error ortográfico: corillo",
                                                        detail="d", check="spelling_unknown_word")])
    assert cli.main(["hallazgos", "reel3"]) == 0
    assert "VIDEO Sushi CD / reel3" in capsys.readouterr().out
    assert cli.main(["corregir", "reel3", "--hallazgo", "spell-1", "--motivo", "jerga nuestra"]) == 0
    assert "solo para Sushi CD" in capsys.readouterr().out
    assert cli.main(["corregir", "reel3", "--hallazgo", "spell-1", "--motivo", "vale siempre", "--para-todos"]) == 0
    c = load_corrections(s.config_dir)
    assert c[0]["cliente"] == "Sushi CD" and "cliente" not in c[1]
