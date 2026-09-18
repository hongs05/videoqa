from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

from videoqa.job import Job

_WS = re.compile(r"\s+")
TEXT_SIM_MIN = 0.75  # tolera pequeñas variaciones de OCR entre frames consecutivos


_DIGITS = re.compile(r"\d+")


def norm_text(s: str) -> str:
    return _WS.sub(" ", s).strip().lower()


def _digit_runs(s: str) -> list[str]:
    return _DIGITS.findall(s)


def _texts_compatible(a: str, b: str) -> bool:
    """True si los textos pueden fusionarse por similitud.

    Compara las secuencias de dígitos de ambos textos solo cuando AMBOS
    contienen al menos un dígito; si difieren (p.ej. "20%" vs "25%",
    "martes 12" vs "martes 13"), nunca se fusionan aunque el ratio de
    similitud sea alto. Si solo uno de los dos tiene dígitos (p.ej. ruido
    de OCR como "0ferta" contra "Oferta"), se ignora esta guarda y se
    recurre solo a la similitud de texto, ya que ahí el dígito es en
    realidad una letra mal reconocida.
    """
    da, db = _digit_runs(a), _digit_runs(b)
    if da and db and da != db:
        return False
    return True


def iou(a: list[float], b: list[float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def ocr_frame(path: Path) -> list[dict]:
    """Delega en el backend registrado (Apple Vision por defecto)."""
    from videoqa import backends

    return backends.get_ocr()(path)


def _ocr_frame_apple(path: Path) -> list[dict]:
    from ocrmac import ocrmac  # import tardío: pyobjc/Vision

    results = ocrmac.OCR(str(path), language_preference=["es-ES"], recognition_level="accurate").recognize()
    items = []
    for text, conf, (x, y, w, h) in results:  # Vision: normalizado, origen abajo-izquierda
        items.append({"text": text, "conf": float(conf), "bbox": [float(x), float(1 - y - h), float(w), float(h)]})
    return items


def dedupe(raw: list[dict], period: float, gap: float = 1.5, iou_min: float = 0.3) -> list[dict]:
    """Agrupa detecciones del mismo texto en frames consecutivos en 'apariciones'."""
    apps: list[dict] = []
    for frame in sorted(raw, key=lambda f: f["t"]):
        for it in frame["items"]:
            key = norm_text(it["text"])
            match = None
            for a in apps:
                if (frame["t"] - a["_last_t"] <= gap and iou(a["bbox"], it["bbox"]) >= iou_min
                        and _texts_compatible(a["_key"], key)
                        and SequenceMatcher(None, a["_key"], key).ratio() >= TEXT_SIM_MIN):
                    match = a
                    break
            if match is None:
                apps.append({"text": it["text"], "_key": key, "_conf": it["conf"], "bbox": it["bbox"],
                             "t_start": frame["t"], "_last_t": frame["t"], "frame": frame["file"],
                             "frames": [frame["file"]]})
            else:
                match["_last_t"] = frame["t"]
                match["frames"].append(frame["file"])
                if it["conf"] > match["_conf"]:
                    match["text"], match["_conf"], match["_key"] = it["text"], it["conf"], key
    out = []
    for a in apps:
        # `conf` = confianza MÁXIMA vista para esta aparición. Se expone (antes se
        # descartaba con el resto de campos `_`) porque los checks de ortografía y
        # color usan un umbral mínimo: el OCR lee texturas y bordados de la ropa con
        # confianza muy baja y esos artefactos generaban bloqueantes falsos.
        out.append({"text": a["text"], "conf": a["_conf"], "bbox": a["bbox"], "t_start": a["t_start"],
                    "t_end": round(a["_last_t"] + period, 3), "frame": a["frame"], "frames": a["frames"]})
    return out


def ocr_frames(job: Job, frames: list[dict], period: float) -> dict:
    raw = [{"file": f["file"], "t": f["t"], "items": ocr_frame(job.path(f["file"]))} for f in frames]
    return {"raw": raw, "appearances": dedupe(raw, period=period)}
