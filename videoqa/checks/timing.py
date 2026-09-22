from __future__ import annotations

import re

from videoqa.checks.scene_text import is_scene_text
from videoqa.findings import Finding

_TOKEN = re.compile(r"[a-záéíóúüñ0-9]+")


def _tokens(s: str) -> set[str]:
    return set(_TOKEN.findall(s.lower()))


def best_segment(text: str, segments: list[dict]) -> tuple[dict | None, float]:
    t = _tokens(text)
    best, score = None, 0.0
    for seg in segments:
        s = _tokens(seg["text"])
        if not t or not s:
            continue
        j = len(t & s) / len(t | s)
        if j > score:
            best, score = seg, j
    return best, score


def _base(i: str, a: dict, typ: str, sev: str, title: str, detail: str, suggestion: str, check: str) -> Finding:
    return Finding(id=i, type=typ, severity=sev, t_start=a["t_start"], t_end=a["t_end"], title=title,
                   detail=detail, suggestion=suggestion, frame=a.get("frame"), bbox=a.get("bbox"),
                   source="code", check=check)


def check_visible_short(appearances: list[dict], rules: dict) -> list[Finding]:
    min_s = float(rules["thresholds"]["min_text_visible_s"])
    sev = rules["severities"]["text_visible_short"]
    short = [(i, a) for i, a in enumerate(appearances) if a["t_end"] - a["t_start"] < min_s]
    if not short:
        return []
    # Un aviso por texto daba cientos en videos con subtítulos palabra por palabra
    # (331 en un reel de 55 s). Es un solo patrón de edición: un solo hallazgo.
    i, a = short[0]
    dur = a["t_end"] - a["t_start"]
    if len(short) == 1:
        return [_base(f"short-{i}", a, "tecnico", sev, f"Texto visible solo {dur:.1f} s",
                      f'"{a["text"]}" aparece menos de {min_s:.1f} s; puede ser ilegible.',
                      "Mantener el texto en pantalla al menos 1 s.", "text_visible_short")]
    shown = "; ".join(f'"{b["text"]}" ({b["t_start"]:.1f} s)' for _, b in short[:5])
    more = f" y {len(short) - 5} más" if len(short) > 5 else ""
    return [_base(f"short-{i}", a, "tecnico", sev, f"{len(short)} textos visibles menos de {min_s:.1f} s",
                  f"Por ejemplo: {shown}{more}. Si los subtítulos van palabra por palabra a propósito, "
                  "es el estilo y no hay que tocar nada.",
                  "Si no es intencional, mantener cada texto en pantalla al menos 1 s.", "text_visible_short")]


def check_occluded(appearances: list[dict], rules: dict, vertical: bool = True) -> list[Finding]:
    """Zona segura de la UI de TikTok/Reels: solo aplica a video vertical.

    Los umbrales (`occluded_bottom`, `occluded_right`) describen dónde el feed
    vertical superpone caption, botones e iconos laterales. En un 16:9 no hay tal
    UI encima, así que marcar los subtítulos de la banda inferior —su sitio
    natural— era ruido puro.
    """
    if not vertical:
        return []
    th = rules["thresholds"]
    sev = rules["severities"]["text_occluded"]
    # Un subtítulo mal colocado lo está en TODO el video: un aviso por línea llenaba el
    # reporte con decenas de copias del mismo problema. Se agrupa por zona.
    groups: dict[tuple[str, ...], tuple[Finding, list[dict]]] = {}
    for i, a in enumerate(appearances):
        x, y, w, h = a["bbox"]
        reasons = []
        if y + h > float(th["occluded_bottom"]):
            reasons.append("banda inferior (caption/botones)")
        if x + w > float(th["occluded_right"]):
            reasons.append("franja derecha (iconos de like/comentar)")
        if not reasons:
            continue
        key = tuple(reasons)
        if key in groups:
            groups[key][1].append(a)
            continue
        groups[key] = (_base(f"occl-{i}", a, "tecnico", sev, "Texto en zona tapada por la UI de TikTok/Reels",
                             f'"{a["text"]}" cae en: {"; ".join(reasons)}.',
                             "Mover el texto hacia el centro/zona segura.", "text_occluded"), [])
    out = []
    for f, rest in groups.values():
        if rest:
            shown = "; ".join(f'"{b["text"]}" ({b["t_start"]:.1f} s)' for b in rest[:5])
            more = f" y {len(rest) - 5} más" if len(rest) > 5 else ""
            f.detail += f" Lo mismo pasa con {len(rest)} texto(s) más: {shown}{more}."
        out.append(f)
    return out


def check_desync(appearances: list[dict], segments: list[dict], rules: dict) -> list[Finding]:
    max_s = float(rules["thresholds"]["desync_s"])
    sev = rules["severities"]["subtitle_desync"]
    out = []
    for i, a in enumerate(appearances):
        seg, score = best_segment(a["text"], segments)
        if seg is None or score < 0.5:
            continue
        diff = a["t_start"] - seg["start"]
        if abs(diff) > max_s:
            out.append(_base(f"desync-{i}", a, "inconsistencia", sev, f"Subtítulo desincronizado {abs(diff):.1f} s",
                             f'"{a["text"]}" aparece en {a["t_start"]:.1f} s pero se dice en {seg["start"]:.1f} s '
                             f'("{seg["text"]}").', "Alinear el texto con el audio.", "subtitle_desync"))
    return out


def check_timing(appearances: list[dict], segments: list[dict], rules: dict, vertical: bool = True) -> list[Finding]:
    # Mismo filtro que ortografía y color: el OCR de baja confianza (texturas, bordados,
    # letras sueltas del fondo) suele durar un solo frame y cae en cualquier parte, así
    # que disparaba "texto visible 0.5 s" y "zona tapada" sobre texto que no existe.
    min_conf = float(rules["thresholds"].get("ocr_min_conf", 0.0))
    appearances = [a for a in appearances if float(a.get("conf", 1.0)) >= min_conf]
    # Duración mínima y zona segura son reglas de los rótulos de edición: una camiseta
    # que entra y sale de cuadro no es "texto ilegible".
    overlays = [a for a in appearances if not is_scene_text(a, rules)]
    return (check_visible_short(overlays, rules) + check_occluded(overlays, rules, vertical)
            + check_desync(overlays, segments, rules))
