import pytest
from videoqa.job import Job
from videoqa.stages.transcribe import normalize, transcribe

def test_normalize_strips_and_drops_empty():
    raw = {"language": "es", "segments": [
        {"start": 0.0, "end": 1.234, "text": "  Hola  "},
        {"start": 1.3, "end": 2.0, "text": "   "},
        {"start": 2.0, "end": 3.0, "text": "mundo"}]}
    out = normalize(raw)
    assert out["segments"] == [{"start": 0.0, "end": 1.23, "text": "Hola"},
                               {"start": 2.0, "end": 3.0, "text": "mundo"}]
    assert out["text"] == "Hola mundo" and out["language"] == "es"

def test_transcribe_without_audio_returns_empty(fixture_videos, tmp_path):
    out = transcribe(Job(fixture_videos["no_audio"], tmp_path), has_audio=False, model="x")
    assert out == {"language": "es", "text": "", "segments": []}

@pytest.mark.slow
def test_transcribe_real_fixture(fixture_videos, tmp_path):
    out = transcribe(Job(fixture_videos["clean"], tmp_path), has_audio=True,
                     model="mlx-community/whisper-large-v3-turbo")
    assert "oferta" in out["text"].lower()
