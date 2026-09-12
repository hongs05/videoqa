from __future__ import annotations

import logging
import subprocess

from videoqa.job import Job

log = logging.getLogger("videoqa")


def _run(args: list[str]) -> None:
    try:
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg falló: {e.stderr[-1000:] if e.stderr else e}") from e


def extract_frames(job: Job, scene_cuts: list[float], fps: int) -> dict:
    out = job.path("frames")
    out.mkdir(exist_ok=True)
    period = 1.0 / fps
    _run(["-i", str(job.video), "-vf", f"fps={fps}", "-q:v", "3", str(out / "sec_%04d.jpg")])
    frames = []
    for i, p in enumerate(sorted(out.glob("sec_*.jpg")), start=1):
        frames.append({"file": f"frames/{p.name}", "t": round((i - 1) * period, 3), "kind": "second"})
    for k, t in enumerate(scene_cuts, start=1):
        name = f"scene_{k:03d}.jpg"
        ts = round(t + 0.1, 3)
        try:
            _run(["-ss", f"{ts:.3f}", "-i", str(job.video), "-frames:v", "1", "-q:v", "3", str(out / name)])
        except RuntimeError as e:
            log.warning("[%s] no se pudo extraer frame de escena en %.2fs: %s", job.name, ts, e)
            continue
        if (out / name).exists():
            frames.append({"file": f"frames/{name}", "t": ts, "kind": "scene"})
    frames.sort(key=lambda f: f["t"])
    return {"fps": fps, "period": period, "frames": frames}
