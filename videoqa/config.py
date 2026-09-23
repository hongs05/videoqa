from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_REGLAS_REPO = Path(__file__).resolve().parent.parent / "reglas.yaml"
_REGLAS_PAQUETE = Path(__file__).resolve().parent / "reglas.yaml"

# En una copia del repositorio manda el reglas.yaml de la raíz: es el que edita
# el equipo (y el que toca /aura:ajustar). Instalado con pip esa ruta no existe,
# así que se usa la copia que viaja dentro del paquete con los valores por defecto.
RULES_PATH = _REGLAS_REPO if _REGLAS_REPO.exists() else _REGLAS_PAQUETE
_PROMPT_PAQUETE = Path(__file__).resolve().parent / "prompts" / "revisor-video.md"
_PROMPT_REPO = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "revisor-video" / "SKILL.md"

# El prompt del juez viaja dentro del paquete para que funcione instalado con
# pip; el de .claude/skills es el que lee Claude Code, y un test comprueba que
# los dos no se desincronicen.
SKILL_PATH = _PROMPT_PAQUETE if _PROMPT_PAQUETE.exists() else _PROMPT_REPO


def videoqa_home() -> Path:
    """Directorio base de estado/config de videoqa (por defecto ``~/.videoqa``).

    Se resuelve en cada llamada (nunca se cachea en una constante de módulo) para
    que ``VIDEOQA_HOME`` pueda fijarse en tiempo de ejecución -- en particular en
    los tests, que así nunca tocan el ``~/.videoqa`` real del usuario que corre
    la suite.
    """
    return Path(os.environ.get("VIDEOQA_HOME", Path.home() / ".videoqa")).expanduser()


def default_config_path() -> Path:
    return videoqa_home() / "config.yaml"


def token_path() -> Path:
    """Token de larga duración de Claude (lo escribe instalar/guardar-token.command)."""
    return videoqa_home() / "token"


def load_token() -> str | None:
    try:
        token = token_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return token or None


@dataclass
class Settings:
    drive_root: Path
    jobs_dir: Path = field(default_factory=lambda: videoqa_home() / "jobs")
    sheet_id: str | None = None
    service_account_json: Path | None = None
    claude_bin: str = "claude"
    whisper_model: str = "mlx-community/whisper-large-v3-turbo"
    # Idiomas del corrector ortográfico: una palabra solo es falta si falla en todos.
    # Los rótulos de redes mezclan español e inglés; con solo "es" salían como errores.
    idiomas: tuple[str, ...] = ("es", "en")

    @property
    def entrada(self) -> Path:
        return self.drive_root / "01_Entrada"

    @property
    def con_errores(self) -> Path:
        return self.drive_root / "02_Con_errores"

    @property
    def aprobado(self) -> Path:
        return self.drive_root / "03_Aprobado"

    @property
    def config_dir(self) -> Path:
        return self.drive_root / "_config"


def load_settings(path: Path | None = None) -> Settings:
    path = path or Path(os.environ.get("VIDEOQA_CONFIG", default_config_path()))
    data = yaml.safe_load(path.read_text()) or {}
    if "drive_root" not in data:
        raise ValueError(f"{path}: falta la clave 'drive_root'")
    kwargs = {"drive_root": Path(data["drive_root"]).expanduser()}
    if "jobs_dir" in data:
        kwargs["jobs_dir"] = Path(data["jobs_dir"]).expanduser()
    if data.get("sheet_id"):
        kwargs["sheet_id"] = str(data["sheet_id"])
    if data.get("service_account_json"):
        kwargs["service_account_json"] = Path(data["service_account_json"]).expanduser()
    if data.get("claude_bin"):
        kwargs["claude_bin"] = str(data["claude_bin"])
    if data.get("whisper_model"):
        kwargs["whisper_model"] = str(data["whisper_model"])
    if data.get("idiomas"):
        kwargs["idiomas"] = tuple(str(x) for x in data["idiomas"])
    return Settings(**kwargs)


def load_all_settings(path: Path | None = None) -> list[Settings]:
    """Todas las carpetas que esta instalación vigila.

    La primera es la principal (`drive_root`, normalmente la de Drive); detrás van
    las de `carpetas_extra`, pensadas para pre-chequeo local. Comparten motor y
    carpeta de trabajos, pero **solo la principal escribe en el Sheet**: el tablero
    es del equipo, y una carpeta personal no tiene por qué aparecer ahí.
    """
    path = path or Path(os.environ.get("VIDEOQA_CONFIG", default_config_path()))
    principal = load_settings(path)
    data = yaml.safe_load(path.read_text()) or {}

    todas = [principal]
    vistas = {principal.drive_root}
    for cruda in data.get("carpetas_extra") or []:
        ruta = Path(str(cruda)).expanduser()
        if ruta in vistas:
            continue
        vistas.add(ruta)
        todas.append(Settings(
            drive_root=ruta,
            jobs_dir=principal.jobs_dir,
            sheet_id=None,
            service_account_json=None,
            claude_bin=principal.claude_bin,
            whisper_model=principal.whisper_model,
            idiomas=principal.idiomas,
        ))
    return todas


def load_rules(path: Path = RULES_PATH) -> dict:
    return yaml.safe_load(path.read_text())
