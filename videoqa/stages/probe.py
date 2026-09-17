from __future__ import annotations

import json
import subprocess
from pathlib import Path

from videoqa.job import Job

FFPROBE_TIMEOUT_S = 900


def run_ffprobe(video: Path) -> dict:
    # Sin wrapper: un TimeoutExpired sube tal cual y lo atrapa el pipeline (except Exception),
    # que deja el video en 01_Entrada/ con estado ❌ Error.
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(video)]
    return json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True,
                                     timeout=FFPROBE_TIMEOUT_S).stdout)


def _fps(stream: dict) -> float:
    num, _, den = stream.get("r_frame_rate", "0/1").partition("/")
    return float(num) / float(den) if float(den or 0) else 0.0


def probe(job: Job) -> dict:
    raw = run_ffprobe(job.video)
    video = next(s for s in raw["streams"] if s["codec_type"] == "video")
    audio = next((s for s in raw["streams"] if s["codec_type"] == "audio"), None)
    return {
        "duration": float(raw["format"]["duration"]),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "fps": _fps(video),
        "has_audio": audio is not None,
    }
