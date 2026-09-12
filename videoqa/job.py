from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

log = logging.getLogger("videoqa")

_UNSAFE_NAMES = {"", ".", ".."}
_SEPARATORS = {"/", os.sep, os.altsep} - {None}


def check_safe_stem(stem: str, video_name: str) -> None:
    """El *stem* del video se usa como nombre de carpeta (job dir y destino en Drive).

    Un video llamado ``...mp4`` tiene stem ``..``, y ``base / ".."`` es la carpeta
    padre: `reset()` o `deliver()` sobre ella borrarían el árbol entero. Se valida
    antes de calcular ninguna ruta o crear ningún directorio.
    """
    if stem in _UNSAFE_NAMES or any(sep in stem for sep in _SEPARATORS):
        raise ValueError(f"nombre de video inseguro: {video_name!r}")


class Job:
    """Directorio de trabajo de un video con etapas cacheadas en JSON."""

    def __init__(self, video: Path, jobs_root: Path):
        self.video = Path(video)
        self.name = self.video.stem
        check_safe_stem(self.name, self.video.name)
        self.dir = Path(jobs_root) / self.name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.dir / "state.json"

    def path(self, rel: str) -> Path:
        return self.dir / rel

    def _fingerprint(self) -> dict | None:
        """Tamaño y mtime del video actual, o None si el archivo no existe."""
        try:
            st = self.video.stat()
        except OSError:
            return None
        return {"video_size": st.st_size, "video_mtime": int(st.st_mtime)}

    def state(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {"video": str(self.video), "stages": {}}

    def record_video(self) -> None:
        """Fija en state.json la huella del archivo que este job dir describe."""
        st = self.state()
        fp = self._fingerprint()
        if fp is None:
            return
        st.update(fp)
        st["video"] = str(self.video)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(st, ensure_ascii=False, indent=2))

    def matches_current_video(self) -> bool:
        """True si state.json corresponde al archivo de video que hay ahora en disco.

        Falso si no hay estado previo, si no trae huella (jobs de versiones anteriores)
        o si el editor resubió un archivo distinto con el mismo nombre. En esos casos el
        caché de etapas no sirve y hay que hacer `reset()`; si coincide, un reintento del
        mismo archivo reaprovecha probe/transcribe/frames/ocr, que es lo caro.
        """
        if not self.state_path.exists():
            return False
        try:
            st = self.state()
        except (json.JSONDecodeError, OSError):
            return False
        fp = self._fingerprint()
        if fp is None or "video_size" not in st or "video_mtime" not in st:
            return False
        return st["video_size"] == fp["video_size"] and st["video_mtime"] == fp["video_mtime"]

    def _mark(self, stage: str, status: str, error: str | None = None) -> None:
        st = self.state()
        st["stages"][stage] = {"status": status, "at": datetime.now().isoformat(timespec="seconds")}
        if error:
            st["stages"][stage]["error"] = error
        self.state_path.write_text(json.dumps(st, ensure_ascii=False, indent=2))

    def run_stage(self, name: str, output_rel: str, fn: Callable[["Job"], dict]) -> dict:
        out = self.path(output_rel)
        if out.exists():
            log.info("[%s] etapa %s: cacheada", self.name, name)
            return json.loads(out.read_text())
        log.info("[%s] etapa %s: ejecutando", self.name, name)
        tmp = out.with_suffix(out.suffix + ".tmp")
        try:
            result = fn(self)
            tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            os.replace(tmp, out)
        except Exception as e:  # noqa: BLE001 — registramos y re-lanzamos
            self._mark(name, "failed", f"{type(e).__name__}: {e}")
            if tmp.exists():
                tmp.unlink()
            raise
        self._mark(name, "done")
        return result

    def reset(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True, exist_ok=True)
