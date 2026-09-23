"""Juez de respaldo local: entra cuando Claude se queda sin uso."""
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tests.unit.test_espera import MANAGUA, MSG, _Speller, _video_con_etapas_cacheadas
from videoqa import backends, cli
from videoqa.claude_runner import UsageLimitError
from videoqa.config import Settings, load_rules
from videoqa.doctor_state import load_wait_until, wait_state_path, write_wait_state
from videoqa.findings import Finding
from videoqa.local_judge import LocalJudgeError, apply_fallback, call_ollama, fallback_config
from videoqa.pipeline import Result, process_video
from videoqa.watcher import watch

VEREDICTO = json.dumps({"findings": [{"type": "blooper", "severity": "blocker", "t_start": 3, "t_end": 4,
                                      "title": "Toma fallida", "detail": "dice otra vez"}],
                        "dismissed_code_findings": [], "guion_real_md": ""})


def _rules(activo=True, url="http://127.0.0.1:9"):
    r = load_rules()
    r["juez_respaldo"] = {**r.get("juez_respaldo", {}), "activo": activo, "url": url, "timeout_s": 5}
    return r


def _sin_uso(prompt, cwd):
    raise UsageLimitError(MSG, datetime(2099, 9, 22, 19, 20, tzinfo=MANAGUA))


class _Ollama:
    """Servidor falso de Ollama: guarda las peticiones y responde `reply`."""

    def __init__(self, reply=VEREDICTO, status=200):
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                outer.requests.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                body = json.dumps({"message": {"role": "assistant", "content": reply}}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def ollama():
    srv = _Ollama()
    yield srv
    srv.close()


@pytest.fixture(autouse=True)
def _speller():
    backends.register_speller(_Speller)
    yield
    backends.reset()


def test_apagado_por_defecto():
    assert fallback_config(load_rules()) is None
    assert fallback_config(_rules())["modelo"] == "qwen3.5:4b"


def test_peticion_a_ollama(ollama, tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\xff\xd8jpeg")
    out = call_ollama("hola", [img], {**fallback_config(_rules(url=ollama.url))})
    path, body = ollama.requests[0]
    assert out == VEREDICTO and path == "/api/chat"
    assert body["model"] == "qwen3.5:4b" and body["format"] == "json" and body["stream"] is False
    assert body["keep_alive"] == 0 and body["think"] is False and body["options"]["num_ctx"] == 16384
    assert body["messages"][1]["content"] == "hola" and len(body["messages"][1]["images"]) == 1


def test_ollama_apagado_da_error_claro(tmp_path):
    with pytest.raises(LocalJudgeError, match="no se pudo hablar con Ollama"):
        call_ollama("hola", [], fallback_config(_rules(url="http://127.0.0.1:9")))


def test_respaldo_no_puede_quitar_bloqueantes():
    code = [Finding(id="b", type="ortografia", severity="blocker", t_start=0, t_end=1, title="t", detail="d"),
            Finding(id="w", type="tecnico", severity="warning", t_start=0, t_end=1, title="t", detail="d")]
    out = apply_fallback(code, {"dismissed": [{"id": "b", "reason": "logo"}, {"id": "w", "reason": "estilo"}],
                                "findings": []}, "qwen3.5:4b")
    by_id = {f.id: f for f in out}
    assert by_id["b"].severity == "warning" and "cree que no es error (logo)" in by_id["b"].detail
    assert "w" not in by_id
    assert by_id["respaldo-aviso"].title == "Revisado con el juez de respaldo"


def test_sin_uso_de_claude_revisa_el_respaldo(ollama, tmp_path):
    video, s = _video_con_etapas_cacheadas(tmp_path)
    res = process_video(video, s, _rules(url=ollama.url), _sin_uso)
    assert res.status == "rejected" and res.dest is not None  # el blooper del respaldo bloquea
    assert any(f.source == "respaldo" and f.title == "Toma fallida" for f in res.findings)
    assert any(f.id == "respaldo-aviso" for f in res.findings)
    assert (res.dest / "guion_real.md").read_text().startswith("## Guion (transcripción automática")
    assert json.loads(wait_state_path().read_text())["respaldo"] is True
    assert len(ollama.requests) == 1
    prompt = ollama.requests[0][1]["messages"][1]["content"]
    assert "ya van ADJUNTOS" in prompt and "# Datos del video" in prompt


def test_con_la_espera_activa_no_se_llama_a_claude(ollama, tmp_path):
    write_wait_state(datetime(2099, 1, 1, tzinfo=MANAGUA), "")
    video, s = _video_con_etapas_cacheadas(tmp_path)
    llamadas = []
    res = process_video(video, s, _rules(url=ollama.url), lambda p, c: llamadas.append(1) or "")
    assert llamadas == [] and res.status == "rejected" and len(ollama.requests) == 1


def test_si_el_respaldo_falla_el_video_espera(tmp_path):
    video, s = _video_con_etapas_cacheadas(tmp_path)
    res = process_video(video, s, _rules(url="http://127.0.0.1:9"), _sin_uso)
    assert res.status == "waiting" and video.exists()
    assert json.loads(wait_state_path().read_text())["videos"] == ["reel.mp4"]


def test_respaldo_apagado_mantiene_la_espera(tmp_path):
    video, s = _video_con_etapas_cacheadas(tmp_path)
    assert process_video(video, s, _rules(activo=False), _sin_uso).status == "waiting"


def test_watch_con_respaldo_no_arranca_en_pausa(tmp_path):
    s = Settings(drive_root=tmp_path / "drive", jobs_dir=tmp_path / "jobs")
    s.entrada.mkdir(parents=True)
    (s.entrada / "a.mp4").write_bytes(b"1")
    write_wait_state(datetime(2099, 1, 1, tzinfo=MANAGUA), "a.mp4")
    vistos = []
    watch(s, _rules(), runner=lambda p, c: "", once=True, sleep=lambda x: None, stable_wait_s=0,
          process=lambda v, *a, **k: vistos.append(v.name) or Result("approved", [], None))
    assert vistos == ["a.mp4"]


def test_cli_respaldo(ollama, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_rules", lambda: _rules(activo=False, url=ollama.url))
    assert cli.main(["respaldo"]) == 0
    assert capsys.readouterr().out.startswith("RESPALDO OK (apagado) · qwen3.5:4b respondió:")


def test_cli_respaldo_sin_ollama(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_rules", lambda: _rules(url="http://127.0.0.1:9"))
    assert cli.main(["respaldo"]) == 1
    assert "RESPALDO NO DISPONIBLE (encendido)" in capsys.readouterr().out
