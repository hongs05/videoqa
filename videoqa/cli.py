from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import shutil
import sys
from pathlib import Path

import yaml

from videoqa.brand import build_brand
from videoqa.claude_runner import ClaudeError, Runner, run_claude
from videoqa.config import (
    Settings,
    default_config_path,
    load_all_settings,
    load_rules,
    load_settings,
    load_token,
    videoqa_home,
)
from videoqa.doctor_state import write_doctor_state
from videoqa.pipeline import process_video
from videoqa.sheet import SheetClient, SheetWriter
from videoqa.watcher import watch


def setup_logging() -> None:
    log_dir = videoqa_home()
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    root = logging.getLogger("videoqa")
    root.setLevel(logging.INFO)
    for h in root.handlers[:]:
        h.close()
        root.removeHandler(h)
    fh = logging.handlers.RotatingFileHandler(log_dir / "videoqa.log", maxBytes=5_000_000, backupCount=3)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    root.handlers = [fh, sh]


def make_runner(settings: Settings, rules: dict) -> Runner:
    timeout = int(rules["claude"]["timeout_s"])
    return lambda prompt, cwd: run_claude(prompt, cwd, claude_bin=settings.claude_bin, timeout=timeout)


def make_sheet(settings: Settings) -> SheetWriter:
    log = logging.getLogger("videoqa")
    factory = None
    if settings.sheet_id and settings.service_account_json:
        factory = lambda: SheetClient.connect(settings.sheet_id, settings.service_account_json)  # noqa: E731
    elif settings.sheet_id or settings.service_account_json:
        # Media configuración es casi siempre un descuido: el Sheet se desactiva en silencio
        # y el equipo cree que el tablero se está actualizando.
        falta = "service_account_json" if settings.sheet_id else "sheet_id"
        log.warning("Sheet desactivado: falta '%s' en la configuración (re-ejecuta `videoqa init` "
                    "con --sheet-id y --service-account)", falta)
    return SheetWriter(factory, settings.jobs_dir / "sheet_pending.json")


def cmd_init(args) -> int:
    cfg_path = Path(os.environ.get("VIDEOQA_CONFIG", default_config_path()))
    drive = Path(args.drive_root).expanduser()
    data = {"drive_root": str(drive)}
    if args.sheet_id:
        data["sheet_id"] = args.sheet_id
    if args.service_account:
        data["service_account_json"] = str(Path(args.service_account).expanduser())
    extras = [Path(e).expanduser() for e in (getattr(args, "carpeta_extra", None) or [])]
    extras = [e for e in extras if e != drive]
    if extras:
        data["carpetas_extra"] = [str(e) for e in extras]
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(yaml.safe_dump(data, allow_unicode=True))
    for raiz in [drive, *extras]:
        for d in ("_config", "01_Entrada", "02_Con_errores", "03_Aprobado"):
            (raiz / d).mkdir(parents=True, exist_ok=True)
    print(f"Config escrita en {cfg_path}\nCarpetas creadas en {drive}")
    for e in extras:
        print(f"Carpeta adicional lista en {e}")
    return 0


def cmd_brand(args) -> int:
    settings, rules = load_settings(), load_rules()
    brand = build_brand(settings.config_dir, make_runner(settings, rules))
    print(f"brand.json actualizado: {len(brand['palette'])} colores, {len(brand['rules'])} reglas")
    return 0


def cmd_run(args) -> int:
    settings, rules = load_settings(), load_rules()
    video = Path(args.video).expanduser().resolve()
    entrada = settings.entrada.resolve()
    if video.parent != entrada and video.exists():
        # Un video de fuera (p. ej. el de prueba que viene con el motor) se copia:
        # deliver() MUEVE el archivo, y mover el fixture del repo lo deja sucio.
        entrada.mkdir(parents=True, exist_ok=True)
        destino = entrada / video.name
        shutil.copy2(video, destino)
        print(f"Copiado a 01_Entrada: {video.name}")
        video = destino
    modo = "preparar" if getattr(args, "hasta_juez", False) else "completo"
    veredicto_text = Path(args.veredicto).expanduser().read_text(encoding="utf-8") if getattr(args, "veredicto", None) else None
    res = process_video(video, settings, rules, make_runner(settings, rules), sheet=make_sheet(settings),
                        modo=modo, veredicto_text=veredicto_text)
    if res.status == "pending":
        print(f"JUEZ_PENDIENTE {settings.jobs_dir / video.stem}")
        return 0
    if res.dest:
        print(f"{res.status.upper()} → {res.dest / 'reporte.md'}")
    else:
        print(f"ERROR: {res.error}")
    return 0 if res.status in ("approved", "rejected") else 1


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
        run_claude("Responde solo con la palabra: ok", videoqa_home(), claude_bin=claude_bin, timeout=180, allowed_tools=())
    except ClaudeError as e:
        ok = False
        motivo = "no encuentro el programa claude" if "no se pudo ejecutar" in str(e) else "la sesión caducó o no está guardada"
    except Exception as e:  # noqa: BLE001 — cualquier otro fallo (timeout de red, permisos…) también se reporta
        ok = False
        motivo = f"no pude comprobarlo: {type(e).__name__}"
    write_doctor_state(ok, motivo)
    print(f"CRITERIO {'OK' if ok else 'SIN SESIÓN'} · {motivo}")
    return 0 if ok else 1


def cmd_watch(args) -> int:
    carpetas, rules = load_all_settings(), load_rules()
    principal = carpetas[0]
    watch(carpetas, rules, make_runner(principal, rules), sheet=make_sheet(principal), once=args.once)
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    ap = argparse.ArgumentParser(prog="videoqa", description="Revisión automática de videos pre-publicación")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="crear config y carpetas de Drive")
    p.add_argument("--drive-root", required=True)
    p.add_argument("--sheet-id")
    p.add_argument("--service-account")
    p.add_argument("--carpeta-extra", action="append", metavar="RUTA",
                   help="carpeta adicional a vigilar (p. ej. una local de pruebas); repetible")
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("brand", help="regenerar brand.json desde guia_de_marca.pdf")
    p.set_defaults(fn=cmd_brand)
    p = sub.add_parser("run", help="procesar un video")
    p.add_argument("video")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--hasta-juez", action="store_true",
                   help="preparar las entradas del juez y parar (la sesión de Claude hace de juez)")
    g.add_argument("--veredicto", metavar="JSON", help="reanudar con un veredicto ya escrito")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("watch", help="vigilar 01_Entrada/")
    p.add_argument("--once", action="store_true")
    p.set_defaults(fn=cmd_watch)
    p = sub.add_parser("doctor", help="comprobar que Claude puede dar criterio")
    p.set_defaults(fn=cmd_doctor)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
