"""Registro de implementaciones dependientes del sistema operativo.

El motor trae la pila de Apple (Vision, MLX, NSSpellChecker) como valor por
defecto. Un proyecto que corra en otra plataforma — por ejemplo videoqa-win —
registra aquí sus propias implementaciones antes de usar el pipeline.
"""
from __future__ import annotations

from typing import Callable

_ocr: Callable | None = None
_transcriber: Callable | None = None
_speller: Callable | None = None


def register_ocr(fn: Callable) -> None:
    """fn(path) -> [{"text", "conf", "bbox": [x, y, w, h] normalizado}]"""
    global _ocr
    _ocr = fn


def register_transcriber(fn: Callable) -> None:
    """fn(job, has_audio, model) -> {"language", "text", "segments"}"""
    global _transcriber
    _transcriber = fn


def register_speller(fn: Callable) -> None:
    """fn(languages: tuple[str, ...]) -> objeto con is_known / unknown / correction.

    `videoqa/pipeline.py` construye el corrector pasando `settings.idiomas`; una fábrica
    que no acepte argumentos también funciona (el punto de llamada cae a `fn()` si
    `fn(settings.idiomas)` da `TypeError`).
    """
    global _speller
    _speller = fn


def reset() -> None:
    """Vuelve a los valores por defecto. Pensado para los tests."""
    global _ocr, _transcriber, _speller
    _ocr = _transcriber = _speller = None


def get_ocr() -> Callable:
    if _ocr is not None:
        return _ocr
    from videoqa.stages.ocr import _ocr_frame_apple

    return _ocr_frame_apple


def get_transcriber() -> Callable:
    if _transcriber is not None:
        return _transcriber
    from videoqa.stages.transcribe import _transcribe_apple

    return _transcribe_apple


def get_speller() -> Callable:
    if _speller is not None:
        return _speller
    from videoqa.checks.spelling import MacSpellChecker

    return MacSpellChecker
