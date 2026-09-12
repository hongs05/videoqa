from __future__ import annotations

import numpy as np
from PIL import Image

from videoqa.job import Job

FG_DISTANCE = 60.0  # distancia RGB mínima al fondo para contar como trazo
MIN_FG_PIXELS = 10
QUANT = 16          # tamaño de bin por canal (256/16 = 16 niveles)
MIN_CLUSTER_DIST = 80.0  # distancia RGB mínima entre los dos colores dominantes


def _hex(rgb: np.ndarray) -> str:
    r, g, b = np.clip(rgb.round(), 0, 255).astype(int)
    return f"#{r:02X}{g:02X}{b:02X}"


def text_colors(img: Image.Image, bbox: list[float]) -> list[str]:
    """Hasta 2 colores dominantes del texto, el más frecuente primero.

    Los subtítulos suelen llevar relleno + contorno (p.ej. blanco con borde negro).
    Tomar la mediana de TODOS los píxeles de trazo devolvía un gris intermedio que
    no existe en el video y disparaba falsos "color fuera de marca". En su lugar se
    cuantizan los píxeles de primer plano a bins de 16 niveles por canal y se
    devuelven los dos bins más poblados que estén separados al menos
    ``MIN_CLUSTER_DIST`` en RGB (si el segundo bin más poblado queda más cerca que
    eso del primero, es la misma tinta con ruido/antialias y se ignora).
    """
    W, H = img.size
    x, y, w, h = bbox
    box = (int(x * W), int(y * H), max(int(x * W) + 2, int((x + w) * W)), max(int(y * H) + 2, int((y + h) * H)))
    a = np.asarray(img.crop(box).convert("RGB")).astype(float)
    if a.size == 0:
        return []
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    px = a.reshape(-1, 3)
    fg = px[np.linalg.norm(px - bg, axis=1) > FG_DISTANCE]
    if len(fg) < MIN_FG_PIXELS:
        return []

    bins = (fg // QUANT).astype(int)
    keys = (bins[:, 0] << 10) | (bins[:, 1] << 5) | bins[:, 2]
    _, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
    sums = np.stack([np.bincount(inverse, weights=fg[:, c], minlength=len(counts)) for c in range(3)], axis=1)
    means = sums / counts[:, None]

    order = np.argsort(-counts)
    first = means[order[0]]
    out = [_hex(first)]
    for idx in order[1:]:
        if np.linalg.norm(means[idx] - first) >= MIN_CLUSTER_DIST:
            out.append(_hex(means[idx]))
            break
    return out


def dominant_text_color(img: Image.Image, bbox: list[float]) -> str | None:
    colors = text_colors(img, bbox)
    return colors[0] if colors else None


def add_colors(job: Job, ocr: dict) -> dict:
    cache: dict[str, Image.Image] = {}
    for app in ocr["appearances"]:
        img = cache.get(app["frame"])
        if img is None:
            img = cache[app["frame"]] = Image.open(job.path(app["frame"])).convert("RGB")
        colors = text_colors(img, app["bbox"])
        app["color_hex"] = colors[0] if colors else None
        app["color_candidates"] = colors
    return ocr
