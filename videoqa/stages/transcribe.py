from __future__ import annotations

import subprocess
from pathlib import Path

from videoqa.job import Job

EMPTY = {"language": "es", "text": "", "segments": []}


def extract_audio(video: Path, wav: Path) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
                    "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)


def normalize(raw: dict) -> dict:
    segments = []
    for s in raw.get("segments", []):
        text = str(s.get("text", "")).strip()
        if text:
            segments.append({"start": round(float(s["start"]), 2), "end": round(float(s["end"]), 2), "text": text})
    return {"language": raw.get("language", "es"), "text": " ".join(s["text"] for s in segments), "segments": segments}


def transcribe(job: Job, has_audio: bool, model: str) -> dict:
    if not has_audio:
        return dict(EMPTY)
    wav = job.path("audio.wav")
    extract_audio(job.video, wav)
    import mlx_whisper  # import tardío: carga MLX solo cuando hace falta

    raw = mlx_whisper.transcribe(str(wav), path_or_hf_repo=model, language="es")
    return normalize(raw)
