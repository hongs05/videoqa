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
from videoqa.judge import run_judge
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
    # Solo se tira el caché si el job dir describe OTRO archivo (resubida del mismo nombre)
    # o si no hay estado previo. Reintentar el MISMO archivo reaprovecha probe/transcribe/
    # frames/ocr, que son las etapas caras; si no, cada reintento volvía a correr Whisper.
    if not job.matches_current_video():
        job.reset()
    else:
        log.info("[%s] reintento del mismo archivo: se conservan las etapas cacheadas", job.name)
    job.record_video()
    started = datetime.now()
    log.info("[%s] inicio", job.name)
    sheet.write(row_for(video.name, "processing", [], "", _rel(settings, video), 0, started))

    # Etapa 1: extracción (probe/transcribe/technical/frames/ocr/color) + checks de código.
    # Cualquier fallo aquí deja el video intacto en Entrada (deliver() nunca se llama).
    stage = "brand"
    try:
        brand = load_brand(settings.config_dir, runner)

        stage = "extraction"
        p = job.run_stage("probe", "probe.json", probe)
        transcript = job.run_stage("transcribe", "transcript.json", lambda j: transcribe(j, p["has_audio"], settings.whisper_model))
        technical = job.run_stage("technical", "technical.json", lambda j: analyze(j, p["has_audio"], float(rules["frames"]["scene_threshold"])))
        frames = job.run_stage("frames", "frames.json", lambda j: extract_frames(j, technical["scene_cuts"], int(rules["frames"]["fps"])))
        ocr = job.run_stage("ocr", "ocr.json", lambda j: ocr_frames(j, frames["frames"], frames["period"]))
        ocr = job.run_stage("color", "ocr_color.json", lambda j: add_colors(j, ocr))

        glossary_path = settings.config_dir / "glosario.txt"
        glossary_text = glossary_path.read_text(encoding="utf-8") if glossary_path.exists() else ""
        glossary = load_glossary(glossary_path)
        apps = ocr["appearances"]
        # La zona segura de la UI (banda inferior / franja derecha) solo existe en el
        # feed vertical; en 16:9 el check no aplica.
        vertical = int(p["height"]) > int(p["width"])
        code_findings = (check_spelling(apps, glossary, rules) + check_brand_colors(apps, brand, rules)
                         + check_timing(apps, transcript["segments"], rules, vertical=vertical)
                         + check_technical(p, technical, rules))
        save_findings(job.path("findings_code.json"), code_findings)
    except Exception as e:  # noqa: BLE001 — fallo de brand/extracción: el video se queda en Entrada
        prefix = "brand: " if stage == "brand" else ""
        msg = f"{prefix}{type(e).__name__}: {e}"
        log.exception("[%s] fallo de procesamiento", job.name)
        sheet.write(row_for(video.name, "error", [], "", _rel(settings, video), 0, datetime.now(), note=msg))
        return Result("error", [], None, msg)

    # Etapa 2: juicio de Claude + reporte + entrega + Sheet. Cualquier fallo de aquí en
    # adelante ya no debe dejar el video en limbo: se registra como error y, si el juez
    # falló, el video igual recibe reporte y termina en 02_Con_errores/.
    findings: list[Finding] = list(code_findings)
    dest: Path | None = None
    try:
        try:
            verdict = run_judge(job, brand, glossary_text, transcript, ocr, technical, code_findings,
                                 frames["frames"], rules, runner, duration=float(p["duration"]))
        except Exception as e:  # noqa: BLE001 — cualquier fallo del juez (ClaudeError u otro) degrada igual
            log.error("[%s] %s", job.name, e)
            findings = code_findings + [Finding(
                id="judge-0", type="tecnico", severity=rules["severities"]["judge_unavailable"], t_start=0.0,
                t_end=float(p["duration"]), title="Revisión de criterio pendiente",
                detail=f"Claude no pudo revisar este video ({e}). Solo se aplicaron los checks automáticos.",
                suggestion="Reintentar más tarde o revisar manualmente.", source="code", check="judge_unavailable")]
            status = "error"
            judge_error: str | None = str(e)
        else:
            dismissed = {d["id"] for d in verdict["dismissed"]}
            findings = [f for f in code_findings if f.id not in dismissed] + verdict["findings"]
            status = decide(findings)
            judge_error = None

        _, evidencia = build_report(job, p, findings, status)
        if rules.get("salida", {}).get("reporte_html"):
            from videoqa.report_html import build_html_report

            build_html_report(job, p, findings, status, evidencia)
        dest = deliver(job, settings, status)
        # Con el juez caído la columna "Reporte" muestra el motivo (la ruta del reporte
        # parcial queda en el propio reporte, dentro de la carpeta del video).
        note = f"Claude no disponible: {judge_error}" if judge_error else ""
        sheet.write(row_for(video.name, status, findings, _rel(settings, dest / "reporte.md"), _rel(settings, dest / video.name),
                            float(p["duration"]), datetime.now(), note=note))
        log.info("[%s] %s → %s", job.name, status, dest)
        return Result(status, findings, dest, judge_error)
    except Exception as e:  # noqa: BLE001 — fallo tras la extracción (reporte, entrega o Sheet)
        msg = f"{type(e).__name__}: {e}"
        log.exception("[%s] fallo tras extracción", job.name)
        sheet.write(row_for(video.name, "error", findings, "", _rel(settings, video), 0, datetime.now(), note=msg))
        return Result("error", findings, dest, msg)
