from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from videoqa import backends
from videoqa.brand import load_brand
from videoqa.checks.brand_color import check_brand_colors
from videoqa.checks.spelling import BASE_GLOSSARY_PATH, check_spelling, load_base_glossary
from videoqa.checks.technical import check_technical
from videoqa.checks.timing import check_timing
from videoqa.claude_runner import Runner, UsageLimitError
from videoqa.config import Settings
from videoqa.doctor_state import clear_wait_state, load_wait_until, write_doctor_state, write_wait_state
from videoqa.findings import Finding, save_findings
from videoqa.gate import decide, deliver
from videoqa.job import Job
from videoqa.judge import JudgeError, prepare_judge, run_judge
from videoqa.learning import load_corrections
from videoqa.profiles import (brand_dir, client_of, glossary_words, jobs_root, load_brief, load_profile,
                               merged_rules)
from videoqa.local_judge import DEFAULTS as FALLBACK_DEFAULTS
from videoqa.local_judge import apply_fallback, fallback_config, run_fallback_judge
from videoqa.report import build_report
from videoqa.sheet import SheetWriter, row_for
from videoqa.stages.color import add_colors
from videoqa.stages.frames import extract_frames
from videoqa.stages.ocr import dedupe, ocr_frames
from videoqa.stages.probe import probe
from videoqa.stages.technical import analyze
from videoqa.stages.transcribe import transcribe

log = logging.getLogger("videoqa")


# Si el mensaje de límite no dice la hora de reinicio, se reintenta pasado este tiempo.
WAIT_FALLBACK = timedelta(hours=1)


@dataclass
class Result:
    status: str                 # approved | rejected | error | pending | waiting
    findings: list[Finding]
    dest: Path | None
    error: str | None = None
    retry_at: datetime | None = None  # solo en "waiting": cuándo vuelve a haber uso de Claude
    judge_seconds: float | None = None  # solo en "prueba_respaldo": lo que tardó el modelo local


def _rel(settings: Settings, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(settings.drive_root))
    except ValueError:
        return str(path)


def _glossary_text_for_judge(team_text: str) -> str:
    """El texto de glosario que se le enseña al juez.

    El check de código acepta "reel", "canva" o "chévere" porque suma el glosario base
    empaquetado al del perfil (general + cliente); si el juez solo viera el del perfil,
    podría marcar como error una palabra que el código ya dio por buena y las dos mitades
    de la revisión se contradirían. Se le da el mismo vocabulario: el texto del perfil
    (tal cual, con sus propios comentarios) seguido del glosario base.
    """
    partes = [team_text.rstrip("\n")] if team_text.strip() else []
    partes.append("# --- Glosario base de VideoQA (viene empaquetado en el programa) ---")
    partes.append(BASE_GLOSSARY_PATH.read_text(encoding="utf-8").rstrip("\n"))
    return "\n".join(partes) + "\n"


PRUEBAS_RESPALDO = "04_Pruebas_respaldo"


def _prueba_respaldo(job: Job, video: Path, settings: Settings, rules: dict, p: dict, brand: dict,
                     glossary_text: str, transcript: dict, ocr: dict, technical: dict,
                     code_findings: list[Finding], frames: list[dict], corrections: list[dict],
                     context: dict | None = None, client: str | None = None) -> Result:
    """Revisa SOLO con el juez de respaldo, para compararlo con Claude antes de fiarse de él.

    No mueve el video, no toca el Sheet ni la lista final de hallazgos (la que usan las
    correcciones del equipo): deja el reporte en `04_Pruebas_respaldo/<video>/` y mide el tiempo.
    Funciona aunque el respaldo esté apagado en reglas.yaml: sirve para decidir si encenderlo.
    """
    cfg = {**FALLBACK_DEFAULTS, **(rules.get("juez_respaldo") or {})}
    t0 = time.monotonic()
    try:
        res = run_fallback_judge(job, brand, glossary_text, transcript, ocr, technical, code_findings, frames,
                                 rules, cfg, duration=float(p["duration"]), corrections=corrections,
                                 context=context)
    except Exception as e:  # noqa: BLE001 — la prueba falla, el video queda como estaba
        log.error("[%s] prueba del juez de respaldo: %s", job.name, e)
        return Result("error", code_findings, None, f"juez de respaldo: {e}")
    seconds = time.monotonic() - t0
    findings = apply_fallback(list(code_findings), res, cfg["modelo"])
    status = decide(findings)
    _, evidencia = build_report(job, p, findings, status)
    if rules.get("salida", {}).get("reporte_html"):
        from videoqa.report_html import build_html_report

        build_html_report(job, p, findings, status, evidencia)
    base = settings.drive_root / PRUEBAS_RESPALDO
    if client:
        base = base / client
    dest = base / job.name
    if dest.resolve().parent != base.resolve():
        raise ValueError(f"nombre de video inseguro: {video.name!r}")
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    for name in ("reporte.md", "reporte.html", "guion_real.md"):
        if job.path(name).exists():
            shutil.copy2(job.path(name), dest / name)
    if job.path("evidencia").exists():
        shutil.copytree(job.path("evidencia"), dest / "evidencia")
    log.info("[%s] prueba del respaldo (%s): %s en %.0f s → %s", job.name, cfg["modelo"], status, seconds, dest)
    return Result(status, findings, dest, None, judge_seconds=seconds)


def process_video(video: Path, settings: Settings, rules: dict, runner: Runner, sheet: SheetWriter | None = None,
                  modo: str = "completo", veredicto_text: str | None = None) -> Result:
    if modo == "prueba_respaldo":
        # Prueba del juez de respaldo: nada de Sheet (el tablero es del flujo real).
        sheet = SheetWriter(None, settings.jobs_dir / "sheet_pending.json")
    sheet = sheet or SheetWriter(None, settings.jobs_dir / "sheet_pending.json")
    # Perfil del cliente (por la carpeta del video): marca, glosario, criterios y reglas propias.
    client = client_of(video, settings)
    profile = load_profile(settings, client)
    rules = merged_rules(rules, profile.rule_overrides)
    row_name = f"{client} / {video.name}" if client else video.name
    job = Job(video, jobs_root(settings, client))
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
    sheet.write(row_for(row_name, "processing", [], "", _rel(settings, video), 0, started))

    # Etapa 1: extracción (probe/transcribe/technical/frames/ocr/color) + checks de código.
    # Cualquier fallo aquí deja el video intacto en Entrada (deliver() nunca se llama).
    stage = "brand"
    try:
        brand = load_brand(brand_dir(settings, profile), runner)

        stage = "extraction"
        p = job.run_stage("probe", "probe.json", probe)
        transcript = job.run_stage("transcribe", "transcript.json", lambda j: transcribe(j, p["has_audio"], settings.whisper_model))
        technical = job.run_stage("technical", "technical.json", lambda j: analyze(j, p["has_audio"], float(rules["frames"]["scene_threshold"])))
        frames = job.run_stage("frames", "frames.json", lambda j: extract_frames(j, technical["scene_cuts"], int(rules["frames"]["fps"])))
        ocr = job.run_stage("ocr", "ocr.json", lambda j: ocr_frames(j, frames["frames"], frames["period"]))
        if any("motion" not in a for a in ocr["appearances"]):
            # OCR cacheado por una versión anterior: se reagrupa desde las lecturas crudas
            # (sin volver a leer los frames) para tener `motion`/`scale`, que distinguen el
            # texto de la escena de los rótulos.
            ocr = {"raw": ocr["raw"], "appearances": dedupe(ocr["raw"], period=frames["period"])}
            job.path("ocr.json").write_text(json.dumps(ocr, ensure_ascii=False, indent=2))
            job.path("ocr_color.json").unlink(missing_ok=True)
        ocr = job.run_stage("color", "ocr_color.json", lambda j: add_colors(j, ocr))

        glossary_text = _glossary_text_for_judge(profile.glossary_text)  # general + cliente + base
        glossary = glossary_words(profile.glossary_text) | load_base_glossary()
        apps = ocr["appearances"]
        # La zona segura de la UI (banda inferior / franja derecha) solo existe en el
        # feed vertical; en 16:9 el check no aplica.
        vertical = int(p["height"]) > int(p["width"])
        try:
            checker = backends.get_speller()(settings.idiomas)
        except TypeError as e:  # backend de terceros sin soporte de idiomas
            log.debug("get_speller() no acepta idiomas, uso el constructor sin argumentos: %s", e)
            checker = backends.get_speller()()
        code_findings = (check_spelling(apps, glossary, rules, checker=checker, segments=transcript["segments"])
                         + check_brand_colors(apps, brand, rules)
                         + check_timing(apps, transcript["segments"], rules, vertical=vertical)
                         + check_technical(p, technical, rules))
        save_findings(job.path("findings_code.json"), code_findings)
    except Exception as e:  # noqa: BLE001 — fallo de brand/extracción: el video se queda en Entrada
        prefix = "brand: " if stage == "brand" else ""
        msg = f"{prefix}{type(e).__name__}: {e}"
        log.exception("[%s] fallo de procesamiento", job.name)
        sheet.write(row_for(row_name, "error", [], "", _rel(settings, video), 0, datetime.now(), note=msg))
        return Result("error", [], None, msg)

    try:
        corrections = load_corrections(settings.config_dir)
    except OSError as e:  # Drive sin sincronizar, permisos…: se revisa igual, sin memoria
        log.warning("[%s] no se pudieron leer las correcciones del equipo: %s", job.name, e)
        corrections = []
    # Las correcciones de OTRO cliente no aplican ("corillo es jerga nuestra" es de uno solo);
    # las generales (sin cliente) valen para todos.
    corrections = [c for c in corrections if not c.get("cliente") or c.get("cliente") == client]
    context = {"cliente": client, "criterios": profile.criteria, "brief": load_brief(video)}

    if modo == "preparar":
        try:
            prepare_judge(job, brand, glossary_text, transcript, ocr, technical, code_findings,
                          frames["frames"], rules, duration=float(p["duration"]), corrections=corrections,
                          context=context)
        except JudgeError as e:
            log.error("[%s] %s", job.name, e)
            return Result("error", code_findings, None, str(e))
        log.info("[%s] entradas del juez listas en %s (esperando veredicto)", job.name, job.dir)
        return Result("pending", code_findings, None, None)

    if modo == "prueba_respaldo":
        return _prueba_respaldo(job, video, settings, rules, p, brand, glossary_text, transcript, ocr, technical,
                                code_findings, frames["frames"], corrections, context, client)

    if veredicto_text is not None:
        texto = veredicto_text
        runner = lambda prompt, cwd: texto  # noqa: E731 — el veredicto ya viene escrito

    # Etapa 2: juicio de Claude + reporte + entrega + Sheet. Cualquier fallo de aquí en
    # adelante ya no debe dejar el video en limbo: se registra como error y, si el juez
    # falló, el video igual recibe reporte y termina en 02_Con_errores/.
    findings: list[Finding] = list(code_findings)
    dest: Path | None = None
    respaldo_note = ""
    fallback = fallback_config(rules)
    try:
        try:
            espera = load_wait_until() or 0.0
            if fallback and espera > time.time():
                # Claude sigue sin uso (lo dijo un video anterior): ni se intenta, directo al
                # juez de respaldo, para no gastar una llamada que va a fallar.
                raise UsageLimitError("Claude sin uso disponible (espera registrada)",
                                      datetime.fromtimestamp(espera).astimezone())
            verdict = run_judge(job, brand, glossary_text, transcript, ocr, technical, code_findings,
                                 frames["frames"], rules, runner, duration=float(p["duration"]),
                                 corrections=corrections, context=context)
        except UsageLimitError as e:
            retry_at = e.resets_at or (datetime.now().astimezone() + WAIT_FALLBACK)
            fallback_findings = None
            if fallback:
                try:
                    res = run_fallback_judge(job, brand, glossary_text, transcript, ocr, technical, code_findings,
                                             frames["frames"], rules, fallback, duration=float(p["duration"]),
                                             corrections=corrections, context=context)
                    fallback_findings = apply_fallback(code_findings, res, fallback["modelo"])
                except Exception as fe:  # noqa: BLE001 — sin respaldo, el video espera a Claude
                    log.warning("[%s] el juez de respaldo tampoco pudo revisar: %s", job.name, fe)
            if fallback_findings is None:
                # Sin uso de Claude (ni respaldo) no hay veredicto que dar, pero el video no
                # tiene la culpa: se queda en Entrada (nada de reporte con los hallazgos sin
                # filtrar) y se reintenta cuando se libere el uso. Extracción y OCR ya quedan
                # cacheados.
                write_wait_state(retry_at, video.name)
                note = f"En espera: Claude sin uso disponible hasta las {retry_at:%H:%M}"
                log.warning("[%s] %s; el video se queda en 01_Entrada", job.name, note)
                sheet.write(row_for(row_name, "waiting", [], "", _rel(settings, video), float(p["duration"]),
                                    datetime.now(), note=note))
                return Result("waiting", code_findings, None, str(e), retry_at=retry_at)
            write_wait_state(retry_at, "", respaldo=True)
            findings = fallback_findings
            status = decide(findings)
            judge_error = None
            respaldo_note = (f"Juez de respaldo ({fallback['modelo']}): Claude sin uso hasta las "
                             f"{retry_at:%H:%M}")
            log.info("[%s] revisado con el juez de respaldo (%s)", job.name, fallback["modelo"])
        except Exception as e:  # noqa: BLE001 — cualquier fallo del juez (ClaudeError u otro) degrada igual
            log.error("[%s] %s", job.name, e)
            texto_error = str(e).lower()
            if "authenticate" in texto_error or "oauth" in texto_error:
                # Deja constancia para que el hook SessionStart de la próxima sesión avise
                # sin esperar a que alguien lance `videoqa doctor` a mano.
                write_doctor_state(False, "la sesión caducó o no está guardada")
            # Con juez_requerido=false (instalaciones de pre-chequeo, sin Claude)
            # la ausencia de criterio es lo esperado, no un fallo: el veredicto
            # sale de los checks automáticos y el video puede aprobarse.
            opcional = rules.get("juez_requerido", True) is False
            findings = code_findings + [Finding(
                id="judge-0", type="tecnico",
                severity="info" if opcional else rules["severities"]["judge_unavailable"],
                t_start=0.0, t_end=float(p["duration"]),
                title=("Esta revisión no incluye criterio" if opcional else "Revisión de criterio pendiente"),
                detail=(("Se aplicaron solo los checks automáticos. El criterio (bloopers, "
                         "inconsistencias, tono) lo aporta la revisión oficial.") if opcional
                        else f"Claude no pudo revisar este video ({e}). Solo se aplicaron los checks automáticos."),
                suggestion=("" if opcional else "Reintentar más tarde o revisar manualmente."),
                source="code", check="judge_unavailable")]
            status = decide(findings) if opcional else "error"
            judge_error: str | None = None if opcional else str(e)
        else:
            clear_wait_state()  # Claude respondió: si había una espera por límite, ya pasó
            dismissed = {d["id"] for d in verdict["dismissed"]}
            findings = [f for f in code_findings if f.id not in dismissed] + verdict["findings"]
            status = decide(findings)
            judge_error = None

        # Lista final (lo que ve la persona en el reporte): `videoqa hallazgos` la usa para
        # que las correcciones del equipo apunten al mismo hallazgo.
        save_findings(job.path("findings_final.json"), findings)
        _, evidencia = build_report(job, p, findings, status)
        if rules.get("salida", {}).get("reporte_html"):
            from videoqa.report_html import build_html_report

            build_html_report(job, p, findings, status, evidencia)
        dest = deliver(job, settings, status, client=client)
        # Con el juez caído la columna "Reporte" muestra el motivo (la ruta del reporte
        # parcial queda en el propio reporte, dentro de la carpeta del video).
        note = f"Claude no disponible: {judge_error}" if judge_error else respaldo_note
        sheet.write(row_for(row_name, status, findings, _rel(settings, dest / "reporte.md"), _rel(settings, dest / video.name),
                            float(p["duration"]), datetime.now(), note=note))
        log.info("[%s] %s → %s", job.name, status, dest)
        return Result(status, findings, dest, judge_error)
    except Exception as e:  # noqa: BLE001 — fallo tras la extracción (reporte, entrega o Sheet)
        msg = f"{type(e).__name__}: {e}"
        log.exception("[%s] fallo tras extracción", job.name)
        sheet.write(row_for(row_name, "error", findings, "", _rel(settings, video), 0, datetime.now(), note=msg))
        return Result("error", findings, dest, msg)
