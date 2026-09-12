from __future__ import annotations

from videoqa.findings import Finding


def _overlaps(a: dict, b: dict) -> bool:
    return a["start"] < b["end"] and b["start"] < a["end"]


def _inside(iv: dict, duration: float, margin: float) -> bool:
    return iv["start"] >= margin and iv["end"] <= duration - margin


def check_technical(probe: dict, technical: dict, rules: dict) -> list[Finding]:
    th, sev = rules["thresholds"], rules["severities"]
    dur, margin = float(probe["duration"]), float(th["edge_margin_s"])
    out: list[Finding] = []

    blacks = [b for b in technical.get("black", []) if b["end"] - b["start"] >= float(th["black_min_s"]) and _inside(b, dur, margin)]
    for i, b in enumerate(blacks):
        out.append(Finding(id=f"black-{i}", type="tecnico", severity=sev["black_frame"], t_start=b["start"], t_end=b["end"],
                           title=f"Pantalla negra de {b['end'] - b['start']:.1f} s", detail="El video queda en negro en medio del contenido.",
                           suggestion="Revisar el corte o la transición en ese punto.", source="code", check="black_frame"))

    for i, f in enumerate(technical.get("freeze", [])):
        if f["end"] - f["start"] < float(th["freeze_min_s"]) or not _inside(f, dur, margin):
            continue
        if any(_overlaps(f, b) for b in blacks):
            continue
        out.append(Finding(id=f"freeze-{i}", type="tecnico", severity=sev["frozen_frame"], t_start=f["start"], t_end=f["end"],
                           title=f"Imagen congelada {f['end'] - f['start']:.1f} s", detail="No hay cambio de imagen durante ese intervalo.",
                           suggestion="Verificar si es un frame duplicado o un clip mal exportado.", source="code", check="frozen_frame"))

    for i, s in enumerate(technical.get("silence", [])):
        if s["end"] - s["start"] >= float(th["silence_min_s"]) and _inside(s, dur, margin):
            out.append(Finding(id=f"silence-{i}", type="tecnico", severity=sev["silence"], t_start=s["start"], t_end=s["end"],
                               title=f"Silencio de {s['end'] - s['start']:.1f} s", detail="Hueco de audio en medio del video.",
                               suggestion="Recortar el hueco o añadir música/ambiente.", source="code", check="silence"))

    audio = technical.get("audio")
    if audio and audio["peak_db"] >= float(th["clipping_peak_db"]) and audio["peak_count"] > int(th["clipping_min_count"]):
        out.append(Finding(id="clip-0", type="tecnico", severity=sev["audio_clipping"], t_start=0.0, t_end=dur,
                           title="Audio saturado (clipping)", detail=f"Pico {audio['peak_db']:.2f} dB con {audio['peak_count']} muestras al límite.",
                           suggestion="Bajar la ganancia de la voz/música.", source="code", check="audio_clipping"))

    if probe["height"] and abs(probe["width"] / probe["height"] - 9 / 16) > float(th["aspect_tolerance"]):
        out.append(Finding(id="aspect-0", type="tecnico", severity=sev["aspect_ratio"], t_start=0.0, t_end=dur,
                           title=f"Relación de aspecto {probe['width']}×{probe['height']} no es 9:16",
                           detail="Reels/TikTok esperan vertical 9:16.", suggestion="Exportar en 1080×1920.", source="code", check="aspect_ratio"))

    if not probe["has_audio"]:
        out.append(Finding(id="noaudio-0", type="tecnico", severity=sev["no_audio"], t_start=0.0, t_end=dur,
                           title="El video no tiene pista de audio", detail="No se pudo transcribir; los checks de guion no aplican.",
                           suggestion="Confirmar si es intencional.", source="code", check="no_audio"))
    return out
