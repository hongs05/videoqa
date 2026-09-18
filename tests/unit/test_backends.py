import pytest

from videoqa import backends


@pytest.fixture(autouse=True)
def _limpio():
    backends.reset()
    yield
    backends.reset()


def test_sin_registro_devuelve_los_de_apple():
    from videoqa.checks.spelling import MacSpellChecker
    from videoqa.stages.ocr import _ocr_frame_apple
    from videoqa.stages.transcribe import _transcribe_apple

    assert backends.get_ocr() is _ocr_frame_apple
    assert backends.get_transcriber() is _transcribe_apple
    assert backends.get_speller() is MacSpellChecker


def test_registrar_reemplaza():
    def ocr(path):
        return [{"text": "x", "conf": 1.0, "bbox": [0, 0, 1, 1]}]

    backends.register_ocr(ocr)
    assert backends.get_ocr() is ocr


def test_reset_vuelve_al_defecto():
    backends.register_ocr(lambda path: [])
    backends.reset()
    from videoqa.stages.ocr import _ocr_frame_apple

    assert backends.get_ocr() is _ocr_frame_apple


def test_ocr_frame_usa_el_registrado(tmp_path):
    from videoqa.stages.ocr import ocr_frame

    llamadas = []

    def ocr(path):
        llamadas.append(path)
        return [{"text": "hola", "conf": 0.9, "bbox": [0.1, 0.2, 0.3, 0.4]}]

    backends.register_ocr(ocr)
    out = ocr_frame(tmp_path / "f.jpg")
    assert out[0]["text"] == "hola" and llamadas == [tmp_path / "f.jpg"]


def test_transcribe_usa_el_registrado(tmp_path):
    from videoqa.job import Job
    from videoqa.stages.transcribe import transcribe

    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")

    def asr(job, has_audio, model):
        return {"language": "es", "text": "hola", "segments": [{"start": 0.0, "end": 1.0, "text": "hola"}]}

    backends.register_transcriber(asr)
    assert transcribe(job, True, "modelo")["text"] == "hola"


def test_transcribe_sin_audio_no_llama_al_backend(tmp_path):
    from videoqa.job import Job
    from videoqa.stages.transcribe import transcribe

    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")

    def asr(job, has_audio, model):
        raise AssertionError("no debería llamarse sin audio")

    backends.register_transcriber(asr)
    assert transcribe(job, False, "modelo") == {"language": "es", "text": "", "segments": []}


def test_check_spelling_usa_el_corrector_registrado():
    from videoqa.checks.spelling import check_spelling
    from videoqa.config import load_rules

    class Corrector:
        def is_known(self, w):
            return w.lower() != "kasa"

        def unknown(self, words):
            return {w for w in words if not self.is_known(w)}

        def correction(self, w):
            return "casa"

    backends.register_speller(lambda: Corrector())
    apps = [{"text": "la kasa", "bbox": [0.1, 0.4, 0.5, 0.1], "t_start": 1.0, "t_end": 3.0,
             "frame": "frames/a.jpg", "frames": [], "conf": 1.0}]
    fs = check_spelling(apps, set(), load_rules())
    assert len(fs) == 1 and "kasa" in fs[0].title and "casa" in fs[0].suggestion
