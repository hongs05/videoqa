from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

log = logging.getLogger("videoqa")


class Job:
    """Directorio de trabajo de un video con etapas cacheadas en JSON."""

    def __init__(self, video: Path, jobs_root: Path):
        self.video = Path(video)
        self.name = self.video.stem
        self.dir = Path(jobs_root) / self.name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.dir / "state.json"

    def path(self, rel: str) -> Path:
        return self.dir / rel

    def state(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {"video": str(self.video), "stages": {}}

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
