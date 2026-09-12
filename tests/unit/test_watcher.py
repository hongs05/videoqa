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
