from pathlib import Path
from videoqa.config import Settings
from videoqa.pipeline import Result
from videoqa.watcher import is_stable, list_videos, watch

def test_list_videos_filters_and_orders(tmp_path):
    (tmp_path / "b.mp4").write_bytes(b"1"); (tmp_path / "a.MOV").write_bytes(b"1")
    (tmp_path / ".oculto.mp4").write_bytes(b"1"); (tmp_path / "x.txt").write_bytes(b"1"); (tmp_path / "c.mp4.partial").write_bytes(b"1")
    import os, time
    os.utime(tmp_path / "b.mp4", (time.time() - 50, time.time() - 50))
    assert [p.name for p in list_videos(tmp_path)] == ["b.mp4", "a.MOV"]

def test_is_stable_true_when_size_constant(tmp_path):
    p = tmp_path / "v.mp4"; p.write_bytes(b"1234")
    assert is_stable(p, wait_s=2, poll_s=1, sleep=lambda s: None) is True

def test_is_stable_false_when_growing(tmp_path):
    p = tmp_path / "v.mp4"; p.write_bytes(b"1")
    def grow(s): p.write_bytes(p.read_bytes() + b"1")
    assert is_stable(p, wait_s=2, poll_s=1, sleep=grow) is False

def test_watch_once_processes_stable_videos_and_skips_failed(tmp_path):
    s = Settings(drive_root=tmp_path / "drive", jobs_dir=tmp_path / "jobs")
    s.entrada.mkdir(parents=True)
    (s.entrada / "a.mp4").write_bytes(b"1"); (s.entrada / "b.mp4").write_bytes(b"1")
    seen = []
    def fake_process(video, settings, rules, runner, sheet=None):
        seen.append(video.name)
        if video.name == "b.mp4":
            return Result("error", [], None, "roto")
        video.unlink()  # simula deliver() moviendo el archivo fuera de Entrada
        return Result("approved", [], None)
    watch(s, {}, runner=lambda p, c: "", once=True, process=fake_process, sleep=lambda x: None, stable_wait_s=0)
    assert sorted(seen) == ["a.mp4", "b.mp4"]
    watch(s, {}, runner=lambda p, c: "", once=True, process=fake_process, sleep=lambda x: None, stable_wait_s=0)
    assert sorted(seen) == ["a.mp4", "b.mp4"]  # b falló hace < retry_after_s: no se reintenta aún

def test_watch_once_continues_after_process_raises(tmp_path):
    s = Settings(drive_root=tmp_path / "drive", jobs_dir=tmp_path / "jobs")
    s.entrada.mkdir(parents=True)
    (s.entrada / "a.mp4").write_bytes(b"1")
    (s.entrada / "b.mp4").write_bytes(b"22")
    seen = []
    def fake_process(video, settings, rules, runner, sheet=None):
        seen.append(video.name)
        if video.name == "b.mp4":
            raise RuntimeError("boom")
        video.unlink()
        return Result("approved", [], None)
    # No debe propagar la excepción de b.mp4; a.mp4 se procesa igual.
    watch(s, {}, runner=lambda p, c: "", once=True, process=fake_process, sleep=lambda x: None, stable_wait_s=0)
    assert sorted(seen) == ["a.mp4", "b.mp4"]
    assert not (s.entrada / "a.mp4").exists()
    assert (s.entrada / "b.mp4").exists()
    # Pase inmediato siguiente: b.mp4 sigue "reciente" en el estado de fallo -> se salta.
    seen.clear()
    watch(s, {}, runner=lambda p, c: "", once=True, process=fake_process, sleep=lambda x: None, stable_wait_s=0)
    assert seen == []

def test_watch_warns_once_when_file_is_unstable_too_long(tmp_path, caplog):
    """Un archivo que lleva >10 min 'sincronizando' merece un aviso (Drive atascado)."""
    import logging
    s = Settings(drive_root=tmp_path / "drive", jobs_dir=tmp_path / "jobs")
    s.entrada.mkdir(parents=True)
    growing = s.entrada / "g.mp4"; growing.write_bytes(b"1")

    def never_stable(video, settings, rules, runner, sheet=None):
        raise AssertionError("no debería procesarse un archivo inestable")

    passes = {"n": 0}

    def loop_sleep(_):
        passes["n"] += 1
        growing.write_bytes(growing.read_bytes() + b"1")   # sigue creciendo: nunca estable
        if passes["n"] > 8:
            raise StopIteration

    with caplog.at_level(logging.WARNING, logger="videoqa"):
        try:
            watch(s, {}, runner=lambda p, c: "", once=False, process=never_stable,
                  sleep=loop_sleep, stable_wait_s=1, unstable_warn_s=0)
        except StopIteration:
            pass

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len([w for w in warnings if "sincronizando" in w]) == 1


def test_watch_reprocesses_reuploaded_file_with_different_size(tmp_path):
    s = Settings(drive_root=tmp_path / "drive", jobs_dir=tmp_path / "jobs")
    s.entrada.mkdir(parents=True)
    video_path = s.entrada / "c.mp4"
    video_path.write_bytes(b"1")
    seen = []
    def fake_process(video, settings, rules, runner, sheet=None):
        seen.append((video.name, video.stat().st_size))
        return Result("error", [], None, "roto")
    watch(s, {}, runner=lambda p, c: "", once=True, process=fake_process, sleep=lambda x: None, stable_wait_s=0)
    assert seen == [("c.mp4", 1)]
    # El mismo pase inmediato no reprocesa (falló hace < retry_after_s).
    watch(s, {}, runner=lambda p, c: "", once=True, process=fake_process, sleep=lambda x: None, stable_wait_s=0)
    assert seen == [("c.mp4", 1)]
    # El editor corrige y resube con el mismo nombre pero contenido distinto: se
    # procesa de inmediato en vez de esperar retry_after_s.
    video_path.write_bytes(b"1234567890")
    watch(s, {}, runner=lambda p, c: "", once=True, process=fake_process, sleep=lambda x: None, stable_wait_s=0)
    assert seen == [("c.mp4", 1), ("c.mp4", 10)]


def test_watch_recorre_varias_carpetas(tmp_path):
    """Una Mac puede vigilar su carpeta local y la de Drive a la vez."""
    drive = Settings(drive_root=tmp_path / "drive", jobs_dir=tmp_path / "jobs")
    local = Settings(drive_root=tmp_path / "local", jobs_dir=tmp_path / "jobs")
    drive.entrada.mkdir(parents=True)
    local.entrada.mkdir(parents=True)
    (drive.entrada / "de_drive.mp4").write_bytes(b"1")
    (local.entrada / "de_local.mp4").write_bytes(b"1")

    vistos = []

    def fake_process(video, settings, rules, runner, sheet=None):
        vistos.append((video.name, settings.drive_root.name))
        video.unlink()
        return Result("approved", [], None)

    watch([drive, local], {}, runner=lambda p, c: "", once=True, process=fake_process,
          sleep=lambda x: None, stable_wait_s=0)
    assert sorted(vistos) == [("de_drive.mp4", "drive"), ("de_local.mp4", "local")]


def test_cada_video_se_procesa_con_los_settings_de_su_carpeta(tmp_path):
    """El video local no debe entregarse en las carpetas de Drive."""
    drive = Settings(drive_root=tmp_path / "drive", jobs_dir=tmp_path / "jobs", sheet_id="abc")
    local = Settings(drive_root=tmp_path / "local", jobs_dir=tmp_path / "jobs")
    drive.entrada.mkdir(parents=True)
    local.entrada.mkdir(parents=True)
    (local.entrada / "mio.mp4").write_bytes(b"1")

    recibidos = []

    def fake_process(video, settings, rules, runner, sheet=None):
        recibidos.append(settings)
        video.unlink()
        return Result("approved", [], None)

    watch([drive, local], {}, runner=lambda p, c: "", once=True, process=fake_process,
          sleep=lambda x: None, stable_wait_s=0)
    assert len(recibidos) == 1
    assert recibidos[0].drive_root == tmp_path / "local"
    assert recibidos[0].sheet_id is None


def test_watch_sigue_aceptando_una_sola_carpeta(tmp_path):
    """Compatibilidad: quien pase un Settings suelto tiene que seguir funcionando."""
    s = Settings(drive_root=tmp_path / "drive", jobs_dir=tmp_path / "jobs")
    s.entrada.mkdir(parents=True)
    (s.entrada / "a.mp4").write_bytes(b"1")
    vistos = []

    def fake_process(video, settings, rules, runner, sheet=None):
        vistos.append(video.name)
        video.unlink()
        return Result("approved", [], None)

    watch(s, {}, runner=lambda p, c: "", once=True, process=fake_process,
          sleep=lambda x: None, stable_wait_s=0)
    assert vistos == ["a.mp4"]
