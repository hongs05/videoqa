from __future__ import annotations

import re
import subprocess

from videoqa.job import Job

_BLACK = re.compile(r"black_start:([\d.]+)\s+black_end:([\d.]+)")
_FREEZE_START = re.compile(r"freeze_start:\s*([\d.]+)")
_FREEZE_END = re.compile(r"freeze_end:\s*([\d.]+)")
_SCENE = re.compile(r"pts_time:([\d.]+)")
_SIL_START = re.compile(r"silence_start:\s*([\d.]+)")
_SIL_END = re.compile(r"silence_end:\s*([\d.]+)")
_PEAK_DB = re.compile(r"Peak level dB:\s*(-?[\d.]+|-inf)")
_PEAK_COUNT = re.compile(r"Peak count:\s*(\d+)")


def _ffmpeg(args: list[str]) -> str:
    cmd = ["ffmpeg", "-hide_banner", "-nostats", *args, "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {proc.stderr[-1000:]}")
    return proc.stderr


def parse_black(stderr: str) -> list[dict]:
    return [{"start": float(a), "end": float(b)} for a, b in _BLACK.findall(stderr)]


def parse_freeze(stderr: str) -> list[dict]:
    starts = [float(x) for x in _FREEZE_START.findall(stderr)]
    ends = [float(x) for x in _FREEZE_END.findall(stderr)]
    return [{"start": s, "end": e} for s, e in zip(starts, ends)]


def parse_scene(stderr: str) -> list[float]:
    return [float(x) for x in _SCENE.findall(stderr)]


def parse_silence(stderr: str) -> list[dict]:
    starts = [float(x) for x in _SIL_START.findall(stderr)]
    ends = [float(x) for x in _SIL_END.findall(stderr)]
    return [{"start": s, "end": e} for s, e in zip(starts, ends)]


def parse_astats(stderr: str) -> dict | None:
    overall = stderr.rsplit("Overall", 1)
    if len(overall) < 2:
        return None
    tail = overall[1]
    db = _PEAK_DB.search(tail)
    cnt = _PEAK_COUNT.search(tail)
    if not db:
        return None
    peak = float("-inf") if db.group(1) == "-inf" else float(db.group(1))
    return {"peak_db": peak, "peak_count": int(cnt.group(1)) if cnt else 0}


def analyze(job: Job, has_audio: bool, scene_threshold: float) -> dict:
    video = str(job.video)
    vid_err = _ffmpeg(["-i", video, "-vf", "blackdetect=d=0.3:pix_th=0.10,freezedetect=n=-60dB:d=0.3", "-an"])
    scene_err = _ffmpeg(["-i", video, "-vf", f"select='gt(scene,{scene_threshold})',showinfo",
                         "-fps_mode", "vfr", "-an"])
    result = {
        "black": parse_black(vid_err),
        "freeze": parse_freeze(vid_err),
        "scene_cuts": parse_scene(scene_err),
        "silence": [],
        "audio": None,
    }
    if has_audio:
        aud_err = _ffmpeg(["-i", video, "-af", "silencedetect=n=-35dB:d=1.0,astats=metadata=0", "-vn"])
        result["silence"] = parse_silence(aud_err)
        result["audio"] = parse_astats(aud_err)
    return result
