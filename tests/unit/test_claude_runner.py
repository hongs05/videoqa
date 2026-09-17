import json
import subprocess
from pathlib import Path
import pytest
from videoqa.claude_runner import ClaudeError, extract_json, run_claude

def test_extract_json_plain_and_fenced():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Aquí va:\n```json\n{"a": [1, 2]}\n```\ngracias') == {"a": [1, 2]}

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
