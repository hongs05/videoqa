from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Callable

Runner = Callable[[str, Path], str]

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


class ClaudeError(Exception):
    """claude -p falló o devolvió error."""


def run_claude(prompt: str, cwd: Path, claude_bin: str = "claude", timeout: int = 600,
               allowed_tools: tuple[str, ...] = ("Read",)) -> str:
    cmd = [claude_bin, "-p", "--output-format", "json", "--allowedTools", ",".join(allowed_tools)]
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise ClaudeError(f"claude -p superó {timeout}s") from e
    if proc.returncode != 0:
        raise ClaudeError(f"claude -p salió con {proc.returncode}: {proc.stderr[-2000:]}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ClaudeError(f"salida no JSON: {proc.stdout[:500]}") from e
    if data.get("is_error"):
        raise ClaudeError(str(data.get("result")))
    return str(data.get("result", ""))


def extract_json(text: str) -> dict:
    m = _FENCE.search(text)
    candidate = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    if not candidate:
        raise ValueError("no se encontró JSON en la respuesta")
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido: {e}") from e
