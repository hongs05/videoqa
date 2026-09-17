import pytest
from PIL import Image

from videoqa.job import Job
from videoqa.stages.frames import _run, extract_frames


def test_extract_two_fps_plus_scene_frames(fixture_videos, tmp_path):
    job = Job(fixture_videos["clean"], tmp_path)
    fr = extract_frames(job, scene_cuts=[1.0, 10.0], fps=2)
    seconds = [f for f in fr["frames"] if f["kind"] == "second"]
    scenes = [f for f in fr["frames"] if f["kind"] == "scene"]
    assert 22 <= len(seconds) <= 26
    assert len(scenes) == 2 and scenes[0]["t"] == 1.1
    assert fr["period"] == 0.5
    assert seconds[0]["t"] == 0.0 and seconds[1]["t"] == 0.5
    assert [f["t"] for f in fr["frames"]] == sorted(f["t"] for f in fr["frames"])
    img = Image.open(job.path(scenes[0]["file"]))
    assert img.size == (1080, 1920)


def test_run_wraps_ffmpeg_error_in_spanish(tmp_path):
    missing = tmp_path / "no_existe.mp4"
    with pytest.raises(RuntimeError) as exc_info:
        _run(["-i", str(missing), "-frames:v", "1", str(tmp_path / "out.jpg")])
    assert str(exc_info.value).startswith("ffmpeg falló")


def test_extract_frames_survives_one_failing_scene_seek(fixture_videos, tmp_path):
    job = Job(fixture_videos["clean"], tmp_path)
    fr = extract_frames(job, scene_cuts=[1.0, 9999.0], fps=2)
    scenes = [f for f in fr["frames"] if f["kind"] == "scene"]
    assert len(scenes) == 1
    assert scenes[0]["t"] == 1.1
