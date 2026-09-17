from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from videoqa.findings import Finding, count_by_severity, sort_findings
from videoqa.job import Job

log = logging.getLogger("videoqa")

CHECK_LABELS = {
    "spelling_unknown_word": "Ortografía", "spelling_punctuation": "Puntuación", "brand_color": "Color de marca",
    "text_visible_short": "Texto legible ≥ 1 s", "subtitle_desync": "Sincronía subtítulos", "text_occluded": "Zona segura UI",
    "black_frame": "Pantalla negra", "frozen_frame": "Frames congelados", "silence": "Silencios", "audio_clipping": "Clipping de audio",
    "aspect_ratio": "Relación de aspecto 9:16", "no_audio": "Pista de audio",
    "ortografia": "Ortografía (criterio)", "marca": "Reglas de marca (criterio)", "inconsistencia": "Guion ↔ pantalla",
    "blooper": "Bloopers", "tecnico": "Elementos extraños en frame",
}
STATUS = {"approved": ("🟢", "APROBADO"), "rejected": ("🔴", "NO APROBADO"), "error": ("❌", "ERROR")}

# Etiqueta en español de cada `Finding.type`, para la línea `[m:ss] Tipo — título`.
TYPE_LABELS = {"ortografia": "Ortografía", "marca": "Marca", "inconsistencia": "Inconsistencia",
               "blooper": "Blooper", "tecnico": "Técnico"}

# Checks que solo puede emitir el juez: si Claude no estuvo disponible, NO se pueden
# declarar "pasados" (sería un visto bueno falso); van a "Pendientes de revisión".
JUDGE_CHECKS = ("ortografia", "marca", "inconsistencia", "blooper", "tecnico")


def fmt_t(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return f"{sec // 60}:{sec % 60:02d}"


def _slug_t(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return f"{sec // 60}m{sec % 60:02d}s"


def write_evidence(job: Job, findings: list[Finding]) -> dict[str, str]:
    out = job.path("evidencia")
    # Se recrea desde cero: en un reintento el job dir se conserva, y las evidencias
    # de la corrida anterior (numeradas 01..NN) sobrevivían y acababan copiadas al
    # destino junto a las nuevas, mostrando findings ya corregidos.
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, str] = {}
    n = 0
    for f in sort_findings(findings):
        if not f.frame or not job.path(f.frame).exists():
            continue
        try:
            img = Image.open(job.path(f.frame)).convert("RGB")
            if f.bbox:
                W, H = img.size
                x, y, w, h = f.bbox
                x0 = min(max(x, 0.0), 1.0)
                y0 = min(max(y, 0.0), 1.0)
                x1 = min(max(x + w, 0.0), 1.0)
                y1 = min(max(y + h, 0.0), 1.0)
                if x1 < x0:
                    x0, x1 = x1, x0
                if y1 < y0:
                    y0, y1 = y1, y0
                if x1 > x0 and y1 > y0:
                    ImageDraw.Draw(img).rectangle([x0 * W, y0 * H, x1 * W, y1 * H], outline=(255, 0, 0), width=max(2, W // 200))
            n += 1
            rel = f"evidencia/{n:02d}_{_slug_t(f.t_start)}.jpg"
            img.save(job.path(rel), quality=85)
            evidence[f.id] = rel
        except Exception as e:  # noqa: BLE001 — un bbox/frame malformado no debe tumbar el reporte completo
            log.warning("No se pudo generar evidencia para %s (%s: %s)", f.id, type(e).__name__, e)
    return evidence


def _plural(n: int, s: str, p: str) -> str:
    return f"{n} {s if n == 1 else p}"


def render_report(video_name: str, probe: dict, findings: list[Finding], status: str, evidence: dict[str, str], when: datetime) -> str:
    icon, label = STATUS[status]
    counts = count_by_severity(findings)
    lines = [f"# {icon} {video_name} — {label}",
             f"Revisado: {when:%Y-%m-%d %H:%M} · Duración {fmt_t(probe['duration'])} · {probe['width']}×{probe['height']} · "
             f"{_plural(counts['blocker'], 'bloqueante', 'bloqueantes')} · {_plural(counts['warning'], 'advertencia', 'advertencias')}", ""]
    n = 0

    def section(title: str, sev: str) -> None:
        nonlocal n
        items = [f for f in sort_findings(findings) if f.severity == sev]
        if not items:
            return
        lines.append(title)
        for f in items:
            n += 1
            span = f"[{fmt_t(f.t_start)}]" if f.t_end - f.t_start <= 1.0 else f"[{fmt_t(f.t_start)}–{fmt_t(f.t_end)}]"
            kind = TYPE_LABELS.get(f.type, f.type)
            lines.append(f"{n}. **{span} {kind} — {f.title}**")
            lines.append(f"   {f.detail}")
            if f.suggestion:
                lines.append(f"   Sugerencia: {f.suggestion}")
            if f.id in evidence:
                lines.append(f"   Evidencia: {evidence[f.id]}")
        lines.append("")

    section("## 🔴 Bloqueantes", "blocker")
    section("## ⚠️ Advertencias", "warning")
    section("## ℹ️ Información", "info")
    failed = {f.check for f in findings}
    # Si el juez no corrió (o el pipeline terminó en error), sus checks no se revisaron:
    # listarlos como "pasados" sería un visto bueno falso.
    judge_down = any(f.check == "judge_unavailable" for f in findings) or status == "error"
    pending = list(JUDGE_CHECKS) if judge_down else []
    passed = [label for key, label in CHECK_LABELS.items()
              if key not in failed and key not in pending]
    lines.append("## ✅ Checks pasados")
    lines.append(" · ".join(passed) if passed else "—")
    lines.append("")
    if pending:
        lines.append("## ⏳ Pendientes de revisión (Claude no disponible)")
        lines.append(" · ".join(CHECK_LABELS.get(key, key) for key in pending))
        lines.append("")
    return "\n".join(lines)


def build_report(job: Job, probe: dict, findings: list[Finding], status: str, when: datetime | None = None) -> Path:
    evidence = write_evidence(job, findings)
    md = render_report(job.video.name, probe, findings, status, evidence, when or datetime.now())
    out = job.path("reporte.md")
    out.write_text(md, encoding="utf-8")
    return out
