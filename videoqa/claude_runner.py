from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from videoqa.config import load_token

Runner = Callable[[str, Path], str]

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


class ClaudeError(Exception):
    """claude -p falló o devolvió error."""


class UsageLimitError(ClaudeError):
    """La cuenta de Claude se quedó sin uso disponible hasta `resets_at` (None si no lo dice).

    No es un fallo del video ni de la sesión: reintentar antes de esa hora solo gasta
    intentos, y tratarlo como "juez caído" entregaba el video con los hallazgos sin filtrar.
    """

    def __init__(self, message: str, resets_at: datetime | None = None):
        super().__init__(message)
        self.resets_at = resets_at


# "You've hit your session limit · resets 7:20pm (America/Managua)",
# "Claude usage limit reached. Your limit will reset at 5pm", "5-hour limit reached ∙ resets 3am"
_LIMIT_RE = re.compile(r"\b(?:session|usage|weekly|daily|5-hour|opus)\s+limit\b|hit your limit|limit (?:reached|will reset)", re.I)
_RESET_RE = re.compile(r"reset(?:s)?(?:\s+at)?\s+(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?(?:\s*\(([^)]+)\))?", re.I)


def parse_reset(text: str, now: datetime | None = None) -> datetime | None:
    """Hora de reinicio que anuncia el mensaje de límite, como datetime con zona.

    El mensaje da solo la hora ("7:20pm"): si ya pasó hoy, es la de mañana.
    """
    m = _RESET_RE.search(text)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    ampm = (m.group(3) or "").lower().replace(".", "")
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    tz = None
    if m.group(4):
        try:
            tz = ZoneInfo(m.group(4).strip())
        except (ZoneInfoNotFoundError, ValueError):
            tz = None
    now = now.astimezone(tz) if now and tz else (now or datetime.now(tz).astimezone(tz))
    when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if when <= now:
        when += timedelta(days=1)
    return when


def _claude_error(message: str) -> ClaudeError:
    if _LIMIT_RE.search(message):
        return UsageLimitError(message, parse_reset(message))
    return ClaudeError(message)


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


# Prompt de sistema corto para `claude -p`. Sin él, cada llamada arrastra el de Claude Code
# completo (pensado para programar, con instrucciones de todas sus herramientas), y lo vuelve
# a procesar en cada paso. Las instrucciones de verdad van en el mensaje.
LEAN_SYSTEM_PROMPT = ("Sigue al pie de la letra las instrucciones del mensaje. Usa la herramienta Read "
                      "solo para abrir los archivos que el mensaje indique. Responde exactamente en el "
                      "formato que se pide, sin texto adicional.")

# Las Macs pueden tener una versión de Claude Code sin `--tools`/`--system-prompt`. Si la
# primera llamada los rechaza, se recuerda aquí y las siguientes van sin ellos.
_lean_supported = True
_UNKNOWN_OPTION = ("unknown option", "unknown argument", "unrecognized option")


def _run(cmd: list[str], prompt: str, cwd: Path, timeout: int, claude_bin: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=cwd, timeout=timeout,
                              env=claude_env())
    except subprocess.TimeoutExpired as e:
        raise ClaudeError(f"claude -p superó {timeout}s") from e
    except OSError as e:  # p.ej. FileNotFoundError si el binario `claude` no existe
        raise ClaudeError(f"no se pudo ejecutar {claude_bin}: {e}") from e


def run_claude(prompt: str, cwd: Path, claude_bin: str = "claude", timeout: int = 600,
               allowed_tools: tuple[str, ...] = ("Read",), lean: bool = True) -> str:
    global _lean_supported
    base = [claude_bin, "-p", "--output-format", "json"]
    if allowed_tools:
        base += ["--allowedTools", ",".join(allowed_tools)]
    use_lean = lean and _lean_supported
    extra = ["--tools", ",".join(allowed_tools), "--system-prompt", LEAN_SYSTEM_PROMPT] if use_lean else []
    proc = _run(base + extra, prompt, cwd, timeout, claude_bin)
    if use_lean and proc.returncode != 0 and any(m in (proc.stderr or "").lower() for m in _UNKNOWN_OPTION):
        _lean_supported = False
        proc = _run(base, prompt, cwd, timeout, claude_bin)
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
        raise _claude_error(f"claude -p salió con {proc.returncode}: {detail}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ClaudeError(f"salida no JSON: {proc.stdout[:500]}") from e
    if data.get("is_error"):
        raise _claude_error(str(data.get("result")))
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
