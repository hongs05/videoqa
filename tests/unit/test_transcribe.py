import pytest
from videoqa.job import Job
from videoqa.stages.transcribe import empty_transcript, normalize, transcribe

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

def test_transcribe_without_audio_returns_fresh_segments_list(fixture_videos, tmp_path):
    job = Job(fixture_videos["no_audio"], tmp_path)
    out1 = transcribe(job, has_audio=False, model="x")
    out2 = transcribe(job, has_audio=False, model="x")
    assert out1["segments"] is not out2["segments"]

def test_empty_transcript_returns_fresh_dict_each_call():
    a = empty_transcript()
    b = empty_transcript()
    assert a == b
    assert a["segments"] is not b["segments"]

@pytest.mark.slow
def test_transcribe_real_fixture(fixture_videos, tmp_path):
    out = transcribe(Job(fixture_videos["clean"], tmp_path), has_audio=True,
                     model="mlx-community/whisper-large-v3-turbo")
    assert "verano" in out["text"].lower()
