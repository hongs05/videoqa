"""Juez de respaldo: un modelo local (Ollama) para cuando Claude se queda sin uso.

Se activa en `reglas.yaml` → `juez_respaldo.activo` (lo hace `/aura:respaldo`). Solo entra
cuando Claude responde con el límite de uso: en vez de dejar el video esperando horas, lo
revisa un modelo que corre en la propia Mac, gratis y sin enviar el video a ningún sitio.

Es un modelo pequeño (pensado para Macs de 8 GB), así que se le dan menos poderes que a Claude:
- Menos fotos y más pequeñas (no caben más en memoria).
- No puede quitar un bloqueante del código: si cree que no es error, el hallazgo baja a aviso
  con su razón, para que una persona lo mire.
- El reporte avisa de que la revisión la hizo el respaldo.
"""
from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

from videoqa.config import SKILL_PATH
from videoqa.findings import Finding
from videoqa.job import Job
from videoqa.judge import (JudgeError, ask_verdict, build_prompt, clear_stale_verdict, prepare_inputs,
                           verdict_result)

log = logging.getLogger("videoqa")

DEFAULTS = {"activo": False, "modelo": "qwen3.5:4b", "url": "http://localhost:11434", "max_frames": 6,
            "frame_height": 512, "num_ctx": 16384, "timeout_s": 900}

SYSTEM = ("Eres una revisora de calidad de videos para redes sociales. Sigue al pie de la letra las "
          "instrucciones del mensaje y responde ÚNICAMENTE con el JSON del veredicto.")


class LocalJudgeError(Exception):
    """El modelo local no está disponible o no respondió."""


def fallback_config(rules: dict) -> dict | None:
    """Configuración del juez de respaldo, o None si está apagado."""
    cfg = {**DEFAULTS, **(rules.get("juez_respaldo") or {})}
    return cfg if cfg.get("activo") else None


def call_ollama(prompt: str, images: list[Path], cfg: dict, system: str = SYSTEM) -> str:
    body = {
        "model": cfg["modelo"],
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": prompt,
                      "images": [base64.b64encode(p.read_bytes()).decode() for p in images]}],
        "stream": False,
        "format": "json",
        "think": False,  # sin "pensar": en un modelo pequeño solo añade minutos
        # keep_alive 0: se descarga al terminar. En 8 GB, Whisper y el OCR del video siguiente
        # necesitan esa memoria.
        "keep_alive": 0,
        "options": {"num_ctx": int(cfg["num_ctx"]), "temperature": 0},
    }
    req = urllib.request.Request(f"{cfg['url'].rstrip('/')}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=float(cfg["timeout_s"])) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise LocalJudgeError(f"Ollama respondió {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise LocalJudgeError(f"no se pudo hablar con Ollama en {cfg['url']} ({e})") from e
    except json.JSONDecodeError as e:
        raise LocalJudgeError("Ollama devolvió algo que no es JSON") from e
    content = (data.get("message") or {}).get("content")
    if not content:
        raise LocalJudgeError(f"Ollama no devolvió respuesta: {str(data)[:300]}")
    return content


def _simple_guion(transcript: dict) -> str:
    segs = transcript.get("segments") or []
    if not segs:
        return "## Escena 1 [0:00]\n(sin diálogo)"
    lines = [f"[{int(s['start']) // 60}:{int(s['start']) % 60:02d}] {s['text']}" for s in segs]
    return "## Guion (transcripción automática, sin revisar)\n" + "\n".join(lines)


def run_fallback_judge(job: Job, brand: dict, glossary_text: str, transcript: dict, ocr: dict, technical: dict,
                       code_findings: list[Finding], frames: list[dict], rules: dict, cfg: dict,
                       duration: float, corrections: list[dict] | None = None,
                       ask=None, skill_path: Path = SKILL_PATH) -> dict:
    """Mismo contrato que `run_judge`. `ask(prompt, images) -> texto` sustituye a Ollama en los tests."""
    small = {**rules, "claude": {**rules.get("claude", {}), "max_frames": int(cfg["max_frames"]),
                                 "frame_height": int(cfg["frame_height"])}}
    try:
        manifest = prepare_inputs(job, brand, glossary_text, transcript, ocr, technical, code_findings, frames,
                                  small, corrections=corrections)
        skill_text = skill_path.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        raise JudgeError(f"no se pudieron preparar las entradas del juez de respaldo: {e}") from e
    prompt = build_prompt(skill_text, manifest, duration, attached=True)
    images = [job.path(f["file"]) for f in manifest["frames"]]
    ask = ask or (lambda p, imgs: call_ollama(p, imgs, cfg))
    clear_stale_verdict(job)

    def ask_once(p: str) -> str:
        try:
            return ask(p, images)
        except LocalJudgeError as e:
            raise JudgeError(str(e)) from e  # sin Ollama no tiene sentido el segundo intento

    # A un modelo pequeño no se le exige el guion: si no lo da, se usa la transcripción.
    verdict = ask_verdict(job, prompt, ask_once, require_guion=False, label="juez de respaldo")
    if not verdict["guion_real_md"].strip():
        verdict["guion_real_md"] = _simple_guion(transcript)
    return verdict_result(job, verdict, manifest, code_findings, source="respaldo")


def apply_fallback(code_findings: list[Finding], result: dict, model: str) -> list[Finding]:
    """Combina hallazgos del código con el veredicto del respaldo, sin dejarle aprobar a ciegas.

    Lo que el respaldo descarta: si era un bloqueante, se queda como aviso con su razón (una
    persona decide); si era un aviso o info, se quita como haría Claude.
    """
    reasons = {d["id"]: d["reason"] for d in result["dismissed"]}
    out: list[Finding] = []
    for f in code_findings:
        if f.id not in reasons:
            out.append(f)
        elif f.severity == "blocker":
            f.severity = "warning"
            f.detail = f"El juez de respaldo cree que no es error ({reasons[f.id]}); confírmalo. {f.detail}"
            out.append(f)
    out += result["findings"]
    out.append(Finding(
        id="respaldo-aviso", type="tecnico", severity="info", t_start=0.0, t_end=0.0,
        title="Revisado con el juez de respaldo",
        detail=(f"Claude no tenía uso disponible, así que el criterio lo dio un modelo local ({model}), "
                "que es menos preciso. Los bloqueantes que descartó quedan como avisos para revisar."),
        suggestion="Si hay dudas, vuelve a revisar el video cuando Claude esté disponible.",
        source="code", check="juez_respaldo"))
    return out
