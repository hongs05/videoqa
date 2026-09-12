"""Genera videos sintéticos con errores sembrados, usando ffmpeg y `say` de macOS."""
from __future__ import annotations

import functools
import shutil
import subprocess
from pathlib import Path

# El ffmpeg estándar de Homebrew se compila sin freetype/libass, por lo que
# el filtro `drawtext` no está disponible. Si existe `ffmpeg-full` (con
# soporte de drawtext) lo preferimos; si no, caemos al `ffmpeg` del PATH.
_FFMPEG_CANDIDATES = [
    "ffmpeg",
    "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
    "/usr/local/opt/ffmpeg-full/bin/ffmpeg",
]


@functools.lru_cache(maxsize=1)
def _ffmpeg_bin() -> str:
    for candidate in _FFMPEG_CANDIDATES:
        path = candidate if candidate.startswith("/") else shutil.which(candidate)
        if not path or not Path(path).exists():
            continue
        try:
            out = subprocess.run([path, "-hide_banner", "-filters"],
                                  capture_output=True, text=True, check=True).stdout
        except (subprocess.CalledProcessError, OSError):
            continue
        if "drawtext" in out:
            return path
    return "ffmpeg"


FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
SIZE = "1080x1920"
DUR = 12
BG = "0x1A1A1A"
VOICE_TEXT = "Aprovecha la oferta de verano, solo por esta semana"

# Cuadrado blanco en movimiento para que ningún fixture sea un frame estático
# (evita que freezedetect se dispare); vive arriba a la izquierda, lejos del
# texto centrado.
MOVING_SQUARE = r",drawbox=x='mod(t*300\,600)':y=150:w=150:h=150:color=white:t=fill"


def _say(out_aiff: Path) -> None:
    if not out_aiff.exists():
        subprocess.run(["say", "-v", "Monica", "-o", str(out_aiff), VOICE_TEXT], check=True)


def _drawtext(text: str, color: str, start: float, end: float) -> str:
    return (f"drawtext=fontfile={FONT}:text='{text}':fontcolor={color}:fontsize=72:"
            f"x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,{start},{end})'")


def _render(out: Path, vf: str, audio: Path | None) -> None:
    cmd = [_ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", f"color=c={BG}:s={SIZE}:r=30:d={DUR}"]
    if audio:
        cmd += ["-i", str(audio)]
    cmd += ["-vf", vf, "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast"]
    if audio:
        cmd += ["-af", "apad", "-c:a", "aac"]
    else:
        cmd += ["-an"]
    cmd += ["-t", str(DUR), str(out)]
    subprocess.run(cmd, check=True)


def build_all(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    voice = out_dir / "voz.aiff"
    _say(voice)
    specs = {
        "spelling_color": (_drawtext("Aprobecha la oferta", "0xFF3B30", 2, 8) + MOVING_SQUARE, voice),
        "black_screen": (_drawtext("Oferta de verano", "0xFFFFFF", 1, 10)
                         + ",drawbox=enable='between(t,5,6)':x=0:y=0:w=iw:h=ih:color=black:t=fill"
                         + MOVING_SQUARE, voice),
        "clean": (_drawtext("Oferta de verano", "0xF5C518", 1, 10) + MOVING_SQUARE, voice),
        "no_audio": (_drawtext("Oferta de verano", "0xF5C518", 1, 10) + MOVING_SQUARE, None),
    }
    result = {}
    for name, (vf, audio) in specs.items():
        out = out_dir / f"{name}.mp4"
        if not out.exists():
            _render(out, vf, audio)
        result[name] = out
    return result


if __name__ == "__main__":
    for k, v in build_all(Path(__file__).parent / "out").items():
        print(k, v)
