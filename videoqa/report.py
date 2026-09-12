from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from videoqa.findings import Finding, count_by_severity, sort_findings
from videoqa.job import Job

CHECK_LABELS = {
    "spelling_unknown_word": "Ortografía", "spelling_punctuation": "Puntuación", "brand_color": "Color de marca",
    "text_visible_short": "Texto legible ≥ 1 s", "subtitle_desync": "Sincronía subtítulos", "text_occluded": "Zona segura UI",
    "black_frame": "Pantalla negra", "frozen_frame": "Frames congelados", "silence": "Silencios", "audio_clipping": "Clipping de audio",
    "aspect_ratio": "Relación de aspecto 9:16", "no_audio": "Pista de audio",
    "ortografia": "Ortografía (criterio)", "marca": "Reglas de marca (criterio)", "inconsistencia": "Guion ↔ pantalla",
    "blooper": "Bloopers", "tecnico": "Elementos extraños en frame",
}
STATUS = {"approved": ("🟢", "APROBADO"), "rejected": ("🔴", "NO APROBADO"), "error": ("❌", "ERROR")}


def fmt_t(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return f"{sec // 60}:{sec % 60:02d}"


def _slug_t(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return f"{sec // 60}m{sec % 60:02d}s"


def write_evidence(job: Job, findings: list[Finding]) -> dict[str, str]:
    out = job.path("evidencia")
    out.mkdir(exist_ok=True)
    evidence: dict[str, str] = {}
    n = 0
    for f in sort_findings(findings):
        if not f.frame or not job.path(f.frame).exists():
            continue
        n += 1
        img = Image.open(job.path(f.frame)).convert("RGB")
        if f.bbox:
            W, H = img.size
            x, y, w, h = f.bbox
            ImageDraw.Draw(img).rectangle([x * W, y * H, (x + w) * W, (y + h) * H], outline=(255, 0, 0), width=max(2, W // 200))
        rel = f"evidencia/{n:02d}_{_slug_t(f.t_start)}.jpg"
        img.save(job.path(rel), quality=85)
        evidence[f.id] = rel
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
            lines.append(f"{n}. **{span} {f.title}**")
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
    passed = [label for key, label in CHECK_LABELS.items() if key not in failed]
    lines.append("## ✅ Checks pasados")
    lines.append(" · ".join(passed) if passed else "—")
    lines.append("")
    return "\n".join(lines)


def build_report(job: Job, probe: dict, findings: list[Finding], status: str, when: datetime | None = None) -> Path:
    evidence = write_evidence(job, findings)
    md = render_report(job.video.name, probe, findings, status, evidence, when or datetime.now())
    out = job.path("reporte.md")
    out.write_text(md, encoding="utf-8")
    return out
