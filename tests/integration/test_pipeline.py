import hashlib
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
    # load_brand() ignora brand.json si no hay un guia_de_marca.pdf con el mismo sha256
    # (ver test_load_brand_without_pdf_ignores_stale_brand_json): sembramos un PDF
    # placeholder y recalculamos el sha para que el brand.json de fixtures se use tal cual,
    # sin necesitar el runner de Claude para reconstruirlo.
    pdf_bytes = b"%PDF fixture guia de marca"
    (s.config_dir / "guia_de_marca.pdf").write_bytes(pdf_bytes)
    brand = json.loads((FIX / "brand.json").read_text())
    brand["source_pdf_sha256"] = hashlib.sha256(pdf_bytes).hexdigest()
    (s.config_dir / "brand.json").write_text(json.dumps(brand))
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
        return json.dumps({"findings": [], "confirmed_code_findings": [], "guion_real_md": "",
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
    assert (s.con_errores / "clean" / "reporte.md").read_text().startswith("# ❌")
    assert ws.rows[1][2] == "❌ Error"
    assert res.dest is not None and res.error

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
    assert ws.rows[-1][2] == "❌ Error"

def test_corrupt_video_stays_in_entrada(tmp_path, fixture_videos):
    s, _ = make_env(tmp_path, fixture_videos, "clean")
    bad = s.entrada / "roto.mp4"; bad.write_bytes(b"no es un video")
    ws = FakeWS()
    res = process_video(bad, s, load_rules(), runner=lambda p, cwd: GOOD_VERDICT,
                        sheet=SheetWriter(lambda: SheetClient(ws), tmp_path / "p.json"))
    assert res.status == "error" and res.error and bad.exists()
    assert ws.rows[-1][2] == "❌ Error" and ws.rows[-1][5]
