import shutil

import pytest

from videoqa.config import Settings
from videoqa.findings import Finding
from videoqa.gate import decide, deliver
from videoqa.job import Job


def f(sev):
    return Finding(id="x", type="marca", severity=sev, t_start=0, t_end=1, title="t", detail="d")


def test_decide():
    assert decide([]) == "approved"
    assert decide([f("warning"), f("info")]) == "approved"
    assert decide([f("warning"), f("blocker")]) == "rejected"


def setup(tmp_path):
    drive = tmp_path / "drive"
    s = Settings(drive_root=drive, jobs_dir=tmp_path / "jobs")
    s.entrada.mkdir(parents=True)
    video = s.entrada / "promo.mp4"; video.write_bytes(b"video")
    job = Job(video, s.jobs_dir)
    job.path("reporte.md").write_text("# r")
    job.path("guion_real.md").write_text("g")
    (job.dir / "evidencia").mkdir(); job.path("evidencia/01_0m01s.jpg").write_bytes(b"jpg")
    return s, job, video


def test_deliver_approved_moves_video_and_artifacts(tmp_path):
    s, job, video = setup(tmp_path)
    dest = deliver(job, s, "approved")
    assert dest == s.aprobado / "promo"
    assert not video.exists() and (dest / "promo.mp4").read_bytes() == b"video"
    assert (dest / "reporte.md").exists() and (dest / "guion_real.md").exists() and (dest / "evidencia" / "01_0m01s.jpg").exists()


def test_deliver_rejected_and_error_go_to_con_errores(tmp_path):
    s, job, _ = setup(tmp_path)
    assert deliver(job, s, "rejected").parent == s.con_errores
    s2, job2, _ = setup(tmp_path / "b")
    assert deliver(job2, s2, "error").parent == s2.con_errores


def test_deliver_overwrites_existing_destination(tmp_path):
    s, job, _ = setup(tmp_path)
    old = s.aprobado / "promo"; old.mkdir(parents=True); (old / "viejo.txt").write_text("x")
    deliver(job, s, "approved")
    assert not (old / "viejo.txt").exists() and (old / "promo.mp4").exists()


def test_deliver_rejects_unsafe_name_without_deleting_anything(tmp_path):
    """Un video llamado `...mp4` tiene stem `..`: `03_Aprobado/..` es la raíz de Drive."""
    drive = tmp_path / "drive"
    s = Settings(drive_root=drive, jobs_dir=tmp_path / "jobs")
    s.entrada.mkdir(parents=True)
    s.aprobado.mkdir(parents=True)
    s.con_errores.mkdir(parents=True)
    canary = s.con_errores / "otro_video"; canary.mkdir(); (canary / "reporte.md").write_text("no borrar")
    video = s.entrada / "...mp4"; video.write_bytes(b"video")
    # `Job` ya rechaza el stem inseguro (ver test_job.py); aquí se comprueba que
    # `deliver` conserva su propia guarda aunque el Job llegue por otra vía.
    job = Job(s.entrada / "seguro.mp4", s.jobs_dir)
    job.video, job.name = video, video.stem
    assert job.name == ".."

    with pytest.raises(ValueError, match="inseguro"):
        deliver(job, s, "approved")

    assert drive.exists() and s.entrada.exists() and s.aprobado.exists()
    assert (canary / "reporte.md").read_text() == "no borrar"
    assert video.exists()


def test_deliver_leaves_video_in_entrada_when_artifact_copy_fails(tmp_path, monkeypatch):
    s, job, video = setup(tmp_path)

    def boom(src, dst, **kw):
        raise OSError("disco lleno")

    monkeypatch.setattr(shutil, "copy2", boom)
    with pytest.raises(OSError):
        deliver(job, s, "approved")
    assert video.exists()
    assert not (s.aprobado / "promo" / "promo.mp4").exists()
