from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Callable

from videoqa.claude_runner import Runner
from videoqa.config import Settings
from videoqa.doctor_state import load_wait_until
from videoqa.pipeline import process_video
from videoqa.sheet import SheetWriter

log = logging.getLogger("videoqa")
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
FAILED_STATE_NAME = "watch_failed.json"


def list_videos(entrada: Path) -> list[Path]:
    if not entrada.exists():
        return []
    vids = [p for p in entrada.iterdir() if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in VIDEO_EXT]
    return sorted(vids, key=lambda p: p.stat().st_mtime)


def is_stable(path: Path, wait_s: float = 30, poll_s: float = 5, sleep: Callable[[float], None] = time.sleep) -> bool:
    """True si el tamaño no cambia durante wait_s (Drive termina de escribir)."""
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return False
    elapsed = 0.0
    while elapsed < wait_s:
        sleep(poll_s)
        elapsed += poll_s
        try:
            now = path.stat().st_size
        except FileNotFoundError:
            return False
        if now != size:
            return False
    return size > 0


def _load_failed(path: Path) -> dict[str, float]:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_failed(path: Path, failed: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(failed))


def _failed_key(video: Path) -> str:
    """Clave de estado de reintento para `video`.

    Incluye mtime y tamaño (no solo la ruta) para que volver a subir un archivo
    con el mismo nombre pero contenido distinto (el editor corrige y resube tras
    un fallo) cuente como un video nuevo y se procese de inmediato, en vez de
    quedar bloqueado hasta `retry_after_s` por el fallo del archivo anterior.
    """
    try:
        st = video.stat()
        return f"{video}|{int(st.st_mtime)}|{st.st_size}"
    except FileNotFoundError:
        return str(video)


def watch(settings: Settings | list[Settings], rules: dict, runner: Runner,
          sheet: SheetWriter | None = None, poll_s: float = 10,
          once: bool = False, process=process_video, sleep: Callable[[float], None] = time.sleep,
          stable_wait_s: float = 30, retry_after_s: float = 600, unstable_warn_s: float = 600) -> None:
    """Vigila una carpeta o varias (por ejemplo la de Drive y una local de pruebas).

    Con varias se recorren por turnos en cada ciclo, una detrás de otra: cada video
    se procesa con los ajustes de SU carpeta, así que nunca se entrega en la que no
    es. El estado de reintentos es común, porque va por ruta completa.
    """
    carpetas = [settings] if isinstance(settings, Settings) else list(settings)
    if not carpetas:
        raise ValueError("watch necesita al menos una carpeta")
    principal = carpetas[0]
    # El estado de reintento se persiste en disco (no solo en memoria) para que un
    # reinicio del watcher (p.ej. launchd con KeepAlive tras un crash) no reprocese
    # de inmediato un video que falló hace poco.
    state_path = principal.jobs_dir / FAILED_STATE_NAME
    failed = _load_failed(state_path)
    # Primer momento en que vimos cada archivo aún inestable, y si ya avisamos por él.
    # Un archivo que lleva >10 min "sincronizando" casi siempre es Drive atascado o una
    # subida interrumpida: se avisa UNA vez para que alguien mire, y se sigue reintentando.
    unstable_since: dict[str, float] = {}
    warned_unstable: set[str] = set()
    for c in carpetas:
        log.info("vigilando %s", c.entrada)
    # Límite de uso de Claude: si un video lo encontró, TODOS los siguientes también lo
    # harían. Se pausa la cola entera hasta la hora de reinicio (leída también del disco,
    # para que un reinicio del watcher no la ignore).
    # Con el juez de respaldo encendido no se pausa de entrada: los videos los revisa el
    # modelo local mientras Claude no tenga uso (solo se pausa si el respaldo también falla).
    from videoqa.local_judge import fallback_config

    pause_until = 0.0 if fallback_config(rules) else (load_wait_until() or 0.0)
    pause_logged = 0.0  # se avisa una vez por pausa, no en cada vuelta de 10 s
    while True:
        for carpeta in carpetas:
            pendientes = list_videos(carpeta.entrada)
            if pendientes and time.time() < pause_until:
                if pause_logged != pause_until:
                    pause_logged = pause_until
                    log.info("Claude sin uso disponible hasta las %s: los videos esperan en 01_Entrada",
                             time.strftime("%H:%M", time.localtime(pause_until)))
                continue
            for video in pendientes:
                if time.time() < pause_until:
                    break
                key = _failed_key(video)
                if key in failed:
                    elapsed = time.time() - failed[key]
                    if elapsed < retry_after_s:
                        log.info("%s falló hace %.0fs; se reintenta en %.0fs", video.name, elapsed, retry_after_s - elapsed)
                        continue
                if stable_wait_s and not is_stable(video, wait_s=stable_wait_s, sleep=sleep):
                    now = time.time()
                    first_seen = unstable_since.setdefault(str(video), now)
                    if now - first_seen > unstable_warn_s and str(video) not in warned_unstable:
                        warned_unstable.add(str(video))
                        log.warning("%s lleva más de %.0f min sincronizando; revisa Google Drive "
                                    "(¿subida interrumpida o archivo bloqueado?)", video.name, unstable_warn_s / 60)
                    log.info("%s aún sincronizando; se reintenta en el próximo ciclo", video.name)
                    continue
                unstable_since.pop(str(video), None)
                warned_unstable.discard(str(video))
                try:
                    result = process(video, carpeta, rules, runner, sheet=sheet)
                except Exception:
                    log.exception("[%s] error inesperado procesando", video.name)
                    failed[key] = time.time()
                    _save_failed(state_path, failed)
                    continue
                if result.status == "waiting":
                    # No es un fallo del video: no se anota en `failed` (eso lo retrasaría
                    # retry_after_s más), solo se pausa la cola hasta que vuelva el uso.
                    pause_until = result.retry_at.timestamp() if result.retry_at else time.time() + 3600
                    continue
                if result.status == "error" and result.dest is None:
                    failed[key] = time.time()
                else:
                    failed.pop(key, None)
                _save_failed(state_path, failed)
        if once:
            return
        sleep(poll_s)
