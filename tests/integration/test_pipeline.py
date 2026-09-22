import json
import shutil
from pathlib import Path
from videoqa.config import Settings, load_rules
from videoqa.pipeline import process_video
from videoqa.sheet import HEADERS, SheetClient, SheetWriter

FIX = Path(__file__).resolve().parents[1] / "fixtures"

GOOD_VERDICT = json.dumps({"findings": [], "confirmed_code_findings": [], "dismissed_code_findings": [],
                           "guion_real_md": "## Escena 1 [0:00]\nAprovecha la oferta de verano."})

class FakeWS:
    def __init__(self): self.rows = []
    def get_all_values(self): return [list(r) for r in self.rows]
    def update(self, values, range_name=None):
        # videoqa.sheet.SheetClient llama gspread con la firma moderna
        # ws.update(values, range_name=...) en vez de la posicional antigua.
        r = int(range_name.split(":")[0].lstrip("A")); self.rows[r - 1] = list(values[0])
    def append_row(self, v): self.rows.append(list(v))

def make_env(tmp_path, fixture_videos, name):
    drive = tmp_path / "drive"
    s = Settings(drive_root=drive, jobs_dir=tmp_path / "jobs")
    s.entrada.mkdir(parents=True); s.config_dir.mkdir()
    # Sin guia_de_marca.pdf: load_brand() usa el brand.json manual tal cual, sin runner.
    shutil.copy(FIX / "brand.json", s.config_dir / "brand.json")
    shutil.copy(FIX / "glosario.txt", s.config_dir / "glosario.txt")
    video = s.entrada / f"{name}.mp4"
    shutil.copy(fixture_videos[name], video)
    return s, video

def stub_transcript(monkeypatch):
    """Evita Whisper real: transcripción fija coherente con el audio de los fixtures."""
    import videoqa.pipeline as pl
    monkeypatch.setattr(pl, "transcribe", lambda job, has_audio, model: {
        "language": "es", "text": "Aprovecha la oferta de verano solo por esta semana" if has_audio else "",
        "segments": [{"start": 0.5, "end": 4.0, "text": "Aprovecha la oferta de verano solo por esta semana"}] if has_audio else []})

def _setup(tmp_path, fixture_videos, monkeypatch, name):
    """Preparación mínima (settings, rules, video) reutilizada por los tests que solo
    necesitan un fixture listo en Entrada con transcripción falsa, sin más lógica."""
    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, name)
    return s, load_rules(), video


def test_spelling_color_fixture_is_rejected(tmp_path, fixture_videos, monkeypatch):
    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "spelling_color")
    ws = FakeWS()
    res = process_video(video, s, load_rules(), runner=lambda p, cwd: GOOD_VERDICT,
                        sheet=SheetWriter(lambda: SheetClient(ws), tmp_path / "pending.json"))
    assert res.status == "rejected"
    checks = {f.check for f in res.findings}
    assert {"spelling_unknown_word", "brand_color"} <= checks
    assert res.dest == s.con_errores / "spelling_color"
    assert not video.exists() and (res.dest / "spelling_color.mp4").exists()
    report = (res.dest / "reporte.md").read_text()
    assert report.startswith("# 🔴") and "Aprobecha" in report and "fuera de marca" in report
    assert (res.dest / "guion_real.md").read_text().startswith("## Escena 1")
    assert any(p.suffix == ".jpg" for p in (res.dest / "evidencia").iterdir())
    assert ws.rows[0] == HEADERS and ws.rows[1][0] == "spelling_color.mp4" and ws.rows[1][2] == "🔴"

def test_clean_fixture_is_approved(tmp_path, fixture_videos, monkeypatch):
    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "clean")
    ws = FakeWS()
    res = process_video(video, s, load_rules(), runner=lambda p, cwd: GOOD_VERDICT,
                        sheet=SheetWriter(lambda: SheetClient(ws), tmp_path / "pending.json"))
    assert res.status == "approved", [f.title for f in res.findings]
    assert (s.aprobado / "clean" / "clean.mp4").exists()
    assert ws.rows[-1][2] == "🟢"
    assert ws.rows[-1][5].startswith("03_Aprobado/") and ws.rows[-1][6].startswith("03_Aprobado/")

def test_black_screen_fixture_is_rejected_by_technical_check(tmp_path, fixture_videos, monkeypatch):
    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "black_screen")
    res = process_video(video, s, load_rules(), runner=lambda p, cwd: GOOD_VERDICT)
    assert res.status == "rejected" and "black_frame" in {f.check for f in res.findings}

def test_judge_dismissal_removes_code_finding(tmp_path, fixture_videos, monkeypatch):
    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "spelling_color")
    def runner(prompt, cwd):
        code = json.loads((cwd / "judge_input" / "findings_code.json").read_text())
        spell_ids = [f["id"] for f in code if f["check"] == "spelling_unknown_word"]
        return json.dumps({"findings": [], "confirmed_code_findings": [], "guion_real_md": "## Escena 1 [0:00] Hola",
                           "dismissed_code_findings": [{"id": i, "reason": "marca del cliente"} for i in spell_ids]})
    res = process_video(video, s, load_rules(), runner=runner)
    assert "spelling_unknown_word" not in {f.check for f in res.findings}
    assert "brand_color" in {f.check for f in res.findings}

def test_judge_failure_yields_error_status_in_con_errores(tmp_path, fixture_videos, monkeypatch):
    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "clean")
    ws = FakeWS()
    from videoqa.claude_runner import ClaudeError
    def failing(p, cwd):
        raise ClaudeError("rate limit")
    res = process_video(video, s, load_rules(), runner=failing, sheet=SheetWriter(lambda: SheetClient(ws), tmp_path / "p.json"))
    assert res.status == "error" and "judge_unavailable" in {f.check for f in res.findings}
    report = (s.con_errores / "clean" / "reporte.md").read_text()
    assert report.startswith("# ⏸️")
    # Sin juez, sus checks NO pueden declararse pasados.
    assert "## ⏳ Pendientes de revisión (Claude no disponible)" in report
    assert "Bloopers" not in report.split("## ✅ Checks pasados")[1].split("## ⏳")[0]
    assert ws.rows[1][2] == "⏸️ Pendiente"
    # La columna "Reporte" del Sheet lleva el motivo, no una ruta.
    assert ws.rows[1][5].startswith("Claude no disponible:") and "rate limit" in ws.rows[1][5]
    assert res.dest is not None and res.error

def test_judge_failure_por_sesion_caducada_escribe_doctor_json(tmp_path, fixture_videos, monkeypatch):
    # Si el juez falla porque la sesión de Claude caducó, el pipeline deja constancia en
    # doctor.json para que el hook SessionStart de la próxima sesión avise sin esperar a
    # que alguien lance `videoqa doctor` a mano.
    monkeypatch.setenv("VIDEOQA_HOME", str(tmp_path / "home"))
    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "clean")
    from videoqa.claude_runner import ClaudeError
    from videoqa.config import videoqa_home

    def failing(p, cwd):
        raise ClaudeError("claude -p salió con 1: Failed to authenticate: OAuth session expired")
    res = process_video(video, s, load_rules(), runner=failing)
    assert res.status == "error"
    doctor = json.loads((videoqa_home() / "doctor.json").read_text())
    assert doctor["ok"] is False
    assert doctor["motivo"] == "la sesión caducó o no está guardada"
    assert "at" in doctor


def test_judge_failure_por_otro_motivo_no_toca_doctor_json(tmp_path, fixture_videos, monkeypatch):
    # Un fallo que no tiene pinta de sesión caducada (p. ej. una salida rara de `claude -p`)
    # no debe hacer que el hook empiece a avisar de sesión caducada por error.
    monkeypatch.setenv("VIDEOQA_HOME", str(tmp_path / "home"))
    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "clean")
    from videoqa.claude_runner import ClaudeError
    from videoqa.config import videoqa_home

    def failing(p, cwd):
        raise ClaudeError("salida no JSON")
    res = process_video(video, s, load_rules(), runner=failing)
    assert res.status == "error"
    assert not (videoqa_home() / "doctor.json").exists()


def test_judge_raising_plain_exception_still_degrades_gracefully(tmp_path, fixture_videos, monkeypatch):
    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "clean")
    ws = FakeWS()
    def exploding(p, cwd):
        raise RuntimeError("claude explotó")
    res = process_video(video, s, load_rules(), runner=exploding,
                        sheet=SheetWriter(lambda: SheetClient(ws), tmp_path / "p.json"))
    assert res.status == "error"
    assert "judge_unavailable" in {f.check for f in res.findings}
    assert (s.con_errores / "clean" / "clean.mp4").exists()
    assert ws.rows[-1][2] == "⏸️ Pendiente"

def test_corrupt_video_stays_in_entrada(tmp_path, fixture_videos):
    s, _ = make_env(tmp_path, fixture_videos, "clean")
    bad = s.entrada / "roto.mp4"; bad.write_bytes(b"no es un video")
    ws = FakeWS()
    res = process_video(bad, s, load_rules(), runner=lambda p, cwd: GOOD_VERDICT,
                        sheet=SheetWriter(lambda: SheetClient(ws), tmp_path / "p.json"))
    assert res.status == "error" and res.error and bad.exists()
    assert ws.rows[-1][2] == "⏸️ Pendiente" and ws.rows[-1][5]


def test_modo_preparar_deja_el_video_en_entrada_y_escribe_el_prompt(tmp_path, fixture_videos, monkeypatch):
    settings, rules, video = _setup(tmp_path, fixture_videos, monkeypatch, "spelling_color")

    def juez_no_debe_llamarse(prompt, cwd):
        raise AssertionError("en modo preparar no se llama al juez")
    res = process_video(video, settings, rules, juez_no_debe_llamarse, modo="preparar")
    assert res.status == "pending" and res.dest is None
    assert video.exists()
    job_dir = settings.jobs_dir / video.stem
    assert (job_dir / "judge_prompt.md").exists()
    assert (job_dir / "judge_input" / "findings_code.json").exists()


def test_veredicto_externo_sustituye_al_juez(tmp_path, fixture_videos, monkeypatch):
    settings, rules, video = _setup(tmp_path, fixture_videos, monkeypatch, "spelling_color")
    veredicto = json.dumps({"findings": [], "guion_real_md": "# Guion\n\nHola.",
                            "confirmed_code_findings": [], "dismissed_code_findings": []})

    def juez_no_debe_llamarse(prompt, cwd):
        raise AssertionError("con veredicto externo no se llama al juez")
    res = process_video(video, settings, rules, juez_no_debe_llamarse, veredicto_text=veredicto)
    assert res.status in ("approved", "rejected")
    assert res.dest is not None and (res.dest / "guion_real.md").read_text().startswith("# Guion")


def test_genera_reporte_html_cuando_la_regla_esta_activa(tmp_path, fixture_videos, monkeypatch):
    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "clean")
    rules = load_rules()
    rules["salida"] = {"reporte_html": True}
    res = process_video(video, s, rules, runner=lambda p, cwd: GOOD_VERDICT)
    assert (res.dest / "reporte.html").exists()
    assert "APROBADO" in (res.dest / "reporte.html").read_text(encoding="utf-8")


def test_sin_juez_requerido_el_video_limpio_se_aprueba(tmp_path, fixture_videos, monkeypatch):
    """Instalaciones de pre-chequeo (sin Claude) tienen que poder decir 🟢."""
    from videoqa.claude_runner import ClaudeError

    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "clean")
    rules = load_rules()
    rules["juez_requerido"] = False

    def sin_juez(prompt, cwd):
        raise ClaudeError("no hay juez configurado")

    res = process_video(video, s, rules, runner=sin_juez)
    assert res.status == "approved", [f.title for f in res.findings]
    assert res.error is None
    judge = [f for f in res.findings if f.check == "judge_unavailable"]
    assert len(judge) == 1 and judge[0].severity == "info"


def test_sin_juez_requerido_un_bloqueante_sigue_rechazando(tmp_path, fixture_videos, monkeypatch):
    from videoqa.claude_runner import ClaudeError

    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "spelling_color")
    rules = load_rules()
    rules["juez_requerido"] = False
    res = process_video(video, s, rules, runner=lambda p, c: (_ for _ in ()).throw(ClaudeError("sin juez")))
    assert res.status == "rejected"
