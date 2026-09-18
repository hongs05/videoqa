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


def test_las_reglas_viajan_dentro_del_paquete():
    """Sin esto, load_rules() falla al instalar el motor como librería."""
    import videoqa
    from videoqa.config import _REGLAS_PAQUETE

    paquete = Path(videoqa.__file__).resolve().parent
    assert _REGLAS_PAQUETE.exists() and _REGLAS_PAQUETE.is_relative_to(paquete)


def test_las_reglas_del_paquete_son_completas():
    import yaml

    from videoqa.config import _REGLAS_PAQUETE

    datos = yaml.safe_load(_REGLAS_PAQUETE.read_text(encoding="utf-8"))
    assert set(datos) >= {"severities", "thresholds", "frames", "claude"}


def test_en_el_repo_mandan_las_reglas_de_la_raiz():
    from videoqa.config import _REGLAS_REPO, RULES_PATH

    assert RULES_PATH == _REGLAS_REPO
