"""Reporte en HTML con las fotos de evidencia incrustadas.

Pensado para quien no lee markdown a gusto (Windows, o mandar el archivo por
chat): un solo archivo, sin dependencias externas, que se abre con doble clic.
"""
from __future__ import annotations

import base64
from datetime import datetime
from html import escape
from pathlib import Path

from videoqa.findings import Finding, count_by_severity, sort_findings
from videoqa.job import Job
from videoqa.report import CHECK_LABELS, JUDGE_CHECKS, STATUS, TYPE_LABELS, fmt_t

_CSS = """
:root { color-scheme: light dark; }
body { font: 16px/1.5 -apple-system, "Segoe UI", system-ui, sans-serif;
       margin: 0 auto; max-width: 52rem; padding: 2rem 1.25rem; }
h1 { font-size: 1.6rem; margin: 0 0 .25rem; }
.meta { color: #777; font-size: .9rem; margin-bottom: 2rem; }
h2 { font-size: 1.15rem; margin: 2rem 0 .75rem; }
.hallazgo { border-left: 4px solid #ccc; padding: .25rem 0 .25rem 1rem; margin: 0 0 1.5rem; }
.hallazgo.blocker { border-color: #d33; }
.hallazgo.warning { border-color: #e9a13b; }
.hallazgo.info { border-color: #4a90d9; }
.hallazgo h3 { font-size: 1rem; margin: 0 0 .35rem; }
.t { font-variant-numeric: tabular-nums; color: #777; font-weight: normal; }
.sug { color: #2a7; }
.hallazgo img { max-width: 100%; border-radius: 6px; margin-top: .6rem; display: block; }
.pasados { color: #777; font-size: .9rem; }
"""


def _img_data_uri(ruta: Path) -> str | None:
    try:
        datos = ruta.read_bytes()
    except OSError:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(datos).decode("ascii")


def _bloque(n: int, f: Finding, evidence: dict[str, str], job: Job | None) -> str:
    span = fmt_t(f.t_start) if f.t_end - f.t_start <= 1.0 else f"{fmt_t(f.t_start)}–{fmt_t(f.t_end)}"
    tipo = TYPE_LABELS.get(f.type, f.type)
    partes = [f'<div class="hallazgo {escape(f.severity)}">',
              f'<h3>{n}. <span class="t">[{escape(span)}]</span> {escape(tipo)} — {escape(f.title)}</h3>',
              f"<p>{escape(f.detail)}</p>"]
    if f.suggestion:
        partes.append(f'<p class="sug">Sugerencia: {escape(f.suggestion)}</p>')
    rel = evidence.get(f.id)
    if rel and job is not None:
        uri = _img_data_uri(job.path(rel))
        if uri:
            partes.append(f'<img alt="Evidencia en {escape(span)}" src="{uri}">')
    partes.append("</div>")
    return "\n".join(partes)


def render_html(video_name: str, probe: dict, findings: list[Finding], status: str,
                evidence: dict[str, str], when: datetime, job: Job | None = None) -> str:
    icono, etiqueta = STATUS[status]
    cuentas = count_by_severity(findings)
    ordenados = sort_findings(findings)
    partes = ["<!doctype html>", '<html lang="es">', "<head>", '<meta charset="utf-8">',
              '<meta name="viewport" content="width=device-width, initial-scale=1">',
              f"<title>{escape(video_name)} — {escape(etiqueta)}</title>",
              f"<style>{_CSS}</style>", "</head>", "<body>",
              f"<h1>{icono} {escape(video_name)} — {escape(etiqueta)}</h1>",
              f'<p class="meta">Revisado: {when:%Y-%m-%d %H:%M} · Duración {fmt_t(probe["duration"])} · '
              f'{probe["width"]}×{probe["height"]} · {cuentas["blocker"]} bloqueantes · '
              f'{cuentas["warning"]} advertencias</p>']
    n = 0
    for sev, titulo in (("blocker", "🔴 Bloqueantes"), ("warning", "⚠️ Advertencias"),
                        ("info", "ℹ️ Información")):
        items = [f for f in ordenados if f.severity == sev]
        if not items:
            continue
        partes.append(f"<h2>{titulo}</h2>")
        for f in items:
            n += 1
            partes.append(_bloque(n, f, evidence, job))

    fallados = {f.check for f in findings}
    juez_caido = status == "error" or "judge_unavailable" in fallados
    pasados = [etq for clave, etq in CHECK_LABELS.items()
               if clave not in fallados and not (juez_caido and clave in JUDGE_CHECKS)]
    partes.append("<h2>✅ Checks pasados</h2>")
    partes.append(f'<p class="pasados">{escape(" · ".join(pasados)) if pasados else "—"}</p>')
    if juez_caido:
        pendientes = [CHECK_LABELS[c] for c in JUDGE_CHECKS if c in CHECK_LABELS]
        partes.append("<h2>⏳ Pendientes de revisión</h2>")
        partes.append(f'<p class="pasados">{escape(" · ".join(pendientes))}</p>')
    partes += ["</body>", "</html>"]
    return "\n".join(partes)


def build_html_report(job: Job, probe: dict, findings: list[Finding], status: str,
                      evidence: dict[str, str], when: datetime | None = None) -> Path:
    html = render_html(job.video.name, probe, findings, status, evidence, when or datetime.now(), job=job)
    out = job.path("reporte.html")
    out.write_text(html, encoding="utf-8")
    return out
