import json
import subprocess
from pathlib import Path
import pytest
from videoqa.claude_runner import ClaudeError, extract_json, run_claude
from videoqa.config import token_path
from videoqa.claude_runner import claude_env

def test_extract_json_plain_and_fenced():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Aquí va:\n```json\n{"a": [1, 2]}\n```\ngracias') == {"a": [1, 2]}

def test_extract_json_ignora_llaves_en_el_texto_de_alrededor():
    """Del primer '{' al último '}' fallaba si el texto de alrededor traía llaves."""
    assert extract_json('Revisé {todo}. Veredicto: {"a": 1} (fin {ok})') == {"a": 1}
    assert extract_json('{"a": 1}\n\nY otro: {"b": 2}') == {"a": 1}
    assert extract_json('```json\n{"md": "```code```"}\n```') == {"md": "```code```"}


def test_extract_json_lista_no_es_veredicto():
    with pytest.raises(ValueError):
        extract_json('[1, 2]')


def test_extract_json_invalid_raises():
    with pytest.raises(ValueError):
        extract_json("sin json")

def test_run_claude_parses_result(monkeypatch, tmp_path):
    captured = {}
    def fake_run(cmd, **kw):
        captured["cmd"], captured["input"], captured["cwd"] = cmd, kw["input"], kw["cwd"]
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"is_error": False, "result": "hola"}), stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run_claude("prompt", cwd=tmp_path, claude_bin="claude-x") == "hola"
    assert captured["cmd"][:4] == ["claude-x", "-p", "--output-format", "json"]
    assert "--allowedTools" in captured["cmd"] and captured["input"] == "prompt" and captured["cwd"] == tmp_path

def test_run_claude_nonzero_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom"))
    with pytest.raises(ClaudeError):
        run_claude("p", cwd=tmp_path)

def test_run_claude_is_error_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 0, stdout=json.dumps({"is_error": True, "result": "rate limit"}), stderr=""))
    with pytest.raises(ClaudeError):
        run_claude("p", cwd=tmp_path)


# --- Fix round 1: hardening test ---

def test_run_claude_nonzero_with_empty_stderr_surfaces_stdout_result(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 1, stdout=json.dumps({"is_error": True, "result": "Failed to authenticate"}), stderr=""))
    with pytest.raises(ClaudeError, match="Failed to authenticate"):
        run_claude("p", cwd=tmp_path)


def test_run_claude_missing_binary_raises_claude_error(monkeypatch, tmp_path):
    def fake_run(cmd, **kw):
        raise FileNotFoundError(2, "No such file or directory")
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ClaudeError, match="no se pudo ejecutar"):
        run_claude("p", cwd=tmp_path, claude_bin="claude")


def test_claude_env_sin_token_no_toca_la_variable(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in claude_env()


def test_claude_env_con_token_lo_inyecta(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    token_path().parent.mkdir(parents=True, exist_ok=True)
    token_path().write_text("sk-ant-oat01-xyz\n")
    env = claude_env()
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-xyz"
    assert env["PATH"]  # conserva el entorno del proceso


def test_run_claude_pasa_el_env_al_subproceso(monkeypatch, tmp_path):
    token_path().parent.mkdir(parents=True, exist_ok=True)
    token_path().write_text("sk-ant-oat01-xyz")
    visto = {}

    def fake_run(cmd, **kw):
        visto.update(kw)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"is_error": False, "result": "ok"}), stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run_claude("hola", tmp_path) == "ok"
    assert visto["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-xyz"


def test_run_claude_sin_herramientas_omite_el_flag(monkeypatch, tmp_path):
    visto = {}
    def fake_run(cmd, **kw):
        visto["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"is_error": False, "result": "ok"}), stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    run_claude("hola", tmp_path, allowed_tools=())
    assert "--allowedTools" not in visto["cmd"]
