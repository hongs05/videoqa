import json
import pytest
from videoqa.job import Job

def test_run_stage_writes_output_and_caches(tmp_path):
    video = tmp_path / "promo.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    calls = []
    def fn(j):
        calls.append(j.name)
        return {"ok": True}
    assert job.run_stage("probe", "probe.json", fn) == {"ok": True}
    assert job.run_stage("probe", "probe.json", fn) == {"ok": True}
    assert calls == ["promo"]
    assert json.loads(job.path("probe.json").read_text()) == {"ok": True}
    assert job.state()["stages"]["probe"]["status"] == "done"

def test_failed_stage_records_state_and_reraises(tmp_path):
    video = tmp_path / "promo.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    def boom(j):
        raise RuntimeError("ffmpeg murió")
    with pytest.raises(RuntimeError):
        job.run_stage("probe", "probe.json", boom)
    assert job.state()["stages"]["probe"]["status"] == "failed"
    assert not job.path("probe.json").exists()

def test_reset_clears_dir(tmp_path):
    video = tmp_path / "promo.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    job.run_stage("probe", "probe.json", lambda j: {})
    job.reset()
    assert job.dir.exists() and not job.path("probe.json").exists()

def test_matches_current_video_without_state(tmp_path):
    video = tmp_path / "promo.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    assert job.matches_current_video() is False


def test_matches_current_video_after_record(tmp_path):
    video = tmp_path / "promo.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    job.record_video()
    assert job.matches_current_video() is True
    st = json.loads(job.state_path.read_text())
    assert st["video_size"] == 1 and "video_mtime" in st


def test_matches_current_video_false_after_reupload(tmp_path):
    import os, time
    video = tmp_path / "promo.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    job.record_video()
    video.write_bytes(b"contenido totalmente distinto")   # el editor resube otro archivo
    os.utime(video, (time.time() + 10, time.time() + 10))
    assert job.matches_current_video() is False


def test_record_video_preserves_stage_state(tmp_path):
    video = tmp_path / "promo.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    job.run_stage("probe", "probe.json", lambda j: {"ok": True})
    job.record_video()
    st = job.state()
    assert st["stages"]["probe"]["status"] == "done" and "video_size" in st
    assert job.matches_current_video() is True


def test_stage_marking_preserves_video_fingerprint(tmp_path):
    """Orden real del pipeline: record_video() primero, luego las etapas."""
    video = tmp_path / "promo.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    job.record_video()
    job.run_stage("probe", "probe.json", lambda j: {"ok": True})
    assert job.matches_current_video() is True
    assert job.state()["stages"]["probe"]["status"] == "done"


def test_unsafe_stem_rejected_before_creating_anything(tmp_path):
    """`...mp4` tiene stem `..`: `jobs/..` es el padre de jobs_root y `reset()` lo borraría."""
    jobs_root = tmp_path / "jobs"; jobs_root.mkdir()
    video = tmp_path / "...mp4"; video.write_bytes(b"x")
    with pytest.raises(ValueError, match="inseguro"):
        Job(video, jobs_root)
    assert list(jobs_root.iterdir()) == []


def test_unsafe_stem_single_dot_rejected(tmp_path):
    """`..mp4` tiene stem `.`: `jobs/.` es jobs_root mismo."""
    jobs_root = tmp_path / "jobs"; jobs_root.mkdir()
    with pytest.raises(ValueError, match="inseguro"):
        Job(tmp_path / "..mp4", jobs_root)
    assert list(jobs_root.iterdir()) == []


def test_unserializable_result_marks_failed_and_writes_nothing(tmp_path):
    video = tmp_path / "promo.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    with pytest.raises(TypeError):
        job.run_stage("probe", "probe.json", lambda j: {"x": object()})
    assert job.state()["stages"]["probe"]["status"] == "failed"
    assert not job.path("probe.json").exists()
    assert not job.path("probe.json.tmp").exists()
