from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path.home() / ".videoqa" / "config.yaml"
RULES_PATH = Path(__file__).resolve().parent.parent / "reglas.yaml"
SKILL_PATH = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "revisor-video" / "SKILL.md"


@dataclass
class Settings:
    drive_root: Path
    jobs_dir: Path = field(default_factory=lambda: Path.home() / ".videoqa" / "jobs")
    sheet_id: str | None = None
    service_account_json: Path | None = None
    claude_bin: str = "claude"
    whisper_model: str = "mlx-community/whisper-large-v3-turbo"

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
    path = path or Path(os.environ.get("VIDEOQA_CONFIG", DEFAULT_CONFIG))
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
    return Settings(**kwargs)


def load_rules(path: Path = RULES_PATH) -> dict:
    return yaml.safe_load(path.read_text())
