from __future__ import annotations

import re

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
    out = []
    for i, a in enumerate(appearances):
        dur = a["t_end"] - a["t_start"]
        if dur < min_s:
            out.append(_base(f"short-{i}", a, "tecnico", sev, f"Texto visible solo {dur:.1f} s",
                             f'"{a["text"]}" aparece menos de {min_s:.1f} s; puede ser ilegible.',
                             "Mantener el texto en pantalla al menos 1 s.", "text_visible_short"))
    return out


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
    out = []
    for i, a in enumerate(appearances):
        x, y, w, h = a["bbox"]
        reasons = []
        if y + h > float(th["occluded_bottom"]):
            reasons.append("banda inferior (caption/botones)")
        if x + w > float(th["occluded_right"]):
            reasons.append("franja derecha (iconos de like/comentar)")
        if reasons:
            out.append(_base(f"occl-{i}", a, "tecnico", sev, "Texto en zona tapada por la UI de TikTok/Reels",
                             f'"{a["text"]}" cae en: {"; ".join(reasons)}.',
                             "Mover el texto hacia el centro/zona segura.", "text_occluded"))
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
    return (check_visible_short(appearances, rules) + check_occluded(appearances, rules, vertical)
            + check_desync(appearances, segments, rules))
