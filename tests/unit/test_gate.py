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
    s.entrada.mkdir(parents=True, exist_ok=True)
    video = s.entrada / "promo.mp4"; video.write_bytes(b"video")
    job = Job(video, s.jobs_dir)
    job.path("reporte.md").write_text("# r")
    job.path("guion_real.md").write_text("g")
    (job.dir / "evidencia").mkdir(exist_ok=True); job.path("evidencia/01_0m01s.jpg").write_bytes(b"jpg")
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


def test_deliver_keeps_previous_version_when_destination_exists(tmp_path):
    """El editor resube el video corregido con el mismo nombre: la entrega anterior
    (video + reporte) no se borra, se aparta en `_anteriores/`."""
    s, job, _ = setup(tmp_path)
    old = s.aprobado / "promo"; old.mkdir(parents=True)
    (old / "promo.mp4").write_bytes(b"v1"); (old / "reporte.md").write_text("viejo")
    deliver(job, s, "approved")
    assert (old / "promo.mp4").read_bytes() == b"video"
    guardadas = list((s.aprobado / "_anteriores").iterdir())
    assert len(guardadas) == 1 and guardadas[0].name.startswith("promo_")
    assert (guardadas[0] / "promo.mp4").read_bytes() == b"v1"
    assert (guardadas[0] / "reporte.md").read_text() == "viejo"


def test_deliver_keeps_every_previous_version(tmp_path):
    s, job, _ = setup(tmp_path)
    old = s.aprobado / "promo"; old.mkdir(parents=True); (old / "promo.mp4").write_bytes(b"v1")
    deliver(job, s, "approved")
    s2, job2, _ = setup(tmp_path)  # tercera subida con el mismo nombre
    deliver(job2, s2, "approved")
    assert len(list((s.aprobado / "_anteriores").iterdir())) == 2


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
