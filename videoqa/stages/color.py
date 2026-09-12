from __future__ import annotations

import numpy as np
from PIL import Image

from videoqa.job import Job

FG_DISTANCE = 60.0  # distancia RGB mínima al fondo para contar como trazo
MIN_FG_PIXELS = 10


def dominant_text_color(img: Image.Image, bbox: list[float]) -> str | None:
    W, H = img.size
    x, y, w, h = bbox
    box = (int(x * W), int(y * H), max(int(x * W) + 2, int((x + w) * W)), max(int(y * H) + 2, int((y + h) * H)))
    a = np.asarray(img.crop(box).convert("RGB")).astype(float)
    if a.size == 0:
        return None
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    px = a.reshape(-1, 3)
    fg = px[np.linalg.norm(px - bg, axis=1) > FG_DISTANCE]
    if len(fg) < MIN_FG_PIXELS:
        return None
    r, g, b = np.median(fg, axis=0).round().astype(int)
    return f"#{r:02X}{g:02X}{b:02X}"


def add_colors(job: Job, ocr: dict) -> dict:
    cache: dict[str, Image.Image] = {}
    for app in ocr["appearances"]:
        img = cache.get(app["frame"])
        if img is None:
            img = cache[app["frame"]] = Image.open(job.path(app["frame"])).convert("RGB")
        app["color_hex"] = dominant_text_color(img, app["bbox"])
    return ocr
