"""El motor se puede haber instalado como copia de carpeta (sin enlace a
internet): entonces `git pull` no tiene de dónde traer nada y la persona se
queda clavada en una versión vieja. `enlazar-motor.sh` arregla eso sin perder
lo que hubiera en la carpeta. Se prueba contra un «internet» de mentira: un
repositorio local."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins" / "aura" / "scripts" / "enlazar-motor.sh"

GIT_ID = [
    "-c", "user.name=Test",
    "-c", "user.email=test@videoqa.local",
    "-c", "commit.gpgsign=false",
]


def git(cwd: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", "-C", str(cwd), *GIT_ID, *args], capture_output=True, text=True
    )
    assert res.returncode == 0, res.stderr
    return res.stdout.strip()


def origen(tmp_path: Path) -> Path:
    """Un repositorio con dos versiones del motor, haciendo de internet."""
    fuente = tmp_path / "fuente"
    fuente.mkdir()
    git(fuente, "init", "-q", "-b", "main")
    (fuente / "motor.py").write_text("version = 1\n")
    (fuente / ".gitignore").write_text(".venv/\n")
    git(fuente, "add", "-A")
    git(fuente, "commit", "-q", "-m", "v1")
    (fuente / "motor.py").write_text("version = 2\n")
    git(fuente, "add", "-A")
    git(fuente, "commit", "-q", "-m", "v2")
    return fuente


def enlazar(motor: Path, remoto: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "HOME": str(motor.parent),
            "VIDEOQA_MOTOR": str(motor),
            "VIDEOQA_REMOTO": str(remoto),
            "VIDEOQA_RAMA": "main",
        },
    )


def copia_de_carpeta(tmp_path: Path, remoto: Path) -> Path:
    """Lo que deja un `rsync --exclude .git`: los archivos, sin el enlace."""
    motor = tmp_path / "casa" / "videoqa"
    motor.mkdir(parents=True)
    (motor / "motor.py").write_text("version = 1\n")
    (motor / ".gitignore").write_text(".venv/\n")
    return motor


def test_copia_sin_enlace_queda_enlazada_y_al_dia(tmp_path):
    remoto = origen(tmp_path)
    motor = copia_de_carpeta(tmp_path, remoto)

    res = enlazar(motor, remoto)

    assert res.returncode == 0, res.stdout + res.stderr
    assert res.stdout.split()[0] in {"enlazado", "enlazado-con-copia"}
    assert git(motor, "remote", "get-url", "origin") == str(remoto)
    assert (motor / "motor.py").read_text() == "version = 2\n"


def test_no_pierde_el_trabajo_que_tuviera_la_copia(tmp_path):
    remoto = origen(tmp_path)
    motor = copia_de_carpeta(tmp_path, remoto)
    (motor / "informe_word.py").write_text("logo = True\n")

    res = enlazar(motor, remoto)

    assert res.stdout.startswith("enlazado-con-copia"), res.stdout
    ramas = git(motor, "branch", "--list", "copia-local-*").split()
    assert ramas, "tiene que quedar una rama con lo que había en la copia"
    rama = ramas[-1]
    assert "logo = True" in git(motor, "show", f"{rama}:informe_word.py")


def test_lo_pesado_no_entra_en_la_copia_de_seguridad(tmp_path):
    remoto = origen(tmp_path)
    motor = copia_de_carpeta(tmp_path, remoto)
    (motor / ".venv").mkdir()
    (motor / ".venv" / "gordo.bin").write_text("x" * 1000)

    enlazar(motor, remoto)

    rama = git(motor, "branch", "--list", "copia-local-*").split()[-1]
    assert ".venv" not in git(motor, "ls-tree", "-r", "--name-only", rama)


def test_motor_ya_enlazado_y_limpio_no_toca_nada(tmp_path):
    remoto = origen(tmp_path)
    casa = tmp_path / "casa"
    casa.mkdir()
    motor = casa / "videoqa"
    subprocess.run(["git", "clone", "-q", str(remoto), str(motor)], check=True)

    res = enlazar(motor, remoto)

    assert res.returncode == 0
    assert res.stdout.startswith("ya-enlazado"), res.stdout
    assert not git(motor, "branch", "--list", "copia-local-*")


def test_motor_enlazado_con_cambios_a_mano_tambien_se_rescata(tmp_path):
    remoto = origen(tmp_path)
    casa = tmp_path / "casa"
    casa.mkdir()
    motor = casa / "videoqa"
    subprocess.run(["git", "clone", "-q", str(remoto), str(motor)], check=True)
    (motor / "motor.py").write_text("version = 1 y algo mio\n")

    res = enlazar(motor, remoto)

    assert res.stdout.startswith("enlazado-con-copia"), res.stdout
    rama = git(motor, "branch", "--list", "copia-local-*").split()[-1]
    assert "algo mio" in git(motor, "show", f"{rama}:motor.py")
    assert (motor / "motor.py").read_text() == "version = 2\n"


def test_sin_internet_lo_dice_y_no_destruye_nada(tmp_path):
    motor = copia_de_carpeta(tmp_path, tmp_path / "no-existe")
    (motor / "mio.txt").write_text("trabajo\n")

    res = enlazar(motor, tmp_path / "no-existe")

    assert res.returncode == 1
    assert res.stdout.startswith("sin-internet"), res.stdout
    assert (motor / "mio.txt").read_text() == "trabajo\n"
    assert (motor / "motor.py").read_text() == "version = 1\n"


def test_sin_motor_lo_dice(tmp_path):
    res = enlazar(tmp_path / "casa" / "videoqa", tmp_path / "fuente")

    assert res.returncode == 1
    assert res.stdout.startswith("no-instalado"), res.stdout
