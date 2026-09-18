"""El plugin `aura` se instala desde el marketplace de este mismo repo, así que
un manifiesto mal escrito o un SKILL.md con el frontmatter torcido no rompe
ningún test de pipeline: rompe la instalación de la revisora. Estos tests
cubren ese hueco sin necesidad de tener `claude` instalado."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from videoqa.config import SKILL_PATH

ROOT = Path(__file__).resolve().parents[2]
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
PLUGIN = ROOT / "plugins" / "aura" / ".claude-plugin" / "plugin.json"
SKILLS_DIR = ROOT / "plugins" / "aura" / "skills"

# Skills con efectos secundarios: solo las lanza la persona, nunca el modelo.
SIDE_EFFECT_SKILLS = {"instalar", "ajustar", "activar-automatico", "actualizar"}

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def skill_files() -> list[Path]:
    return sorted(SKILLS_DIR.glob("*/SKILL.md"))


def frontmatter(path: Path) -> dict:
    m = FRONTMATTER.match(path.read_text())
    assert m, f"{path}: falta el frontmatter YAML al principio del archivo"
    data = yaml.safe_load(m.group(1))
    assert isinstance(data, dict), f"{path}: el frontmatter no es un mapa"
    return data


def test_manifiestos_parsean_y_concuerdan() -> None:
    market = json.loads(MARKETPLACE.read_text())
    plugin = json.loads(PLUGIN.read_text())

    assert market["name"] == "videoqa"
    assert market["owner"]["name"]

    entradas = [p for p in market["plugins"] if p["name"] == "aura"]
    assert len(entradas) == 1, "el marketplace debe listar aura exactamente una vez"
    entrada = entradas[0]

    origen = (MARKETPLACE.parent.parent / entrada["source"]).resolve()
    assert origen == PLUGIN.parent.parent, f"source apunta a {origen}"
    assert origen.is_dir()

    assert plugin["name"] == "aura"
    assert plugin["version"] == entrada["version"]
    assert len(plugin["description"]) <= 200


def test_hay_skills() -> None:
    nombres = {p.parent.name for p in skill_files()}
    assert SIDE_EFFECT_SKILLS <= nombres
    assert {"revisar", "estado"} <= nombres


@pytest.mark.parametrize("skill", skill_files(), ids=lambda p: p.parent.name)
def test_frontmatter_del_skill(skill: Path) -> None:
    fm = frontmatter(skill)

    # `name` es redundante (el nombre sale del directorio) y desincroniza el menú.
    assert "name" not in fm, f"{skill}: quita el campo 'name' del frontmatter"

    desc = fm.get("description")
    assert desc, f"{skill}: falta 'description'"
    assert len(desc) <= 200, f"{skill}: description de {len(desc)} caracteres (máx 200)"

    assert fm.get("allowed-tools"), f"{skill}: falta 'allowed-tools'"

    nombre = skill.parent.name
    if nombre in SIDE_EFFECT_SKILLS:
        assert fm.get("disable-model-invocation") is True, (
            f"{skill}: tiene efectos secundarios, necesita disable-model-invocation: true"
        )
    else:
        assert "disable-model-invocation" not in fm, (
            f"{skill}: déjalo al valor por defecto para que Claude pueda proponerlo"
        )


def test_skill_del_motor_sigue_en_su_sitio() -> None:
    # El plugin se llevó los skills de la persona; el criterio del juez no.
    # Desde que el motor se instala como librería, el prompt vive dentro del
    # paquete (videoqa/prompts) y .claude/skills conserva el que lee Claude Code.
    assert SKILL_PATH.exists(), f"falta {SKILL_PATH}"
    assert SKILL_PATH.parent.name == "prompts"
    assert (ROOT / ".claude" / "skills" / "revisor-video" / "SKILL.md").exists()


def test_hook_de_sesion() -> None:
    hooks = json.loads((ROOT / "plugins" / "aura" / "hooks" / "hooks.json").read_text())
    entradas = hooks["hooks"]["SessionStart"]
    comandos = [h["command"] for e in entradas for h in e["hooks"]]
    assert any("check-engine.sh" in c for c in comandos)
    script = ROOT / "plugins" / "aura" / "scripts" / "check-engine.sh"
    assert script.exists() and script.stat().st_mode & 0o111, f"{script} tiene que ser ejecutable"
