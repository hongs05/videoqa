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
    sev = rules["severities"]["brand_color"]
    out = []
    for i, a in enumerate(appearances):
        color = a.get("color_hex")
        if not color:
            continue
        nearest = min(palette, key=lambda p: hex_delta_e(color, p))
        de = hex_delta_e(color, nearest)
        if de <= tol:
            continue
        out.append(Finding(
            id=f"color-{i}", type="marca", severity=sev, t_start=a["t_start"], t_end=a["t_end"],
            title=f"Color de texto fuera de marca: {color}",
            detail=(f'El texto "{a["text"]}" usa {color}. Paleta permitida: {", ".join(palette)} '
                    f"(ΔE mínimo {de:.1f} respecto a {nearest})."),
            suggestion=f"Cambiar a {nearest} o a otro color de la paleta.",
            frame=a.get("frame"), bbox=a.get("bbox"), source="code", check="brand_color"))
    return out
