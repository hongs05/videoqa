"""Los scripts que se entregan a mano no los cubre ningún test de integración:
al menos se comprueba que bash los puede parsear, para que un typo no llegue al
doble clic de la revisora."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = [
    ROOT / "instalar" / "install.sh",
    ROOT / "instalar" / "Instalar VideoQA.command",
    ROOT / "instalar" / "guardar-token.command",
    ROOT / "scripts" / "build_demo_zip.sh",
]


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_sintaxis_bash(script: Path) -> None:
    bash = shutil.which("bash")
    assert bash, "bash no disponible"
    assert script.exists(), f"falta {script}"
    res = subprocess.run([bash, "-n", str(script)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
