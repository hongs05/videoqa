from datetime import datetime

from PIL import Image

from videoqa.findings import Finding
from videoqa.job import Job
from videoqa.report_html import build_html_report, render_html

PROBE = {"duration": 58.0, "width": 1080, "height": 1920, "fps": 30.0, "has_audio": True}


def fnd(id, sev, t, check="brand_color", typ="marca", frame=None):
    return Finding(id=id, type=typ, severity=sev, t_start=t, t_end=t + 1, title=f"T{id}",
                   detail=f"D{id}", suggestion="S", frame=frame, check=check)


def test_html_rechazado_tiene_semaforo_y_secciones():
    fs = [fnd("b", "blocker", 12), fnd("w", "warning", 3, check="silence", typ="tecnico")]
    html = render_html("promo.mp4", PROBE, fs, "rejected", {}, datetime(2026, 9, 17, 14, 32))
    assert html.startswith("<!doctype html>")
    assert "promo.mp4" in html and "NO APROBADO" in html
    assert "Bloqueantes" in html and "Advertencias" in html
    assert "0:12" in html and "0:03" in html
    assert html.index("Bloqueantes") < html.index("Advertencias")
    assert '<html lang="es">' in html


def test_html_aprobado_no_lista_bloqueantes():
    html = render_html("ok.mp4", PROBE, [], "approved", {}, datetime(2026, 9, 17))
    assert "APROBADO" in html and "NO APROBADO" not in html
    assert "Bloqueantes" not in html


def test_la_evidencia_va_incrustada_en_base64(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    (job.dir / "evidencia").mkdir()
    Image.new("RGB", (40, 30), (255, 0, 0)).save(job.path("evidencia/01_0m12s.jpg"))
    fs = [fnd("b", "blocker", 12, frame="frames/x.jpg")]
    html = render_html("v.mp4", PROBE, fs, "rejected", {"b": "evidencia/01_0m12s.jpg"},
                       datetime(2026, 9, 17), job=job)
    assert "data:image/jpeg;base64," in html


def test_evidencia_ausente_no_rompe(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    fs = [fnd("b", "blocker", 12)]
    html = render_html("v.mp4", PROBE, fs, "rejected", {"b": "evidencia/no_existe.jpg"},
                       datetime(2026, 9, 17), job=job)
    assert "data:image" not in html and "Tb" in html


def test_build_html_report_escribe_el_archivo(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    p = build_html_report(job, PROBE, [], "approved", {})
    assert p == job.path("reporte.html") and "APROBADO" in p.read_text(encoding="utf-8")


def test_el_html_escapa_el_texto():
    fs = [Finding(id="x", type="marca", severity="blocker", t_start=0, t_end=1,
                  title="<script>alerta</script>", detail="a & b", suggestion="")]
    html = render_html("v.mp4", PROBE, fs, "rejected", {}, datetime(2026, 9, 17))
    assert "<script>alerta</script>" not in html
    assert "&lt;script&gt;" in html and "a &amp; b" in html


def test_pendientes_cuando_el_juez_no_corrio():
    fs = [Finding(id="j", type="tecnico", severity="warning", t_start=0, t_end=10,
                  title="Revisión de criterio pendiente", detail="d", check="judge_unavailable")]
    html = render_html("v.mp4", PROBE, fs, "error", {}, datetime(2026, 9, 17))
    assert "Pendientes de revisión" in html
    pasados = html.split("Checks pasados")[1].split("Pendientes")[0]
    assert "Bloopers" not in pasados
