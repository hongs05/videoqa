from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from videoqa.brand import load_brand
from videoqa.checks.brand_color import check_brand_colors
from videoqa.checks.spelling import check_spelling, load_glossary
from videoqa.checks.technical import check_technical
from videoqa.checks.timing import check_timing
from videoqa.claude_runner import Runner
from videoqa.config import Settings
from videoqa.findings import Finding, save_findings
from videoqa.gate import decide, deliver
from videoqa.job import Job
from videoqa.judge import JudgeError, run_judge
from videoqa.report import build_report
from videoqa.sheet import SheetWriter, row_for
from videoqa.stages.color import add_colors
from videoqa.stages.frames import extract_frames
from videoqa.stages.ocr import ocr_frames
from videoqa.stages.probe import probe
from videoqa.stages.technical import analyze
from videoqa.stages.transcribe import transcribe

log = logging.getLogger("videoqa")


@dataclass
class Result:
    status: str                 # approved | rejected | error
    findings: list[Finding]
    dest: Path | None
    error: str | None = None


def _rel(settings: Settings, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(settings.drive_root))
    except ValueError:
        return str(path)


def process_video(video: Path, settings: Settings, rules: dict, runner: Runner, sheet: SheetWriter | None = None) -> Result:
    sheet = sheet or SheetWriter(None, settings.jobs_dir / "sheet_pending.json")
    job = Job(video, settings.jobs_dir)
    job.reset()
    started = datetime.now()
    log.info("[%s] inicio", job.name)
    sheet.write(row_for(video.name, "processing", [], "", _rel(settings, video), 0, started))

    try:
        p = job.run_stage("probe", "probe.json", probe)
        transcript = job.run_stage("transcribe", "transcript.json", lambda j: transcribe(j, p["has_audio"], settings.whisper_model))
        technical = job.run_stage("technical", "technical.json", lambda j: analyze(j, p["has_audio"], float(rules["frames"]["scene_threshold"])))
        frames = job.run_stage("frames", "frames.json", lambda j: extract_frames(j, technical["scene_cuts"], int(rules["frames"]["fps"])))
        ocr = job.run_stage("ocr", "ocr.json", lambda j: ocr_frames(j, frames["frames"], frames["period"]))
        ocr = job.run_stage("color", "ocr_color.json", lambda j: add_colors(j, ocr))

        brand = load_brand(settings.config_dir, runner)
        glossary_path = settings.config_dir / "glosario.txt"
        glossary = load_glossary(glossary_path)
        apps = ocr["appearances"]
        code_findings = (check_spelling(apps, glossary, rules) + check_brand_colors(apps, brand, rules)
                         + check_timing(apps, transcript["segments"], rules) + check_technical(p, technical, rules))
        save_findings(job.path("findings_code.json"), code_findings)
    except Exception as e:  # noqa: BLE001 — fallo de extracción: el video se queda en Entrada
        msg = f"{type(e).__name__}: {e}"
        log.exception("[%s] fallo de procesamiento", job.name)
        sheet.write(row_for(video.name, "error", [], "", _rel(settings, video), 0, datetime.now(), note=msg))
        return Result("error", [], None, msg)

    glossary_text = glossary_path.read_text(encoding="utf-8") if glossary_path.exists() else ""
    try:
        verdict = run_judge(job, brand, glossary_text, transcript, ocr, technical, code_findings, frames["frames"], rules, runner)
        dismissed = {d["id"] for d in verdict["dismissed"]}
        findings = [f for f in code_findings if f.id not in dismissed] + verdict["findings"]
        status = decide(findings)
    except JudgeError as e:
        log.error("[%s] %s", job.name, e)
        findings = code_findings + [Finding(
            id="judge-0", type="tecnico", severity=rules["severities"]["judge_unavailable"], t_start=0.0, t_end=float(p["duration"]),
            title="Revisión de criterio pendiente", detail=f"Claude no pudo revisar este video ({e}). Solo se aplicaron los checks automáticos.",
            suggestion="Reintentar más tarde o revisar manualmente.", source="code", check="judge_unavailable")]
        status = "error"

    build_report(job, p, findings, status)
    dest = deliver(job, settings, status)
    sheet.write(row_for(video.name, status, findings, _rel(settings, dest / "reporte.md"), _rel(settings, dest / video.name),
                        float(p["duration"]), datetime.now()))
    log.info("[%s] %s → %s", job.name, status, dest)
    return Result(status, findings, dest)
