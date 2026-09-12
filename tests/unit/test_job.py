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
