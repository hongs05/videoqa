from __future__ import annotations

import hashlib
import json
from pathlib import Path

from videoqa.claude_runner import Runner, extract_json

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


def build_brand(config_dir: Path, runner: Runner) -> dict:
    pdf = config_dir / PDF_NAME
    data = extract_json(runner(BRAND_PROMPT, config_dir))
    brand = dict(EMPTY_BRAND)
    brand["palette"] = [{"name": str(p.get("name", "")), "hex": str(p["hex"]).upper()} for p in data.get("palette", []) if p.get("hex")]
    brand["fonts"] = [str(f) for f in data.get("fonts", [])]
    brand["rules"] = [str(r) for r in data.get("rules", [])]
    brand["logo_required"] = bool(data.get("logo_required", False))
    brand["source_pdf_sha256"] = _sha(pdf)
    (config_dir / BRAND_NAME).write_text(json.dumps(brand, ensure_ascii=False, indent=2))
    return brand


def load_brand(config_dir: Path, runner: Runner) -> dict:
    pdf, brand = config_dir / PDF_NAME, config_dir / BRAND_NAME
    if brand_is_stale(config_dir):
        return build_brand(config_dir, runner)
    if brand.exists():
        return json.loads(brand.read_text())
    return dict(EMPTY_BRAND)
