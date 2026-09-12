from __future__ import annotations

import subprocess

from videoqa.job import Job


def _run(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


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
        _run(["-ss", f"{ts:.3f}", "-i", str(job.video), "-frames:v", "1", "-q:v", "3", str(out / name)])
        if (out / name).exists():
            frames.append({"file": f"frames/{name}", "t": ts, "kind": "scene"})
    frames.sort(key=lambda f: f["t"])
    return {"fps": fps, "period": period, "frames": frames}
