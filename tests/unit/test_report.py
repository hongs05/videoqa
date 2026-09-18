from datetime import datetime

from PIL import Image

from videoqa.findings import Finding
from videoqa.job import Job
from videoqa.report import build_report, fmt_t, render_report, write_evidence

PROBE = {"duration": 58.0, "width": 1080, "height": 1920, "fps": 30.0, "has_audio": True}


def fnd(id, sev, t, check="brand_color", frame=None, bbox=None, typ="marca"):
    return Finding(id=id, type=typ, severity=sev, t_start=t, t_end=t + 1, title=f"T{id}", detail=f"D{id}",
                   suggestion="S", frame=frame, bbox=bbox, check=check)


def test_fmt_t():
    assert fmt_t(0) == "0:00" and fmt_t(72.4) == "1:12" and fmt_t(605) == "10:05"


def test_render_rejected_report_structure():
    fs = [fnd("w", "warning", 3, check="silence"), fnd("b", "blocker", 12)]
    md = render_report("promo.mp4", PROBE, fs, "rejected", {"b": "evidencia/01_0m12s.jpg"}, datetime(2026, 9, 11, 14, 32))
    assert md.startswith("# 🔴 promo.mp4 — NO APROBADO")
    assert "0:58" in md and "1080×1920" in md and "1 bloqueante" in md and "1 advertencia" in md
    assert md.index("## 🔴 Bloqueantes") < md.index("[0:12]") < md.index("## ⚠️ Advertencias") < md.index("[0:03]")
    assert "evidencia/01_0m12s.jpg" in md
    assert "## ✅ Checks pasados" in md and "Pantalla negra" in md and "Color de marca" not in md.split("## ✅ Checks pasados")[1]


def test_render_approved_report():
    md = render_report("ok.mp4", PROBE, [], "approved", {}, datetime(2026, 9, 11))
    assert md.startswith("# 🟢 ok.mp4 — APROBADO") and "## 🔴" not in md


def test_render_error_report():
    md = render_report("x.mp4", PROBE, [fnd("j", "warning", 0, check="judge_unavailable")], "error", {}, datetime(2026, 9, 11))
    assert md.startswith("# ❌ x.mp4 — ERROR")


def test_judge_checks_are_pending_not_passed_when_judge_unavailable():
    fs = [fnd("j", "warning", 0, check="judge_unavailable", typ="tecnico")]
    md = render_report("x.mp4", PROBE, fs, "error", {}, datetime(2026, 9, 11))
    passed = md.split("## ✅ Checks pasados")[1].split("## ⏳")[0]
    assert "Bloopers" not in passed
    assert "Pantalla negra" in passed          # los checks de código sí se revisaron
    assert "## ⏳ Pendientes de revisión (Claude no disponible)" in md
    pending = md.split("## ⏳ Pendientes de revisión (Claude no disponible)")[1]
    assert "Bloopers" in pending and "Reglas de marca (criterio)" in pending


def test_item_line_includes_spanish_type_label():
    md = render_report("x.mp4", PROBE, [fnd("b", "blocker", 12, typ="marca")], "rejected", {}, datetime(2026, 9, 11))
    assert "Marca —" in md
    assert "**[0:12] Marca — Tb**" in md


def test_write_evidence_crops_with_bbox(tmp_path):
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    (job.dir / "frames").mkdir()
    Image.new("RGB", (108, 192), (0, 0, 0)).save(job.path("frames/sec_0025.jpg"))
    fs = [fnd("b", "blocker", 12, frame="frames/sec_0025.jpg", bbox=[0.1, 0.4, 0.8, 0.1]), fnd("n", "warning", 3)]
    ev = write_evidence(job, fs)
    assert ev == {"b": "evidencia/01_0m12s.jpg"}
    assert job.path(ev["b"]).exists()


def test_write_evidence_skips_malformed_bbox_without_raising(tmp_path):
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    (job.dir / "frames").mkdir()
    Image.new("RGB", (108, 192), (0, 0, 0)).save(job.path("frames/sec_0025.jpg"))
    Image.new("RGB", (108, 192), (0, 0, 0)).save(job.path("frames/sec_0040.jpg"))
    fs = [fnd("bad", "blocker", 12, frame="frames/sec_0025.jpg", bbox=[0.5, 0.5, -0.4, 0.1]),
          fnd("good", "warning", 20, frame="frames/sec_0040.jpg", bbox=[0.1, 0.1, 0.2, 0.2])]
    ev = write_evidence(job, fs)
    assert "good" in ev
    assert job.path(ev["good"]).exists()


def test_write_evidence_clears_previous_run(tmp_path):
    """Reintento del mismo video: las evidencias viejas no deben sobrevivir."""
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    (job.dir / "frames").mkdir()
    (job.dir / "evidencia").mkdir()
    stale = job.path("evidencia/99_old.jpg"); stale.write_bytes(b"viejo")
    Image.new("RGB", (108, 192), (0, 0, 0)).save(job.path("frames/sec_0025.jpg"))
    ev = write_evidence(job, [fnd("b", "blocker", 12, frame="frames/sec_0025.jpg", bbox=[0.1, 0.4, 0.8, 0.1])])
    assert not stale.exists()
    assert sorted(p.name for p in job.path("evidencia").iterdir()) == ["01_0m12s.jpg"]
    assert ev == {"b": "evidencia/01_0m12s.jpg"}


def test_build_report_writes_file(tmp_path):
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    p, evidencia = build_report(job, PROBE, [], "approved")
    assert evidencia == {}
    assert p == job.path("reporte.md") and "APROBADO" in p.read_text()
