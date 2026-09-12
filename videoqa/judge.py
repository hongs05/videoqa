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

    def add(file: str | None) -> None:
        if file and file in by_file and file not in chosen and len(chosen) < max_frames:
            chosen.append(file)

    for f in frames:
        if f["kind"] == "scene":
            add(f["file"])
    for a in appearances:
        add(a.get("frame"))
    for fnd in code_findings:
        add(fnd.frame)
    seconds = [f["file"] for f in frames if f["kind"] == "second" and f["file"] not in chosen]
    remaining = max_frames - len(chosen)
    if remaining > 0 and seconds:
        step = max(1, len(seconds) // remaining)
        for file in seconds[::step]:
            add(file)
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


def parse_verdict(text: str) -> dict:
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
    if not isinstance(data.get("guion_real_md", ""), str):
        raise ValueError("'guion_real_md' debe ser texto")
    data.setdefault("guion_real_md", "")
    data["confirmed_code_findings"] = [str(x) for x in data.get("confirmed_code_findings", []) or []]
    dismissed = []
    for d in data.get("dismissed_code_findings", []) or []:
        if isinstance(d, dict) and d.get("id"):
            dismissed.append({"id": str(d["id"]), "reason": str(d.get("reason", ""))})
    data["dismissed_code_findings"] = dismissed
    return data


def run_judge(job: Job, brand: dict, glossary_text: str, transcript: dict, ocr: dict, technical: dict,
              code_findings: list[Finding], frames: list[dict], rules: dict, runner: Runner,
              skill_path: Path = SKILL_PATH) -> dict:
    manifest = prepare_inputs(job, brand, glossary_text, transcript, ocr, technical, code_findings, frames, rules)
    duration = max([f["t"] for f in frames], default=0.0)
    prompt = build_prompt(skill_path.read_text(encoding="utf-8"), manifest, duration)
    last: Exception | None = None
    verdict = None
    for attempt in (1, 2):
        try:
            verdict = parse_verdict(runner(prompt, job.dir))
            break
        except (ClaudeError, ValueError) as e:
            last = e
            log.warning("[%s] juez intento %d falló: %s", job.name, attempt, e)
    if verdict is None:
        raise JudgeError(f"juez falló tras 2 intentos: {last}")
    findings = []
    for i, f in enumerate(verdict["findings"]):
        findings.append(Finding(id=f"claude-{i}", type=f["type"], severity=f["severity"], t_start=float(f["t_start"]),
                                t_end=float(f["t_end"]), title=f["title"], detail=f["detail"],
                                suggestion=str(f.get("suggestion", "")), frame=f.get("frame") or None,
                                bbox=None, source="claude", check=f["type"]))
    job.path("findings_claude.json").write_text(json.dumps([f.to_dict() for f in findings], ensure_ascii=False, indent=2))
    job.path("guion_real.md").write_text(verdict["guion_real_md"], encoding="utf-8")
    return {"findings": findings, "dismissed": verdict["dismissed_code_findings"], "guion_real_md": verdict["guion_real_md"]}
