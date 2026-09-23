"""Perfiles por cliente y brief por pieza.

Una agencia no revisa igual el reel de un cliente que el de otro: cambia la marca, el tono, lo
prohibido, lo obligatorio y cuánto bloquea cada cosa. El cliente de un video sale de su
carpeta:

    01_Entrada/<Cliente>/reel.mp4          → perfil `_config/clientes/<Cliente>/`
    01_Entrada/reel.mp4                    → perfil general (`_config/`), como siempre

Un perfil de cliente puede traer (todo opcional; lo que falta se hereda del general):

    guia_de_marca.pdf o brand.json   su marca (sustituye a la general)
    glosario.txt                     palabras válidas (se SUMAN a las generales)
    criterios.md                     criterios en lenguaje normal para el juez
    reglas.yaml                      cambios de gravedad/umbrales sobre `reglas.yaml`

Y cada pieza puede llevar su brief al lado, con el mismo nombre: `reel.txt` o `reel.md`
(objetivo, guion previsto, copy, CTA). El juez lo usa para detectar lo que falta o no cuadra.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from videoqa.config import Settings
from videoqa.job import check_safe_stem

CLIENTS_DIR = "clientes"
JOBS_SUBDIR = "_clientes"
BRIEF_EXTS = (".txt", ".md")
MAX_BRIEF_CHARS = 6000  # un brief es una página, no un manual: acota el gasto del juez
_FLOW_DIRS = ("01_Entrada", "02_Con_errores", "03_Aprobado", "04_Pruebas_respaldo")


@dataclass
class Profile:
    client: str | None                      # None = perfil general
    dir: Path                               # carpeta de donde salen marca/glosario/criterios
    criteria: str = ""
    glossary_text: str = ""
    rule_overrides: dict = field(default_factory=dict)


def is_client_folder(name: str) -> bool:
    return bool(name) and not name.startswith((".", "_"))


def client_of(video: Path, settings: Settings) -> str | None:
    """Cliente de un video por su carpeta, o None si va suelto.

    Reconoce `01_Entrada/<Cliente>/v.mp4` y, para videos ya revisados,
    `02_Con_errores|03_Aprobado|04_Pruebas_respaldo/<Cliente>/<nombre>/v.mp4`.
    """
    try:
        parts = Path(video).resolve().relative_to(settings.drive_root.resolve()).parts
    except ValueError:
        return None
    if len(parts) == 3 and parts[0] == "01_Entrada" and is_client_folder(parts[1]):
        client = parts[1]
    elif len(parts) == 4 and parts[0] in _FLOW_DIRS[1:] and is_client_folder(parts[1]):
        client = parts[1]
    else:
        return None
    check_safe_stem(client, client)  # nombre de carpeta: nunca "..", nunca con "/"
    return client


def profile_dir(settings: Settings, client: str) -> Path:
    return settings.config_dir / CLIENTS_DIR / client


def jobs_root(settings: Settings, client: str | None) -> Path:
    """Donde viven los job dirs: los de un cliente, aparte (dos clientes pueden tener "reel3")."""
    return settings.jobs_dir / JOBS_SUBDIR / client if client else settings.jobs_dir


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_profile(settings: Settings, client: str | None) -> Profile:
    general_glossary = _read(settings.config_dir / "glosario.txt")
    if not client:
        return Profile(None, settings.config_dir, glossary_text=general_glossary)
    d = profile_dir(settings, client)
    overrides = {}
    if (d / "reglas.yaml").exists():
        overrides = yaml.safe_load((d / "reglas.yaml").read_text(encoding="utf-8")) or {}
        if not isinstance(overrides, dict):
            overrides = {}
    own_glossary = _read(d / "glosario.txt")
    glossary = general_glossary + ("\n# " + client + "\n" + own_glossary if own_glossary else "")
    return Profile(client, d, criteria=_read(d / "criterios.md").strip(), glossary_text=glossary,
                   rule_overrides=overrides)


def brand_dir(settings: Settings, profile: Profile) -> Path:
    """La marca del cliente si tiene la suya (PDF o brand.json); si no, la general."""
    if profile.client and ((profile.dir / "guia_de_marca.pdf").exists() or (profile.dir / "brand.json").exists()):
        return profile.dir
    return settings.config_dir


def merged_rules(rules: dict, overrides: dict) -> dict:
    """`reglas.yaml` general con los cambios del cliente encima (fusión por claves)."""
    out = copy.deepcopy(rules)

    def merge(dst: dict, src: dict) -> None:
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                merge(dst[k], v)
            else:
                dst[k] = v

    merge(out, overrides)
    return out


def glossary_words(text: str) -> set[str]:
    return {ln.strip().lower() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")}


def brief_path(video: Path) -> Path | None:
    for ext in BRIEF_EXTS:
        candidate = Path(video).with_suffix(ext)
        if candidate.exists():
            return candidate
    return None


def load_brief(video: Path) -> str:
    path = brief_path(video)
    if path is None:
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if len(text) > MAX_BRIEF_CHARS:
        text = text[:MAX_BRIEF_CHARS] + "\n[… brief recortado]"
    return text
