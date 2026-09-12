from PIL import Image

from videoqa.job import Job
from videoqa.stages.frames import extract_frames


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
