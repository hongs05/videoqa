from __future__ import annotations


def is_scene_text(a: dict, rules: dict) -> bool:
    """True si la aparición parece texto de la escena y no un rótulo de edición.

    El OCR lee también camisetas, carteles y empaques ("SUSHI CD" en la espalda del
    fotógrafo). Ese texto no lo escribió el editor ni lo puede corregir, pero se
    revisaba como si fuera un subtítulo y bloqueaba el video. Los rótulos de edición se
    quedan fijos en pantalla; el texto de la escena se mueve o cambia de tamaño.
    Los `ocr.json` de versiones anteriores no traen `motion`/`scale`: cuentan como rótulo.
    """
    th = rules["thresholds"]
    return (float(a.get("motion", 0.0)) > float(th.get("scene_text_motion", 0.03))
            or float(a.get("scale", 1.0)) > float(th.get("scene_text_scale", 1.25)))
