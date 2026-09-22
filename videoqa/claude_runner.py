from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable

from videoqa.config import load_token

Runner = Callable[[str, Path], str]

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


class ClaudeError(Exception):
    """claude -p falló o devolvió error."""


def claude_env() -> dict[str, str]:
    """Entorno para `claude -p`: el del proceso, más el token guardado si lo hay.

    `claude` lee CLAUDE_CODE_OAUTH_TOKEN; con eso el juez funciona aunque la
    sesión interactiva del CLI haya caducado (o nunca se haya iniciado).
    """
    env = dict(os.environ)
    token = load_token()
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    return env


def run_claude(prompt: str, cwd: Path, claude_bin: str = "claude", timeout: int = 600,
               allowed_tools: tuple[str, ...] = ("Read",)) -> str:
    cmd = [claude_bin, "-p", "--output-format", "json"]
    if allowed_tools:
        cmd += ["--allowedTools", ",".join(allowed_tools)]
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=cwd, timeout=timeout,
                               env=claude_env())
    except subprocess.TimeoutExpired as e:
        raise ClaudeError(f"claude -p superó {timeout}s") from e
    except OSError as e:  # p.ej. FileNotFoundError si el binario `claude` no existe
        raise ClaudeError(f"no se pudo ejecutar {claude_bin}: {e}") from e
    if proc.returncode != 0:
        detail = ""
        try:
            stdout_data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            stdout_data = None
        if isinstance(stdout_data, dict):
            detail = str(stdout_data.get("result") or stdout_data.get("error") or "")
        if not detail:
            detail = proc.stderr[-2000:]
        raise ClaudeError(f"claude -p salió con {proc.returncode}: {detail}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ClaudeError(f"salida no JSON: {proc.stdout[:500]}") from e
    if data.get("is_error"):
        raise ClaudeError(str(data.get("result")))
    return str(data.get("result", ""))


def extract_json(text: str) -> dict:
    """Primer objeto JSON de la respuesta del modelo.

    Antes se tomaba del primer ``{`` al último ``}``: bastaba una llave en el texto
    que acompaña al JSON (o un segundo bloque) para que todo el veredicto fuera
    "JSON inválido" y el video terminara en error. Ahora se prueba primero el bloque
    ```json``` y luego cada ``{`` hasta dar con un objeto que decodifique.
    """
    decoder = json.JSONDecoder()
    m = _FENCE.search(text)
    starts = [m.start(1)] if m else []
    starts += [i for i, ch in enumerate(text) if ch == "{" and i not in starts]
    if not starts:
        raise ValueError("no se encontró JSON en la respuesta")
    first_error: json.JSONDecodeError | None = None
    for i in starts:
        try:
            data, _ = decoder.raw_decode(text, i)
        except json.JSONDecodeError as e:
            first_error = first_error or e
            continue
        if isinstance(data, dict):
            return data
    raise ValueError(f"JSON inválido: {first_error}" if first_error else "la respuesta no contiene un objeto JSON")
