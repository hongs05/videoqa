from pathlib import Path

from videoqa.config import SKILL_PATH

REPO_SKILL = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "revisor-video" / "SKILL.md"


def _cuerpo(texto: str) -> str:
    """Devuelve el contenido sin el frontmatter YAML (--- … ---)."""
    if texto.startswith("---"):
        return texto.split("---", 2)[2].strip()
    return texto.strip()


def test_el_prompt_vive_dentro_del_paquete():
    import videoqa

    paquete = Path(videoqa.__file__).resolve().parent
    assert SKILL_PATH.exists()
    assert SKILL_PATH.is_relative_to(paquete), f"{SKILL_PATH} está fuera del paquete"


def test_el_prompt_del_paquete_y_el_de_claude_code_coinciden():
    assert REPO_SKILL.exists(), "la skill que lee Claude Code tiene que seguir ahí"
    assert _cuerpo(SKILL_PATH.read_text(encoding="utf-8")) == _cuerpo(REPO_SKILL.read_text(encoding="utf-8"))


def test_el_prompt_tiene_las_secciones_clave():
    texto = SKILL_PATH.read_text(encoding="utf-8")
    for seccion in ("# Rol", "# Entradas", "# Qué revisar", "# Guion real", "# Salida", "# Seguridad"):
        assert seccion in texto, f"falta la sección {seccion}"
