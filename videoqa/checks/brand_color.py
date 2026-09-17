from __future__ import annotations

import logging

from videoqa.checks.colors import hex_delta_e
from videoqa.findings import Finding

log = logging.getLogger("videoqa")


def check_brand_colors(appearances: list[dict], brand: dict, rules: dict) -> list[Finding]:
    palette = [p["hex"].upper() for p in brand.get("palette", []) if p.get("hex")]
    if not palette:
        log.warning("brand.json sin paleta: se omite el check de color de marca")
        return []
    tol = float(rules["thresholds"]["color_delta_e"])
    min_conf = float(rules["thresholds"].get("ocr_min_conf", 0.0))
    sev = rules["severities"]["brand_color"]
    out = []
    for i, a in enumerate(appearances):
        # OCR de baja confianza = casi siempre un artefacto (logo bordado, textura);
        # su color no representa un rótulo real y disparaba bloqueantes falsos.
        if float(a.get("conf", 1.0)) < min_conf:
            continue
        # Un subtítulo con contorno tiene DOS tintas legítimas (relleno y borde):
        # basta con que UNA esté en paleta para que la aparición pase.
        candidates = [c for c in (a.get("color_candidates") or [a.get("color_hex")]) if c]
        if not candidates:
            continue
        best = min(((hex_delta_e(c, p), c, p) for c in candidates for p in palette), key=lambda t: t[0])
        de, _, nearest = best
        if de <= tol:
            continue
        shown = ", ".join(candidates)
        out.append(Finding(
            id=f"color-{i}", type="marca", severity=sev, t_start=a["t_start"], t_end=a["t_end"],
            title=f"Color de texto fuera de marca: {candidates[0]}",
            detail=(f'El texto "{a["text"]}" usa {shown}. Paleta permitida: {", ".join(palette)} '
                    f"(ΔE mínimo {de:.1f} respecto a {nearest})."),
            suggestion=f"Cambiar a {nearest} o a otro color de la paleta.",
            frame=a.get("frame"), bbox=a.get("bbox"), source="code", check="brand_color"))
    return out
