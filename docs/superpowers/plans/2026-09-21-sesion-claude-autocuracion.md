# Sesión de Claude: detección y autocuración — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el juez (`claude -p`) deje de fallar por sesión caducada, que Aura lo detecte al abrir la sesión, y que cuando aun así falle la propia skill haga de juez en vez de devolver el video "con errores".

**Architecture:** (1) Un token de larga duración (`claude setup-token`) se guarda en `~/.videoqa/token` mediante un script que la persona ejecuta en Terminal; el motor lo inyecta como `CLAUDE_CODE_OAUTH_TOKEN` en cada `claude -p`. (2) Un comando `videoqa doctor` hace la comprobación real de criterio; el hook de SessionStart avisa en una línea. (3) `videoqa run --hasta-juez` prepara las entradas del juez y se detiene; `videoqa run --veredicto archivo.json` reanuda con un veredicto escrito por la skill `revisar` desde la propia sesión de Claude. (4) `videoqa run` sobre un video fuera de `01_Entrada` lo copia ahí primero, para que la prueba de instalación no se lleve el fixture del repo.

**Tech Stack:** Python 3.12, pytest, bash, Claude Code plugin (skills en Markdown, hook SessionStart).

**Spec:** Diagnóstico y diseño acordados en conversación el 2026-09-21 (este plan es la fuente). Hechos verificados: `claude setup-token` imprime el token y **no lo guarda**; `claude auth status` sale con código 1 sin sesión y no sabe del token en variable de entorno; `claude auth login` desde un Bash sin TTY abre el navegador pero se queda esperando un código pegado por stdin, así que no sirve lanzado por Claude; `claude -p` anidado dentro de Claude Code sí funciona.

## Global Constraints

- Idioma de todo texto visible por la persona: español informal (tú), sin jerga ("launchd", "token", "OAuth" no se dicen; se dice "sesión de Claude").
- Claude (la skill) **nunca lee, muestra ni escribe el token**. Solo el script en Terminal y el motor lo tocan.
- Los tests nunca tocan `~/.videoqa`: usan `VIDEOQA_HOME` (fixture autouse en `tests/conftest.py`). Los scripts bash deben honrar `VIDEOQA_HOME` por lo mismo.
- Ningún test nuevo requiere `claude`, `ffmpeg` real ni red: se falsea `subprocess.run` o se mete un `claude` falso en `PATH`.
- Toda skill nueva o modificada pasa `tests/unit/test_plugin_layout.py` (frontmatter sin `name`, `description` ≤ 200 caracteres, `allowed-tools` presente).
- Comandos del motor siempre como `uv run --project ~/videoqa videoqa …`.
- Commits pequeños, en español, con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` al final.
- Al terminar todo: `uv run pytest -q` en verde y versión del plugin subida a `1.2.0` en `plugins/aura/.claude-plugin/plugin.json` y `.claude-plugin/marketplace.json`.

---

### Task 1: El motor inyecta el token guardado en cada `claude -p`

**Files:**
- Modify: `videoqa/config.py` (añadir `token_path()` y `load_token()` junto a `videoqa_home()`)
- Modify: `videoqa/claude_runner.py:17-24` (`run_claude` construye `env`)
- Test: `tests/unit/test_config.py`, `tests/unit/test_claude_runner.py`

**Interfaces:**
- Produces: `videoqa.config.token_path() -> Path` (= `videoqa_home() / "token"`), `videoqa.config.load_token() -> str | None` (contenido sin espacios; `None` si no existe o está vacío), `videoqa.claude_runner.claude_env() -> dict[str, str]` (copia de `os.environ` con `CLAUDE_CODE_OAUTH_TOKEN` puesto si hay token).

- [ ] **Step 1: Tests de config**

Añadir a `tests/unit/test_config.py`:

```python
from videoqa.config import load_token, token_path, videoqa_home


def test_token_path_vive_en_videoqa_home():
    assert token_path() == videoqa_home() / "token"


def test_load_token_none_si_no_existe():
    assert load_token() is None


def test_load_token_recorta_espacios_y_saltos():
    token_path().parent.mkdir(parents=True, exist_ok=True)
    token_path().write_text("  sk-ant-oat01-abc\n")
    assert load_token() == "sk-ant-oat01-abc"


def test_load_token_vacio_cuenta_como_ausente():
    token_path().parent.mkdir(parents=True, exist_ok=True)
    token_path().write_text("\n")
    assert load_token() is None
```

- [ ] **Step 2: Correr y ver fallar**

Run: `uv run pytest tests/unit/test_config.py -q -k token`
Expected: FAIL con `ImportError: cannot import name 'load_token'`.

- [ ] **Step 3: Implementar en `videoqa/config.py`** (debajo de `default_config_path`)

```python
def token_path() -> Path:
    """Token de larga duración de Claude (lo escribe instalar/guardar-token.command)."""
    return videoqa_home() / "token"


def load_token() -> str | None:
    try:
        token = token_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return token or None
```

- [ ] **Step 4: Tests del runner**

Añadir a `tests/unit/test_claude_runner.py`:

```python
from videoqa.config import token_path
from videoqa.claude_runner import claude_env, run_claude


def test_claude_env_sin_token_no_toca_la_variable(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in claude_env()


def test_claude_env_con_token_lo_inyecta(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    token_path().parent.mkdir(parents=True, exist_ok=True)
    token_path().write_text("sk-ant-oat01-xyz\n")
    env = claude_env()
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-xyz"
    assert env["PATH"]  # conserva el entorno del proceso


def test_run_claude_pasa_el_env_al_subproceso(monkeypatch, tmp_path):
    token_path().parent.mkdir(parents=True, exist_ok=True)
    token_path().write_text("sk-ant-oat01-xyz")
    visto = {}

    def fake_run(cmd, **kw):
        visto.update(kw)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"is_error": False, "result": "ok"}), stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run_claude("hola", tmp_path) == "ok"
    assert visto["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-xyz"
```

- [ ] **Step 5: Correr y ver fallar**

Run: `uv run pytest tests/unit/test_claude_runner.py -q`
Expected: FAIL con `ImportError: cannot import name 'claude_env'`.

- [ ] **Step 6: Implementar en `videoqa/claude_runner.py`**

```python
import os
from videoqa.config import load_token


def claude_env() -> dict[str, str]:
    """Entorno para `claude -p`: el del proceso, más el token guardado si lo hay.

    `claude` lee CLAUDE_CODE_OAUTH_TOKEN; con eso el juez funciona aunque la
    sesión interactiva del CLI haya caducado (o nunca se haya iniciado).
    """
    env = dict(os.environ)
    token = load_token()
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    return env
```

y en `run_claude`, la llamada pasa a:

```python
proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=cwd, timeout=timeout, env=claude_env())
```

- [ ] **Step 7: Correr toda la suite**

Run: `uv run pytest -q`
Expected: todo en verde.

- [ ] **Step 8: Commit**

```bash
git add videoqa/config.py videoqa/claude_runner.py tests/unit/test_config.py tests/unit/test_claude_runner.py
git commit -m "feat: el juez usa el token guardado en ~/.videoqa/token"
```

---

### Task 2: `videoqa doctor` — comprobación real de que Claude puede dar criterio

**Files:**
- Modify: `videoqa/cli.py` (nuevo `cmd_doctor`, subparser `doctor`)
- Test: `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: `run_claude`, `load_token`, `token_path` (Task 1).
- Produces: comando `videoqa doctor`. Imprime **una línea** y sale con 0 (criterio OK) o 1. Escribe `videoqa_home()/doctor.json` con `{"ok": bool, "motivo": str, "at": "<iso>"}` para que el hook lo lea sin lanzar `claude`. Líneas exactas:
  - `CRITERIO OK · sesión guardada` (había token y `claude -p` respondió)
  - `CRITERIO OK · sesión del CLI` (sin token, pero `claude -p` respondió)
  - `CRITERIO SIN SESIÓN · <motivo>` (exit 1). Motivos: `no encuentro el programa claude`, `la sesión caducó o no hay token guardado`.

- [ ] **Step 1: Tests**

Añadir a `tests/unit/test_cli.py`:

```python
import json

from videoqa import cli
from videoqa.claude_runner import ClaudeError
from videoqa.config import token_path, videoqa_home


def test_doctor_ok_con_token(monkeypatch, capsys):
    token_path().parent.mkdir(parents=True, exist_ok=True)
    token_path().write_text("sk-ant-oat01-x")
    monkeypatch.setattr(cli, "run_claude", lambda *a, **k: "ok")
    assert cli.main(["doctor"]) == 0
    assert capsys.readouterr().out.strip() == "CRITERIO OK · sesión guardada"
    assert json.loads((videoqa_home() / "doctor.json").read_text())["ok"] is True


def test_doctor_ok_sin_token(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_claude", lambda *a, **k: "ok")
    assert cli.main(["doctor"]) == 0
    assert capsys.readouterr().out.strip() == "CRITERIO OK · sesión del CLI"


def test_doctor_falla_si_claude_no_responde(monkeypatch, capsys):
    def boom(*a, **k):
        raise ClaudeError("claude -p salió con 1: Failed to authenticate: OAuth session expired")
    monkeypatch.setattr(cli, "run_claude", boom)
    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out.strip()
    assert out.startswith("CRITERIO SIN SESIÓN · la sesión caducó o no hay token guardado")
    assert json.loads((videoqa_home() / "doctor.json").read_text())["ok"] is False


def test_doctor_falla_si_no_hay_binario(monkeypatch, capsys):
    def boom(*a, **k):
        raise ClaudeError("no se pudo ejecutar claude: [Errno 2] No such file")
    monkeypatch.setattr(cli, "run_claude", boom)
    assert cli.main(["doctor"]) == 1
    assert "no encuentro el programa claude" in capsys.readouterr().out
```

- [ ] **Step 2: Correr y ver fallar**

Run: `uv run pytest tests/unit/test_cli.py -q -k doctor`
Expected: FAIL (`argparse` no conoce `doctor`, SystemExit 2).

- [ ] **Step 3: Implementar en `videoqa/cli.py`**

```python
import json
from datetime import datetime
from videoqa.claude_runner import ClaudeError, Runner, run_claude
from videoqa.config import ..., load_token, videoqa_home


def cmd_doctor(args) -> int:
    """Una línea: ¿puede Claude dar criterio ahora mismo? Deja el resultado en doctor.json."""
    con_token = load_token() is not None
    claude_bin = "claude"
    cfg = Path(os.environ.get("VIDEOQA_CONFIG", default_config_path()))
    if cfg.exists():
        try:
            claude_bin = load_settings(cfg).claude_bin
        except Exception:  # noqa: BLE001 — config rota: se prueba con el binario por defecto
            pass
    ok, motivo = True, "sesión guardada" if con_token else "sesión del CLI"
    try:
        run_claude("Responde solo con la palabra: ok", videoqa_home(), claude_bin=claude_bin, timeout=90, allowed_tools=())
    except ClaudeError as e:
        ok = False
        motivo = "no encuentro el programa claude" if "no se pudo ejecutar" in str(e) else "la sesión caducó o no hay token guardado"
    videoqa_home().mkdir(parents=True, exist_ok=True)
    (videoqa_home() / "doctor.json").write_text(json.dumps(
        {"ok": ok, "motivo": motivo, "at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False))
    print(f"CRITERIO {'OK' if ok else 'SIN SESIÓN'} · {motivo}")
    return 0 if ok else 1
```

En `main`: `p = sub.add_parser("doctor", help="comprobar que Claude puede dar criterio"); p.set_defaults(fn=cmd_doctor)`.

Nota: `run_claude` con `allowed_tools=()` produce `--allowedTools ""`; cambiar `run_claude` para omitir el flag cuando la tupla está vacía:

```python
cmd = [claude_bin, "-p", "--output-format", "json"]
if allowed_tools:
    cmd += ["--allowedTools", ",".join(allowed_tools)]
```

y añadir en `tests/unit/test_claude_runner.py`:

```python
def test_run_claude_sin_herramientas_omite_el_flag(monkeypatch, tmp_path):
    visto = {}
    def fake_run(cmd, **kw):
        visto["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"is_error": False, "result": "ok"}), stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    run_claude("hola", tmp_path, allowed_tools=())
    assert "--allowedTools" not in visto["cmd"]
```

- [ ] **Step 4: Correr**

Run: `uv run pytest tests/unit/test_cli.py tests/unit/test_claude_runner.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add videoqa/cli.py videoqa/claude_runner.py tests/unit/test_cli.py tests/unit/test_claude_runner.py
git commit -m "feat: videoqa doctor comprueba de verdad que Claude puede dar criterio"
```

---

### Task 3: Script `guardar-token.command` (lo ejecuta la persona en Terminal)

**Files:**
- Create: `instalar/guardar-token.command` (ejecutable, `chmod +x`)
- Modify: `tests/unit/test_installer_syntax.py` (añadir el script a `SCRIPTS`)
- Test: `tests/unit/test_guardar_token.py`

**Interfaces:**
- Consumes: `videoqa doctor` (Task 2).
- Produces: fichero `${VIDEOQA_HOME:-$HOME/.videoqa}/token` con permisos `600`. Texto en español. Sale con 0 si guardó y `doctor` dio OK.

- [ ] **Step 1: Test funcional con un `claude` falso**

`tests/unit/test_guardar_token.py`:

```python
"""El script corre `claude setup-token` y guarda el token. Se prueba con un
`claude` falso en PATH y un `uv` falso para no depender de nada instalado."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "instalar" / "guardar-token.command"


def _bin_falso(tmp_path: Path, salida_setup_token: str, doctor_exit: int = 0) -> Path:
    b = tmp_path / "bin"
    b.mkdir()
    (b / "claude").write_text(f"#!/bin/bash\nif [ \"$1\" = setup-token ]; then printf '%s\\n' \"$SALIDA\"; fi\n")
    (b / "uv").write_text(f"#!/bin/bash\necho 'CRITERIO OK · sesión guardada'\nexit {doctor_exit}\n")
    for f in ("claude", "uv"):
        (b / f).chmod((b / f).stat().st_mode | stat.S_IEXEC)
    os.environ["SALIDA"] = salida_setup_token
    return b


def _run(tmp_path: Path, salida: str, stdin: str = "", doctor_exit: int = 0):
    b = _bin_falso(tmp_path, salida, doctor_exit)
    env = {**os.environ, "PATH": f"{b}:{os.environ['PATH']}", "VIDEOQA_HOME": str(tmp_path / "home"),
           "HOME": str(tmp_path), "SALIDA": salida, "GUARDAR_TOKEN_SIN_PAUSA": "1"}
    return subprocess.run(["bash", str(SCRIPT)], input=stdin, capture_output=True, text=True, env=env)


def test_guarda_el_token_de_la_salida(tmp_path):
    res = _run(tmp_path, "Bla bla\nsk-ant-oat01-ABCdef_123-xyz\nListo")
    assert res.returncode == 0, res.stdout + res.stderr
    tok = tmp_path / "home" / "token"
    assert tok.read_text() == "sk-ant-oat01-ABCdef_123-xyz\n"
    assert stat.S_IMODE(tok.stat().st_mode) == 0o600
    assert "guardada" in res.stdout.lower()


def test_si_no_hay_token_en_la_salida_lo_pide(tmp_path):
    res = _run(tmp_path, "no salio nada", stdin="sk-ant-oat01-pegado\n")
    assert res.returncode == 0, res.stdout + res.stderr
    assert (tmp_path / "home" / "token").read_text() == "sk-ant-oat01-pegado\n"


def test_sin_token_ni_pegado_falla_claro(tmp_path):
    res = _run(tmp_path, "nada", stdin="\n")
    assert res.returncode == 1
    assert "no se guardó" in res.stdout.lower()
    assert not (tmp_path / "home" / "token").exists()


def test_es_ejecutable():
    assert SCRIPT.stat().st_mode & 0o111
```

- [ ] **Step 2: Correr y ver fallar**

Run: `uv run pytest tests/unit/test_guardar_token.py -q`
Expected: FAIL (`No such file`).

- [ ] **Step 3: Escribir `instalar/guardar-token.command`**

```bash
#!/usr/bin/env bash
#
# Deja guardada la sesión de Claude para que VideoQA revise videos sin que la
# sesión caduque. Lo ejecuta la persona en la Terminal (doble clic o `open`).
# Pide autorizar en el navegador una vez. Claude (la app) nunca ve el token.
#
# Variables para tests: VIDEOQA_HOME (dónde guardar), GUARDAR_TOKEN_SIN_PAUSA=1
# (no esperar Enter al final).
set -u

HOME_VQA="${VIDEOQA_HOME:-$HOME/.videoqa}"
TOKEN_FILE="$HOME_VQA/token"
PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

pausa() {
  if [ -z "${GUARDAR_TOKEN_SIN_PAUSA:-}" ]; then
    echo
    read -r -p "Pulsa Enter para cerrar esta ventana." _
  fi
}

echo "═══════════════════════════════════════════════"
echo "  VideoQA · guardar la sesión de Claude"
echo "═══════════════════════════════════════════════"
echo
if ! command -v claude >/dev/null 2>&1; then
  echo "No encuentro el programa 'claude' en esta Mac."
  echo "Vuelve a Claude y escribe /aura:instalar para que lo instale."
  pausa; exit 1
fi

echo "Se va a abrir el navegador. Autoriza con tu cuenta de Claude y,"
echo "si te pide pegar un código aquí, pégalo y pulsa Enter."
echo

SALIDA_TMP="$(mktemp)"
trap 'rm -f "$SALIDA_TMP"' EXIT
# stdin sigue siendo la Terminal, así setup-token puede pedir el código.
claude setup-token 2>&1 | tee "$SALIDA_TMP"
TOKEN="$(grep -oE 'sk-ant-oat01-[A-Za-z0-9_-]+' "$SALIDA_TMP" | tail -1)"

if [ -z "$TOKEN" ]; then
  echo
  echo "No vi el token en la pantalla. Si claude lo mostró, cópialo y pégalo aquí"
  echo "(no se verá mientras lo pegas). Si no, pulsa Enter para salir."
  read -r -s -p "> " TOKEN
  echo
  TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"
fi

if [ -z "$TOKEN" ]; then
  echo "No se guardó ninguna sesión. Vuelve a Claude y dile «arregla la sesión» para intentarlo otra vez."
  pausa; exit 1
fi

mkdir -p "$HOME_VQA"
umask 077
printf '%s\n' "$TOKEN" > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE"
echo
echo "✅ Sesión guardada. Comprobando que Claude responde…"
if command -v uv >/dev/null 2>&1 && [ -d "$HOME/videoqa" ]; then
  uv run --project "$HOME/videoqa" videoqa doctor || { echo "La sesión quedó guardada pero Claude no respondió. Vuelve a Claude y dile «arregla la sesión»."; pausa; exit 1; }
fi
echo
echo "Listo. Ya puedes cerrar esta ventana y volver a Claude."
pausa
exit 0
```

`chmod +x instalar/guardar-token.command`.

Detalle del test 2: el `uv` falso vive en `$PATH` y `$HOME/videoqa` no existe en el test, así que la rama de `doctor` no corre. Para que sí corra en `test_guarda_el_token_de_la_salida`, crear `tmp_path / "videoqa"` en `_run` (`(tmp_path / "videoqa").mkdir(exist_ok=True)`) — hacerlo, y comprobar que `CRITERIO OK` aparece en `res.stdout`.

- [ ] **Step 4: Añadir a `tests/unit/test_installer_syntax.py`**

```python
    ROOT / "instalar" / "guardar-token.command",
```

- [ ] **Step 5: Correr**

Run: `uv run pytest tests/unit/test_guardar_token.py tests/unit/test_installer_syntax.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add instalar/guardar-token.command tests/unit/test_guardar_token.py tests/unit/test_installer_syntax.py
git commit -m "feat: guardar-token.command deja la sesión de Claude guardada desde la Terminal"
```

---

### Task 4: El hook de SessionStart avisa de la sesión caducada y cuenta solo videos

**Files:**
- Modify: `plugins/aura/scripts/check-engine.sh`
- Test: `tests/unit/test_check_engine.py`

**Interfaces:**
- Consumes: `videoqa_home()/token`, `videoqa_home()/doctor.json` (Task 2). El hook **no** lanza `claude -p` (tiene que ser instantáneo); lanza `claude auth status` solo si no hay token.
- Produces: línea `Aura: motor OK · config OK · <cola> · <auto> · <sesión>` donde `<sesión>` es una de:
  - `sesión OK` (hay token y `doctor.json` no dice `ok:false` más reciente que el token; o no hay token pero `claude auth status` sale 0)
  - `⚠️ sesión de Claude caducada → dime «arregla la sesión»`

Reglas de decisión, en orden:
1. Si `doctor.json` existe, tiene `"ok": false` y es más nuevo que `token` (o no hay token) → caducada.
2. Si existe `token` → OK.
3. Si `claude auth status >/dev/null 2>&1` sale 0 → OK; si no → caducada.

Cola: contar solo ficheros con extensión `.mp4`, `.mov`, `.m4v` (mayúsculas también), ignorando los que empiezan por `.`.

- [ ] **Step 1: Test**

`tests/unit/test_check_engine.py`:

```python
"""El hook saluda con una línea de estado. Se ejecuta con HOME/VIDEOQA_HOME
falsos y un `claude`/`launchctl` falsos en PATH."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "plugins" / "aura" / "scripts" / "check-engine.sh"


def _entorno(tmp_path: Path, auth_exit: int = 1) -> dict:
    b = tmp_path / "bin"
    b.mkdir(exist_ok=True)
    (b / "claude").write_text(f"#!/bin/bash\nexit {auth_exit}\n")
    (b / "launchctl").write_text("#!/bin/bash\nexit 1\n")
    for f in ("claude", "launchctl"):
        (b / f).chmod((b / f).stat().st_mode | stat.S_IEXEC)
    home = tmp_path / "home"
    (home / "videoqa").mkdir(parents=True)
    vq = home / ".videoqa"
    vq.mkdir()
    drive = tmp_path / "drive"
    (drive / "01_Entrada").mkdir(parents=True)
    (vq / "config.yaml").write_text(f"drive_root: {drive}\n")
    return {**os.environ, "HOME": str(home), "PATH": f"{b}:/usr/bin:/bin", "VIDEOQA_HOME": str(vq)}


def _run(env: dict) -> str:
    res = subprocess.run(["bash", str(HOOK)], capture_output=True, text=True, env=env)
    assert res.returncode == 0
    return res.stdout.strip()


def test_sin_token_y_sin_sesion_avisa(tmp_path):
    out = _run(_entorno(tmp_path, auth_exit=1))
    assert "sesión de Claude caducada" in out and "arregla la sesión" in out


def test_sin_token_con_sesion_del_cli_ok(tmp_path):
    out = _run(_entorno(tmp_path, auth_exit=0))
    assert "sesión OK" in out


def test_con_token_ok_sin_lanzar_claude(tmp_path):
    env = _entorno(tmp_path, auth_exit=1)
    (Path(env["VIDEOQA_HOME"]) / "token").write_text("sk-ant-oat01-x\n")
    assert "sesión OK" in _run(env)


def test_doctor_reciente_en_falso_gana_al_token(tmp_path):
    env = _entorno(tmp_path)
    vq = Path(env["VIDEOQA_HOME"])
    (vq / "token").write_text("sk-ant-oat01-x\n")
    viejo = time.time() - 3600
    os.utime(vq / "token", (viejo, viejo))
    (vq / "doctor.json").write_text(json.dumps({"ok": False, "motivo": "caducó", "at": "x"}))
    assert "caducada" in _run(env)


def test_doctor_viejo_en_falso_no_gana_a_un_token_nuevo(tmp_path):
    env = _entorno(tmp_path)
    vq = Path(env["VIDEOQA_HOME"])
    (vq / "doctor.json").write_text(json.dumps({"ok": False, "motivo": "caducó", "at": "x"}))
    viejo = time.time() - 3600
    os.utime(vq / "doctor.json", (viejo, viejo))
    (vq / "token").write_text("sk-ant-oat01-x\n")
    assert "sesión OK" in _run(env)


def test_cuenta_solo_videos(tmp_path):
    env = _entorno(tmp_path, auth_exit=0)
    entrada = tmp_path / "drive" / "01_Entrada"
    (entrada / ".DS_Store").write_text("")
    (entrada / "notas.txt").write_text("")
    (entrada / "a.mp4").write_text("")
    (entrada / "b.MOV").write_text("")
    assert "2 videos pendientes" in _run(env)


def test_sin_videos(tmp_path):
    assert "sin videos pendientes" in _run(_entorno(tmp_path, auth_exit=0))
```

- [ ] **Step 2: Correr y ver fallar**

Run: `uv run pytest tests/unit/test_check_engine.py -q`
Expected: FAIL en los tests de sesión (la línea no lleva nada de sesión) y en `test_cuenta_solo_videos` (cuenta 4).

- [ ] **Step 3: Modificar `check-engine.sh`**

Cambiar `CONFIG="$HOME/.videoqa/config.yaml"` por:

```bash
HOME_VQA="${VIDEOQA_HOME:-$HOME/.videoqa}"
CONFIG="$HOME_VQA/config.yaml"
TOKEN="$HOME_VQA/token"
DOCTOR="$HOME_VQA/doctor.json"
```

Sustituir el recuento por:

```bash
PEND="?"
if [ -n "$DRIVE" ] && [ -d "$DRIVE/01_Entrada" ]; then
  PEND="$(find "$DRIVE/01_Entrada" -maxdepth 1 -type f ! -name '.*' \
            \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.m4v' \) 2>/dev/null | wc -l | tr -d ' ')"
fi
```

Añadir antes del `echo` final:

```bash
SESION="sesión OK"
CADUCADA="⚠️ sesión de Claude caducada → dime «arregla la sesión»"
if [ -f "$DOCTOR" ] && grep -q '"ok": *false' "$DOCTOR" && { [ ! -f "$TOKEN" ] || [ "$DOCTOR" -nt "$TOKEN" ]; }; then
  SESION="$CADUCADA"
elif [ -f "$TOKEN" ]; then
  SESION="sesión OK"
elif claude auth status >/dev/null 2>&1; then
  SESION="sesión OK"
else
  SESION="$CADUCADA"
fi

echo "Aura: motor OK · config OK · $COLA · $AUTO · $SESION"
```

(`PATH` del hook: añadir al principio `PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"` para encontrar `claude` cuando la app arranca con un PATH corto.)

- [ ] **Step 4: Correr**

Run: `uv run pytest tests/unit/test_check_engine.py tests/unit/test_plugin_layout.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/aura/scripts/check-engine.sh tests/unit/test_check_engine.py
git commit -m "feat(aura): el saludo avisa de la sesión caducada y cuenta solo videos"
```

---

### Task 5: `videoqa run` copia a `01_Entrada` los videos que vienen de fuera

**Files:**
- Modify: `videoqa/cli.py` (`cmd_run`)
- Test: `tests/unit/test_cli.py`

**Interfaces:**
- Produces: `cmd_run` procesa siempre un fichero dentro de `settings.entrada`. Si el argumento está fuera, lo copia con `shutil.copy2` a `settings.entrada / nombre` (sobrescribe si ya hay uno con ese nombre) e imprime `Copiado a 01_Entrada: <nombre>`. El original **no se toca**.

- [ ] **Step 1: Test** (sigue el patrón de `test_run_uses_injected_process`, que inyecta `cli.process_video`)

```python
def test_run_copia_a_entrada_si_viene_de_fuera(tmp_path, monkeypatch, capsys):
    drive = tmp_path / "drive"
    main(["init", "--drive-root", str(drive)])
    fuera = tmp_path / "otra" / "clip.mp4"
    fuera.parent.mkdir()
    fuera.write_bytes(b"x")
    visto = {}

    def fake_process(video, settings, rules, runner, sheet=None):
        visto["video"] = video
        return Result("approved", [], drive / "03_Aprobado" / "clip")
    monkeypatch.setattr(cli, "process_video", fake_process)
    assert main(["run", str(fuera)]) == 0
    assert visto["video"] == drive / "01_Entrada" / "clip.mp4"
    assert fuera.exists(), "el original se conserva"
    assert "Copiado a 01_Entrada" in capsys.readouterr().out


def test_run_no_copia_si_ya_esta_en_entrada(tmp_path, monkeypatch):
    drive = tmp_path / "drive"
    main(["init", "--drive-root", str(drive)])
    dentro = drive / "01_Entrada" / "clip.mp4"
    dentro.write_bytes(b"x")
    visto = {}

    def fake_process(video, settings, rules, runner, sheet=None):
        visto["video"] = video
        return Result("approved", [], drive / "03_Aprobado" / "clip")
    monkeypatch.setattr(cli, "process_video", fake_process)
    main(["run", str(dentro)])
    assert visto["video"] == dentro
```

(Importar `Result` de `videoqa.pipeline` y `cli` como en los tests existentes del fichero.)

- [ ] **Step 2: Correr y ver fallar**

Run: `uv run pytest tests/unit/test_cli.py -q -k copia`
Expected: FAIL (`visto["video"]` es la ruta de fuera).

- [ ] **Step 3: Implementar en `cmd_run`**

```python
import shutil

def cmd_run(args) -> int:
    settings, rules = load_settings(), load_rules()
    video = Path(args.video).expanduser().resolve()
    entrada = settings.entrada.resolve()
    if video.parent != entrada:
        # Un video de fuera (p. ej. el de prueba que viene con el motor) se copia:
        # deliver() MUEVE el archivo, y mover el fixture del repo lo deja sucio.
        entrada.mkdir(parents=True, exist_ok=True)
        destino = entrada / video.name
        shutil.copy2(video, destino)
        print(f"Copiado a 01_Entrada: {video.name}")
        video = destino
    res = process_video(video, settings, rules, make_runner(settings, rules), sheet=make_sheet(settings))
    ...
```

Cuidado con `test_run_returns_1_on_error`: pasa `tmp_path / "x.mp4"` que no existe; `shutil.copy2` lanzaría `FileNotFoundError`. Solución: copiar solo si `video.exists()`; si no existe, dejar que `process_video` (o el fake) falle como antes.

- [ ] **Step 4: Correr**

Run: `uv run pytest tests/unit/test_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add videoqa/cli.py tests/unit/test_cli.py
git commit -m "fix: videoqa run copia a 01_Entrada los videos de fuera en vez de moverlos"
```

---

### Task 6: `run --hasta-juez` y `run --veredicto` (juez desde la propia sesión)

**Files:**
- Modify: `videoqa/judge.py` (extraer `prepare_judge`, `run_judge` la usa)
- Modify: `videoqa/pipeline.py` (`process_video(..., modo="completo", veredicto_text=None)`)
- Modify: `videoqa/cli.py` (flags de `run`)
- Modify: `videoqa/report.py:23` (etiqueta de `error`) y `tests/unit/test_report.py:38`
- Test: `tests/unit/test_judge.py`, `tests/integration/test_pipeline.py`, `tests/unit/test_cli.py`

**Interfaces:**
- Produces:
  - `videoqa.judge.prepare_judge(job, brand, glossary_text, transcript, ocr, technical, code_findings, frames, rules, skill_path=SKILL_PATH, duration=None) -> str`: escribe `judge_input/`, `claude_frames/` y `judge_prompt.md` en el job dir; devuelve el prompt. Lanza `JudgeError` si falla.
  - `run_judge(...)` mantiene su firma y llama a `prepare_judge`.
  - `process_video(video, settings, rules, runner, sheet=None, modo="completo", veredicto_text=None)`:
    - `modo="preparar"`: tras extracción y checks, llama a `prepare_judge`, **no** entrega el video, y devuelve `Result("pending", code_findings, None, None)`; el job dir queda en `job.dir`.
    - `veredicto_text` no `None`: se usa como respuesta del juez en lugar de `runner` (runner interno `lambda p, cwd: veredicto_text`). Si no parsea, se degrada igual que hoy (video a `02_Con_errores` con "criterio pendiente").
  - CLI: `videoqa run VIDEO --hasta-juez` imprime `JUEZ_PENDIENTE <job_dir>` y sale 0. `videoqa run VIDEO --veredicto RUTA.json` lee el fichero como texto y lo pasa en `veredicto_text`. Los dos flags son excluyentes (`argparse` `add_mutually_exclusive_group`).
  - `report.STATUS["error"] = ("⏸️", "PENDIENTE (sin criterio de Claude)")`.

- [ ] **Step 1: Tests del juez**

En `tests/unit/test_judge.py` (reutilizar los helpers que ya existen ahí para `job`, `brand`, `frames`, etc.; mirar `test_run_judge_happy_path` y copiar su preparación):

```python
def test_prepare_judge_escribe_prompt_y_entradas(tmp_path):
    job, brand, transcript, ocr, technical, frames, rules = _preparar(tmp_path)  # el helper que usen los tests vecinos
    prompt = prepare_judge(job, brand, "", transcript, ocr, technical, [], frames, rules, skill_path=SKILL, duration=6.0)
    assert (job.dir / "judge_prompt.md").read_text() == prompt
    assert (job.dir / "judge_input" / "transcript.json").exists()
    assert "Duración del video: 6.0 s" in prompt
```

- [ ] **Step 2: Tests de pipeline** (en `tests/integration/test_pipeline.py`, siguiendo `test_judge_failure_yields_error_status_in_con_errores` para la preparación del drive/settings y el monkeypatch de `transcribe`)

```python
def test_modo_preparar_deja_el_video_en_entrada_y_escribe_el_prompt(tmp_path, fixture_videos, monkeypatch):
    settings, rules, video = _setup(tmp_path, fixture_videos, monkeypatch, "spelling_color")  # helper local del fichero
    def juez_no_debe_llamarse(prompt, cwd):
        raise AssertionError("en modo preparar no se llama al juez")
    res = process_video(video, settings, rules, juez_no_debe_llamarse, modo="preparar")
    assert res.status == "pending" and res.dest is None
    assert video.exists()
    job_dir = settings.jobs_dir / video.stem
    assert (job_dir / "judge_prompt.md").exists()
    assert (job_dir / "judge_input" / "findings_code.json").exists()


def test_veredicto_externo_sustituye_al_juez(tmp_path, fixture_videos, monkeypatch):
    settings, rules, video = _setup(tmp_path, fixture_videos, monkeypatch, "spelling_color")
    veredicto = json.dumps({"findings": [], "guion_real_md": "# Guion\n\nHola.",
                            "confirmed_code_findings": [], "dismissed_code_findings": []})
    def juez_no_debe_llamarse(prompt, cwd):
        raise AssertionError("con veredicto externo no se llama al juez")
    res = process_video(video, settings, rules, juez_no_debe_llamarse, veredicto_text=veredicto)
    assert res.status in ("approved", "rejected")
    assert res.dest is not None and (res.dest / "guion_real.md").read_text().startswith("# Guion")
```

Si el fichero no tiene un helper `_setup`, crear uno mínimo a partir de la preparación repetida en los tests existentes (init de carpetas + `Settings` + `load_rules()` + monkeypatch de `pl.transcribe`), sin cambiar los tests que ya hay.

- [ ] **Step 3: Tests de CLI**

```python
def test_run_hasta_juez_imprime_el_job_dir(tmp_path, monkeypatch, capsys):
    drive = tmp_path / "drive"
    main(["init", "--drive-root", str(drive)])
    video = drive / "01_Entrada" / "clip.mp4"
    video.write_bytes(b"x")
    visto = {}

    def fake_process(v, settings, rules, runner, sheet=None, modo="completo", veredicto_text=None):
        visto["modo"] = modo
        return Result("pending", [], None)
    monkeypatch.setattr(cli, "process_video", fake_process)
    assert main(["run", str(video), "--hasta-juez"]) == 0
    assert visto["modo"] == "preparar"
    assert capsys.readouterr().out.strip().startswith("JUEZ_PENDIENTE ")


def test_run_con_veredicto_lo_pasa_como_texto(tmp_path, monkeypatch):
    drive = tmp_path / "drive"
    main(["init", "--drive-root", str(drive)])
    video = drive / "01_Entrada" / "clip.mp4"
    video.write_bytes(b"x")
    ver = tmp_path / "veredicto.json"
    ver.write_text('{"findings": []}')
    visto = {}

    def fake_process(v, settings, rules, runner, sheet=None, modo="completo", veredicto_text=None):
        visto["texto"] = veredicto_text
        return Result("approved", [], drive / "03_Aprobado" / "clip")
    monkeypatch.setattr(cli, "process_video", fake_process)
    assert main(["run", str(video), "--veredicto", str(ver)]) == 0
    assert visto["texto"] == '{"findings": []}'
```

Los fakes existentes de `process_video` en `test_cli.py` tienen la firma vieja; `cmd_run` va a pasar `modo=` y `veredicto_text=` siempre, así que **actualizar esos fakes** para aceptar `**kw`.

- [ ] **Step 4: Test del reporte** — en `tests/unit/test_report.py:38` cambiar la aserción a:

```python
    assert md.startswith("# ⏸️ x.mp4 — PENDIENTE (sin criterio de Claude)")
```

- [ ] **Step 5: Correr y ver fallar**

Run: `uv run pytest tests/unit/test_judge.py tests/integration/test_pipeline.py tests/unit/test_cli.py tests/unit/test_report.py -q`
Expected: FAIL (imports y flags inexistentes; el reporte aún dice ERROR).

- [ ] **Step 6: Implementar `prepare_judge` en `videoqa/judge.py`**

```python
def prepare_judge(job: Job, brand: dict, glossary_text: str, transcript: dict, ocr: dict, technical: dict,
                  code_findings: list[Finding], frames: list[dict], rules: dict,
                  skill_path: Path = SKILL_PATH, duration: float | None = None) -> str:
    """Deja en el job dir todo lo que el juez necesita y devuelve el prompt.

    Lo usa `run_judge` (juez por `claude -p`) y también `videoqa run --hasta-juez`,
    donde el juez es la propia sesión de Claude que lee `judge_prompt.md`.
    """
    try:
        manifest = prepare_inputs(job, brand, glossary_text, transcript, ocr, technical, code_findings, frames, rules)
        skill_text = skill_path.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001 — cualquier fallo aquí es fatal para el juez
        raise JudgeError(f"no se pudieron preparar las entradas del juez: {e}") from e
    if duration is None:
        duration = max([f["t"] for f in frames], default=0.0)
    prompt = build_prompt(skill_text, manifest, duration)
    job.path("judge_prompt.md").write_text(prompt, encoding="utf-8")
    job.path("judge_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return prompt
```

`run_judge` pasa a: `base_prompt = prepare_judge(...)` y `manifest = json.loads(job.path("judge_manifest.json").read_text())` (o hacer que `prepare_judge` devuelva `(prompt, manifest)` y que el test del Step 1 desempaquete; elegir una y ser consistente). Quitar el bloque `try/except` y el cálculo de `duration` duplicados de `run_judge`.

- [ ] **Step 7: Implementar en `videoqa/pipeline.py`**

Firma: `def process_video(video, settings, rules, runner, sheet=None, modo: str = "completo", veredicto_text: str | None = None) -> Result:`

Justo antes de la "Etapa 2" (después de `save_findings(...)` y su `except`):

```python
    if modo == "preparar":
        try:
            prepare_judge(job, brand, glossary_text, transcript, ocr, technical, code_findings,
                          frames["frames"], rules, duration=float(p["duration"]))
        except JudgeError as e:
            log.error("[%s] %s", job.name, e)
            return Result("error", code_findings, None, str(e))
        log.info("[%s] entradas del juez listas en %s (esperando veredicto)", job.name, job.dir)
        return Result("pending", code_findings, None, None)

    if veredicto_text is not None:
        texto = veredicto_text
        runner = lambda prompt, cwd: texto  # noqa: E731 — el veredicto ya viene escrito
```

Importar `prepare_judge, JudgeError` de `videoqa.judge`.

- [ ] **Step 8: Implementar flags en `videoqa/cli.py`**

En `main`, en el parser de `run`:

```python
    g = p.add_mutually_exclusive_group()
    g.add_argument("--hasta-juez", action="store_true",
                   help="preparar las entradas del juez y parar (la sesión de Claude hace de juez)")
    g.add_argument("--veredicto", metavar="JSON", help="reanudar con un veredicto ya escrito")
```

En `cmd_run`, tras la copia a Entrada:

```python
    modo = "preparar" if getattr(args, "hasta_juez", False) else "completo"
    veredicto_text = Path(args.veredicto).expanduser().read_text(encoding="utf-8") if getattr(args, "veredicto", None) else None
    res = process_video(video, settings, rules, make_runner(settings, rules), sheet=make_sheet(settings),
                        modo=modo, veredicto_text=veredicto_text)
    if res.status == "pending":
        print(f"JUEZ_PENDIENTE {settings.jobs_dir / video.stem}")
        return 0
```

- [ ] **Step 9: Etiqueta del reporte** en `videoqa/report.py:23`:

```python
STATUS = {"approved": ("🟢", "APROBADO"), "rejected": ("🔴", "NO APROBADO"),
          "error": ("⏸️", "PENDIENTE (sin criterio de Claude)")}
```

Comprobar con `grep -rn "ERROR" tests/unit/test_report_html.py tests/integration` si algún otro test espera "ERROR" en el título y actualizarlo.

- [ ] **Step 10: Correr toda la suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add videoqa/judge.py videoqa/pipeline.py videoqa/cli.py videoqa/report.py tests/
git commit -m "feat: run --hasta-juez / --veredicto para que la sesión de Claude haga de juez"
```

---

### Task 7: Skills de Aura: `sesion` nueva, y `instalar`/`estado`/`revisar` usan lo nuevo

**Files:**
- Create: `plugins/aura/skills/sesion/SKILL.md`
- Modify: `plugins/aura/skills/instalar/SKILL.md` (Paso 8 y Paso 9, `allowed-tools`)
- Modify: `plugins/aura/skills/estado/SKILL.md` (sección "Comprobar que Claude puede dar criterio", `allowed-tools`)
- Modify: `plugins/aura/skills/revisar/SKILL.md` (nuevo Paso 4 "Si el video vuelve PENDIENTE", `allowed-tools`)
- Modify: `plugins/aura/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (versión `1.2.0`)
- Modify: `plugins/aura/README.md`, `LEEME.md` (fila de `/aura:sesion` en la tabla de comandos)
- Modify: `tests/unit/test_plugin_layout.py` (`SIDE_EFFECT_SKILLS` añade `"sesion"`; `test_hay_skills` exige `"sesion"`)
- Test: `tests/unit/test_plugin_layout.py`

**Interfaces:**
- Consumes: `guardar-token.command` (Task 3), `videoqa doctor` (Task 2), `run --hasta-juez` / `--veredicto` (Task 6), línea del hook (Task 4).

- [ ] **Step 1: Test** — en `tests/unit/test_plugin_layout.py`:

```python
SIDE_EFFECT_SKILLS = {"instalar", "ajustar", "activar-automatico", "actualizar", "sesion"}
```

y en `test_hay_skills`: `assert {"revisar", "estado", "sesion"} <= nombres`. Añadir además:

```python
def test_ninguna_skill_usa_claude_auth_status() -> None:
    # `claude auth status` no sabe del token guardado: siempre diría "caducada".
    for skill in skill_files():
        assert "claude auth status" not in skill.read_text(), f"{skill}: usa videoqa doctor"


def test_ninguna_skill_manda_ejecutar_setup_token_a_pelo() -> None:
    # setup-token imprime el token y NO lo guarda: solo vale a través del .command.
    for skill in skill_files():
        texto = skill.read_text()
        assert "claude setup-token" not in texto or "guardar-token.command" in texto, skill
```

- [ ] **Step 2: Correr y ver fallar**

Run: `uv run pytest tests/unit/test_plugin_layout.py -q`
Expected: FAIL (falta `sesion`; `estado` e `instalar` usan `claude auth status`).

- [ ] **Step 3: Crear `plugins/aura/skills/sesion/SKILL.md`**

```markdown
---
description: Arregla la sesión de Claude cuando caduca y los videos vuelven sin criterio. Úsalo cuando la persona diga "arregla la sesión", "sesión caducada" o "los videos salen pendientes".
disable-model-invocation: true
allowed-tools: Bash(uv run --project ~/videoqa videoqa:*) Bash(open:*) Bash(ls:*) Read
---

# Arreglar la sesión de Claude

Habla en español informal (tú), sin jerga: nunca digas "token", "OAuth" ni "login". Di "la sesión
de Claude". **Nunca leas ni muestres el contenido de `~/.videoqa/token`.**

El motor vive en `~/videoqa`; si no existe (`ls ~/videoqa`), dile "Todavía no está instalado:
escribe `/aura:instalar`" y termina.

## Paso 1 — Comprobar

```bash
uv run --project ~/videoqa videoqa doctor
```

- Si empieza por `CRITERIO OK`: "La sesión está bien, no hay nada que arreglar." Si te lo
  pidieron porque un video salió pendiente, ofrécele revisarlo otra vez ahora.
- Si dice `no encuentro el programa claude`: "Falta el programa de Claude en esta Mac. Escribe
  `/aura:instalar` y lo dejo listo." Termina.
- Si dice `la sesión caducó o no hay token guardado`: sigue al Paso 2.

## Paso 2 — Guardar la sesión (lo hace la persona, en la Terminal)

Dile, tal cual:

> Te abro una ventana de la Terminal. Se abre el navegador: autoriza con tu cuenta de Claude y, si
> te pide pegar un código en la Terminal, pégalo y pulsa Enter. Cuando la ventana diga "Listo",
> vuelve aquí y me dices.

```bash
open ~/videoqa/instalar/guardar-token.command
```

Espera a que te diga que terminó. Luego vuelve al Paso 1. Si a la segunda sigue fallando, dile
"No consigo dejar la sesión guardada; avisa a quien te pasó la herramienta" y termina.

## Paso 3 — Rematar

Si hay videos en `02_Con_errores` cuyo `reporte.md` empieza por `⏸️` (pendientes de criterio),
dile: "Los que quedaron pendientes los vuelvo a revisar cuando quieras: dime «revisa los
pendientes»". Si lo pide, para cada uno lanza `videoqa run` sobre el archivo que está dentro de
`02_Con_errores/<nombre>/` (el motor lo copia solo a `01_Entrada`) y explica el resultado como en
`/aura:revisar`.
```

- [ ] **Step 4: `instalar/SKILL.md`**

`allowed-tools`: añadir `Bash(curl:*)`, `Bash(rsync:*)`.

Sustituir el **Paso 8** entero por:

```markdown
## Paso 8 — Dejar la sesión de Claude guardada

La revisión de criterio la hace Claude y necesita una sesión que no caduque. Se guarda una vez y
ya. Dile, tal cual:

> Falta un paso que haces tú, porque es iniciar sesión y yo no manejo contraseñas. Te abro una
> ventana de la Terminal: se abre el navegador, autorizas con tu cuenta de Claude y, si te pide
> pegar un código en la Terminal, lo pegas y pulsas Enter. Cuando diga "Listo", vuelves aquí.

```bash
open ~/videoqa/instalar/guardar-token.command
```

Espera a que te diga que terminó y compruébalo:

```bash
uv run --project ~/videoqa videoqa doctor
```

Si empieza por `CRITERIO OK`, sigue. Si no, pídele que repita el paso una vez; si sigue fallando,
continúa igual y avísale: "La parte de criterio no va a funcionar hasta que la sesión quede
guardada; dime luego «arregla la sesión» y lo intentamos otra vez."
```

En el **Paso 9**, sustituir el bloque de resultados por:

```markdown
- 🔴 **NO APROBADO** — perfecto, todo funciona. Es el resultado esperado.
- ⏸️ **PENDIENTE (sin criterio de Claude)** — los checks automáticos van bien, pero Claude no pudo
  dar su criterio: es la sesión del Paso 8. Di "arregla la sesión" y vuelve a probar.
- 🟢 **APROBADO** — algo no está revisando. Mira `~/.videoqa/videoqa.log` y dile que te avise.
```

(El comando del Paso 9 no cambia: `videoqa run` ya copia el video de prueba a `01_Entrada` en vez de llevárselo.)

- [ ] **Step 5: `estado/SKILL.md`**

`allowed-tools`: `Bash(ls:*) Bash(tail:*) Bash(launchctl print:*) Bash(cat:*) Bash(uv run --project ~/videoqa videoqa doctor:*) Read`.

Sustituir la sección "Comprobar que Claude puede dar criterio" por:

```markdown
## Comprobar que Claude puede dar criterio

Cuando la sesión de Claude caduca, los videos vuelven con "⏸️ PENDIENTE (sin criterio de Claude)".
Compruébalo siempre:

```bash
uv run --project ~/videoqa videoqa doctor
```

Si no empieza por `CRITERIO OK`, díselo en una frase y dale la salida:

> La sesión de Claude caducó, por eso los últimos videos salen pendientes. Dime **"arregla la
> sesión"** y lo dejamos listo en un minuto.
```

- [ ] **Step 6: `revisar/SKILL.md`**

`allowed-tools`: `Bash(uv run --project ~/videoqa videoqa:*) Bash(open:*) Bash(ls:*) Read Write`.

Añadir, antes de "## Cómo explicar el resultado":

```markdown
## Paso 4 — Si un video vuelve ⏸️ PENDIENTE (sin criterio de Claude)

Eso significa que los checks automáticos pasaron pero el juez no pudo dar criterio. **No le digas
que el video "tiene errores"**: no se ha terminado de revisar. Haz tú de juez, sin pedir nada:

1. Vuelve a lanzar el video en modo "hasta el juez". El video ya está en `02_Con_errores/<nombre>/`;
   cópialo primero a `01_Entrada` (con `videoqa run` sobre esa ruta se copia solo):

```bash
uv run --project ~/videoqa videoqa run "<drive_root>/02_Con_errores/<nombre>/<archivo>" --hasta-juez
```

   La última línea es `JUEZ_PENDIENTE <carpeta>`.

2. Lee con Read `<carpeta>/judge_prompt.md` y síguelo al pie de la letra: te pide leer los
   archivos de `<carpeta>/judge_input/` y las fotos de `<carpeta>/claude_frames/` (las rutas del
   prompt son relativas a `<carpeta>`) y responder solo con un JSON.

3. Escribe ese JSON, y nada más, con Write en `<carpeta>/veredicto.json`.

4. Reanuda:

```bash
uv run --project ~/videoqa videoqa run "<drive_root>/01_Entrada/<archivo>" --veredicto "<carpeta>/veredicto.json"
```

   Y explica el resultado como siempre (Paso 3). Si vuelve a salir pendiente, es que el JSON no
   era válido: vuelve al punto 2 una sola vez.

5. Al final, avísale en una frase: "La sesión de Claude está caducada, por eso esta vez hice yo
   la revisión de criterio. Dime **"arregla la sesión"** cuando puedas y así lo automático vuelve
   a funcionar solo."
```

- [ ] **Step 7: Versión y documentación**

- `plugins/aura/.claude-plugin/plugin.json` y `.claude-plugin/marketplace.json`: `"version": "1.2.0"`.
- `plugins/aura/README.md` y `LEEME.md`: en la tabla de comandos, fila `| /aura:sesion | Arreglar la sesión de Claude cuando los videos salen pendientes. |`. En `LEEME.md` cambiar "Hay seis comandos" por "Hay siete comandos".

- [ ] **Step 8: Correr**

Run: `uv run pytest tests/unit/test_plugin_layout.py -q && uv run pytest -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add plugins/aura .claude-plugin/marketplace.json LEEME.md tests/unit/test_plugin_layout.py
git commit -m "feat(aura): skill sesion, doctor en estado/instalar y juez en sesión en revisar — aura 1.2.0"
```

---

### Task 8: Prueba manual de punta a punta en esta Mac (sin subagente; la hace el orquestador)

**Files:** ninguno.

- [ ] **Step 1: Hook** — `bash plugins/aura/scripts/check-engine.sh` en esta Mac debe terminar en `⚠️ sesión de Claude caducada → dime «arregla la sesión»` (aquí no hay token y el CLI no tiene sesión).
- [ ] **Step 2: Doctor** — `uv run videoqa doctor` debe salir 1 con `CRITERIO SIN SESIÓN · la sesión caducó o no hay token guardado`.
- [ ] **Step 3: Juez en sesión** — con el fixture: `uv run videoqa run tests/fixtures/prueba_instalacion.mp4 --hasta-juez` → leer `judge_prompt.md`, escribir `veredicto.json`, `uv run videoqa run ~/Desktop/videos/01_Entrada/prueba_instalacion.mp4 --veredicto …/veredicto.json` → el reporte debe empezar por 🔴 y `git status` debe seguir limpio (el fixture no se movió).
- [ ] **Step 4: El token real** lo guarda el usuario ejecutando `open instalar/guardar-token.command`; después `videoqa doctor` debe decir `CRITERIO OK · sesión guardada`. Esto queda como paso del usuario, documentado en el mensaje final.
