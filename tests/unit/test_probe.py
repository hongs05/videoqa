from videoqa.job import Job
from videoqa.stages.probe import probe

def test_probe_reads_clean_fixture(fixture_videos, tmp_path):
    job = Job(fixture_videos["clean"], tmp_path)
    p = probe(job)
    assert 11.5 <= p["duration"] <= 12.5
    assert (p["width"], p["height"]) == (1080, 1920)
    assert abs(p["fps"] - 30) < 0.01
    assert p["has_audio"] is True

def test_probe_detects_missing_audio(fixture_videos, tmp_path):
    assert probe(Job(fixture_videos["no_audio"], tmp_path))["has_audio"] is False
