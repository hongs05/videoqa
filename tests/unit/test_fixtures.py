import subprocess, json
from tests.fixtures.make_fixtures import build_all

def test_build_all_creates_four_videos(fixture_videos):
    assert set(fixture_videos) == {"spelling_color", "black_screen", "clean", "no_audio"}
    for p in fixture_videos.values():
        assert p.exists() and p.stat().st_size > 10_000

def test_no_audio_fixture_has_no_audio_stream(fixture_videos):
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams",
                          str(fixture_videos["no_audio"])], capture_output=True, text=True, check=True).stdout
    assert all(s["codec_type"] != "audio" for s in json.loads(out)["streams"])
