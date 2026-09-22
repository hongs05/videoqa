from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from PIL import Image

from videoqa.claude_runner import ClaudeError, Runner, extract_json
from videoqa.config import SKILL_PATH
from videoqa.findings import SEVERITIES, TYPES, Finding
from videoqa.job import Job

log = logging.getLogger("videoqa")


class JudgeError(Exception):
    """El juez (claude -p) no produjo un veredicto válido tras los reintentos."""


def select_frames(frames: list[dict], appearances: list[dict], code_findings: list[Finding], max_frames: int) -> list[str]:
    by_file = {f["file"]: f["t"] for f in frames}
    chosen: list[str] = []

    def add(file: str | None) -> bool:
        if file and file in by_file and file not in chosen and len(chosen) < max_frames:
            chosen.append(file)
            return True
        return False

    # Cuota: hasta max_frames // 3 slots reservados para findings de código y apariciones OCR
    # (findings primero), el resto de la budget para frames de escena. Los slots que sobran de
    # un lado pasan al otro, y lo que quede se llena con frames "second" espaciados.
    reserved = max_frames // 3
    scene_cap = max_frames - reserved

    priority_files = [fnd.frame for fnd in code_findings] + [a.get("frame") for a in appearances]
    scene_files = [f["file"] for f in frames if f["kind"] == "scene"]

    added_priority = 0
    for file in priority_files:
        if added_priority >= reserved or len(chosen) >= max_frames:
            break
        if add(file):
            added_priority += 1

    added_scene = 0
    for file in scene_files:
        if added_scene >= scene_cap or len(chosen) >= max_frames:
            break
        if add(file):
            added_scene += 1

    # Slots sobrantes: primero más frames prioritarios que no cupieron en la reserva, luego más
    # frames de escena que no cupieron en su cupo.
    if len(chosen) < max_frames:
        for file in priority_files:
            if len(chosen) >= max_frames:
                break
            add(file)
    if len(chosen) < max_frames:
        for file in scene_files:
            if len(chosen) >= max_frames:
                break
            add(file)

    seconds = [f["file"] for f in frames if f["kind"] == "second" and f["file"] not in chosen]
    remaining = max_frames - len(chosen)
    if remaining > 0 and seconds:
        if remaining > 1:
            idxs = [round(i * (len(seconds) - 1) / (remaining - 1)) for i in range(remaining)]
        else:
            idxs = [len(seconds) // 2]
        seen_idx: set[int] = set()
        for idx in idxs:
            if idx in seen_idx:
                continue
            seen_idx.add(idx)
            add(seconds[idx])
    return sorted(chosen, key=lambda f: by_file[f])


def prepare_inputs(job: Job, brand: dict, glossary_text: str, transcript: dict, ocr: dict, technical: dict,
                   code_findings: list[Finding], frames: list[dict], rules: dict) -> dict:
    inp = job.path("judge_input")
    shutil.rmtree(inp, ignore_errors=True)
    inp.mkdir()
    files = {
        "brand.json": brand,
        "transcript.json": transcript,
        "ocr.json": {"appearances": ocr.get("appearances", [])},
        "technical.json": technical,
        "findings_code.json": [f.to_dict() for f in code_findings],
    }
    for name, data in files.items():
        (inp / name).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    (inp / "glosario.txt").write_text(glossary_text)

    out = job.path("claude_frames")
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    height = int(rules["claude"]["frame_height"])
    by_file = {f["file"]: f["t"] for f in frames}
    selected = select_frames(frames, ocr.get("appearances", []), code_findings, int(rules["claude"]["max_frames"]))
    manifest_frames = []
    for i, rel in enumerate(selected):
        t = by_file[rel]
        img = Image.open(job.path(rel)).convert("RGB")
        if img.height > height:
            img = img.resize((round(img.width * height / img.height), height))
        name = f"claude_frames/{i:02d}_{t:06.1f}s.jpg"
        img.save(job.path(name), quality=85)
        manifest_frames.append({"file": name, "t": t})
    return {"frames": manifest_frames, "inputs": [f"judge_input/{n}" for n in [*files, "glosario.txt"]]}


def build_prompt(skill_text: str, manifest: dict, duration: float) -> str:
    frame_lines = "\n".join(f"- {f['file']}  (t = {f['t']:.1f} s)" for f in manifest["frames"])
    input_lines = "\n".join(f"- {p}" for p in manifest["inputs"])
    return (f"{skill_text}\n\n---\n\n# Trabajo actual\n\nDuración del video: {duration:.1f} s.\n\n"
            f"Archivos de entrada (léelos todos con Read):\n{input_lines}\n\n"
            f"Frames clave (léelos todos con Read):\n{frame_lines}\n\n"
            "Responde solo con el JSON del veredicto.")


def parse_verdict(text: str, require_guion: bool = True) -> dict:
    data = extract_json(text)
    findings = data.get("findings")
    if not isinstance(findings, list):
        raise ValueError("'findings' debe ser una lista")
    for f in findings:
        if not isinstance(f, dict):
            raise ValueError("cada finding debe ser objeto")
        if f.get("type") not in TYPES:
            raise ValueError(f"type inválido: {f.get('type')}")
        if f.get("severity") not in SEVERITIES:
            raise ValueError(f"severity inválida: {f.get('severity')}")
        for k in ("t_start", "t_end"):
            if not isinstance(f.get(k), (int, float)):
                raise ValueError(f"{k} debe ser numérico")
        for k in ("title", "detail"):
            if not isinstance(f.get(k), str) or not f[k]:
                raise ValueError(f"{k} requerido")
        # Sanitize frame: if present and not None and not a string, set to None with warning
        if "frame" in f and f["frame"] is not None and not isinstance(f["frame"], str):
            log.warning("verdict finding: frame no es string, descartado: %r", f["frame"])
            f["frame"] = None
    # El guion real es un entregable del pipeline, no un campo opcional: si viene vacío el
    # veredicto no sirve y debe reintentarse (o degradarse a "juez no disponible"). La
    # excepción es un video SIN diálogo: ahí no hay guion que transcribir y exigirlo
    # condenaba el veredicto a fallar los 2 intentos.
    if not require_guion and data.get("guion_real_md") is None:
        data["guion_real_md"] = ""
    guion = data.get("guion_real_md")
    if not isinstance(guion, str):
        raise ValueError("'guion_real_md' debe ser texto")
    if require_guion and not guion.strip():
        raise ValueError("guion_real_md vacío")

    confirmed = data.get("confirmed_code_findings", []) or []
    if not isinstance(confirmed, list):
        raise ValueError("'confirmed_code_findings' debe ser una lista")
    data["confirmed_code_findings"] = [str(x) for x in confirmed]

    dismissed_raw = data.get("dismissed_code_findings", []) or []
    if not isinstance(dismissed_raw, list):
        raise ValueError("'dismissed_code_findings' debe ser una lista")
    dismissed = []
    for d in dismissed_raw:
        if not isinstance(d, dict):
            log.warning("dismissed_code_findings: entrada descartada (no es objeto): %r", d)
            continue
        d_id, d_reason = d.get("id"), d.get("reason")
        if not isinstance(d_id, str) or not d_id:
            log.warning("dismissed_code_findings: entrada descartada (id inválido): %r", d)
            continue
        if not isinstance(d_reason, str) or not d_reason:
            log.warning("dismissed_code_findings: entrada descartada (sin reason): %r", d)
            continue
        dismissed.append({"id": d_id, "reason": d_reason})
    data["dismissed_code_findings"] = dismissed
    return data


def prepare_judge(job: Job, brand: dict, glossary_text: str, transcript: dict, ocr: dict, technical: dict,
                  code_findings: list[Finding], frames: list[dict], rules: dict,
                  skill_path: Path = SKILL_PATH, duration: float | None = None) -> str:
    """Deja en el job dir todo lo que el juez necesita y devuelve el prompt.

    Lo usa `run_judge` (juez por `claude -p`) y también `videoqa run --hasta-juez`,
    donde el juez es la propia sesión de Claude que lee `judge_prompt.md`.
    """
    try:
        manifest = prepare_inputs(job, brand, glossary_text, transcript, ocr, technical, code_findings, frames, rules)
        skill_text = skill_path.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001 — cualquier fallo aquí es fatal para el juez
        raise JudgeError(f"no se pudieron preparar las entradas del juez: {e}") from e
    if duration is None:
        duration = max([f["t"] for f in frames], default=0.0)
    prompt = build_prompt(skill_text, manifest, duration)
    job.path("judge_prompt.md").write_text(prompt, encoding="utf-8")
    job.path("judge_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return prompt


def run_judge(job: Job, brand: dict, glossary_text: str, transcript: dict, ocr: dict, technical: dict,
              code_findings: list[Finding], frames: list[dict], rules: dict, runner: Runner,
              skill_path: Path = SKILL_PATH, duration: float | None = None) -> dict:
    base_prompt = prepare_judge(job, brand, glossary_text, transcript, ocr, technical, code_findings, frames, rules,
                                skill_path=skill_path, duration=duration)
    manifest = json.loads(job.path("judge_manifest.json").read_text())
    # Sin segmentos de audio no hay diálogo que transcribir: no se exige guion real.
    require_guion = bool(transcript.get("segments"))
    # Artefactos de la corrida anterior: si el juez falla ahora, un `guion_real.md` o
    # `findings_claude.json` viejos seguirían en el job dir y se entregarían como si
    # fueran de esta revisión.
    for stale in ("guion_real.md", "findings_claude.json"):
        job.path(stale).unlink(missing_ok=True)
    last: Exception | None = None
    verdict = None
    for attempt in (1, 2):
        prompt = base_prompt
        if attempt == 2 and last is not None:
            prompt += (f"\n\nTu respuesta anterior no fue válida ({last}). "
                       "Responde ÚNICAMENTE con el JSON del veredicto, sin texto adicional.")
        try:
            verdict = parse_verdict(runner(prompt, job.dir), require_guion=require_guion)
            break
        except (ClaudeError, ValueError) as e:
            last = e
            log.warning("[%s] juez intento %d falló: %s", job.name, attempt, e)
    if verdict is None:
        raise JudgeError(f"juez falló tras 2 intentos: {last}")

    valid_frames = {mf["file"] for mf in manifest["frames"]}
    findings = []
    for i, f in enumerate(verdict["findings"]):
        frame = f.get("frame") or None
        if frame is not None:
            if not isinstance(frame, str):
                log.warning("[%s] juez: frame no es string, descartado: %r", job.name, frame)
                frame = None
            elif frame not in valid_frames and not (frame.startswith("frames/") and job.path(frame).exists()):
                log.warning("[%s] juez: frame inválido descartado: %s", job.name, frame)
                frame = None
        findings.append(Finding(id=f"claude-{i}", type=f["type"], severity=f["severity"], t_start=float(f["t_start"]),
                                t_end=float(f["t_end"]), title=f["title"], detail=f["detail"],
                                suggestion=str(f.get("suggestion", "")), frame=frame,
                                bbox=None, source="claude", check=f["type"]))
    job.path("findings_claude.json").write_text(json.dumps([f.to_dict() for f in findings], ensure_ascii=False, indent=2))
    job.path("guion_real.md").write_text(verdict["guion_real_md"], encoding="utf-8")

    known_ids = {fnd.id for fnd in code_findings}
    dismissed = []
    for d in verdict["dismissed_code_findings"]:
        if d["id"] not in known_ids:
            log.warning("[%s] juez: dismissal de id desconocido descartado: %s", job.name, d["id"])
            continue
        dismissed.append(d)
    return {"findings": findings, "dismissed": dismissed, "guion_real_md": verdict["guion_real_md"]}
