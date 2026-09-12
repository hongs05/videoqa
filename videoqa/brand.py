from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from videoqa.claude_runner import ClaudeError, Runner, extract_json

log = logging.getLogger("videoqa")

_HEX_RE = re.compile(r"^#?[0-9A-Fa-f]{6}$")

PDF_NAME = "guia_de_marca.pdf"
BRAND_NAME = "brand.json"

EMPTY_BRAND = {"palette": [], "fonts": [], "rules": [], "logo_required": False, "source_pdf_sha256": ""}

BRAND_PROMPT = f"""Eres un diseñador de marca. Lee el archivo `{PDF_NAME}` que está en este directorio
(usa la herramienta Read) y extrae la identidad visual para revisión de videos.

Responde ÚNICAMENTE con un JSON válido con este esquema exacto, sin texto adicional:
{{
  "palette": [{{"name": "<nombre>", "hex": "#RRGGBB"}}],
  "fonts": ["<nombre de fuente>"],
  "rules": ["<regla escrita de uso, una frase cada una, en español>"],
  "logo_required": true | false
}}

Instrucciones:
- Incluye en "palette" TODOS los colores que la guía permita para texto o fondos, en hex de 6 dígitos.
- En "rules" copia reglas explícitas sobre color de texto, tipografía, tamaños, posición del logo,
  palabras prohibidas o tono. Si la guía no dice nada, deja la lista vacía.
- "logo_required" es true solo si la guía exige el logo en cada pieza de video.
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def brand_is_stale(config_dir: Path) -> bool:
    pdf, brand = config_dir / PDF_NAME, config_dir / BRAND_NAME
    if not pdf.exists():
        return False
    if not brand.exists():
        return True
    try:
        saved = json.loads(brand.read_text()).get("source_pdf_sha256", "")
    except json.JSONDecodeError:
        return True
    if saved == _sha(pdf):
        return False
    return pdf.stat().st_mtime > brand.stat().st_mtime


def _coerced_list(value) -> list:
    return list(value) if isinstance(value, list) else []


def build_brand(config_dir: Path, runner: Runner) -> dict:
    pdf = config_dir / PDF_NAME
    data = extract_json(runner(BRAND_PROMPT, config_dir))
    if not isinstance(data, dict):
        raise ClaudeError(
            f"brand.json: respuesta de Claude con formato inesperado: "
            f"se esperaba un objeto JSON y se obtuvo {type(data).__name__}"
        )
    brand = dict(EMPTY_BRAND)

    palette = []
    for p in _coerced_list(data.get("palette", [])):
        if not isinstance(p, dict):
            continue
        hex_value = p.get("hex")
        if not isinstance(hex_value, str) or not _HEX_RE.match(hex_value):
            continue
        normalized = hex_value if hex_value.startswith("#") else f"#{hex_value}"
        palette.append({"name": str(p.get("name", "")), "hex": normalized.upper()})
    brand["palette"] = palette

    brand["fonts"] = [str(f) for f in _coerced_list(data.get("fonts", []))]
    brand["rules"] = [str(r) for r in _coerced_list(data.get("rules", []))]
    brand["logo_required"] = bool(data.get("logo_required", False))
    brand["source_pdf_sha256"] = _sha(pdf)
    (config_dir / BRAND_NAME).write_text(json.dumps(brand, ensure_ascii=False, indent=2))
    return brand


def load_brand(config_dir: Path, runner: Runner) -> dict:
    pdf, brand = config_dir / PDF_NAME, config_dir / BRAND_NAME
    if not pdf.exists():
        # Sin PDF, un brand.json escrito a mano es una configuración válida y soportada
        # (el equipo puede no tener la guía en PDF). Solo si tampoco hay brand.json —o no
        # parsea— se cae a la marca vacía, que desactiva el check de color.
        if brand.exists():
            try:
                data = json.loads(brand.read_text())
            except json.JSONDecodeError as e:
                log.warning("brand.json ilegible y sin %s para regenerarlo (%s); se omite la marca", PDF_NAME, e)
                return dict(EMPTY_BRAND)
            if isinstance(data, dict):
                log.info("usando brand.json manual (no hay %s)", PDF_NAME)
                return data
            log.warning("brand.json no es un objeto JSON y no hay %s para regenerarlo; se omite la marca", PDF_NAME)
        return dict(EMPTY_BRAND)
    if brand_is_stale(config_dir):
        return build_brand(config_dir, runner)
    try:
        return json.loads(brand.read_text())
    except json.JSONDecodeError:
        return build_brand(config_dir, runner)
