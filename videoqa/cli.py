from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sys
from pathlib import Path

import yaml

from videoqa.brand import build_brand
from videoqa.claude_runner import Runner, run_claude
from videoqa.config import Settings, default_config_path, load_rules, load_settings, videoqa_home
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
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(yaml.safe_dump(data, allow_unicode=True))
    for d in ("_config", "01_Entrada", "02_Con_errores", "03_Aprobado"):
        (drive / d).mkdir(parents=True, exist_ok=True)
    print(f"Config escrita en {cfg_path}\nCarpetas creadas en {drive}")
    return 0


def cmd_brand(args) -> int:
    settings, rules = load_settings(), load_rules()
    brand = build_brand(settings.config_dir, make_runner(settings, rules))
    print(f"brand.json actualizado: {len(brand['palette'])} colores, {len(brand['rules'])} reglas")
    return 0


def cmd_run(args) -> int:
    settings, rules = load_settings(), load_rules()
    res = process_video(Path(args.video).expanduser(), settings, rules, make_runner(settings, rules), sheet=make_sheet(settings))
    if res.dest:
        print(f"{res.status.upper()} → {res.dest / 'reporte.md'}")
    else:
        print(f"ERROR: {res.error}")
    return 0 if res.status in ("approved", "rejected") else 1


def cmd_watch(args) -> int:
    settings, rules = load_settings(), load_rules()
    watch(settings, rules, make_runner(settings, rules), sheet=make_sheet(settings), once=args.once)
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    ap = argparse.ArgumentParser(prog="videoqa", description="Revisión automática de videos pre-publicación")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="crear config y carpetas de Drive")
    p.add_argument("--drive-root", required=True)
    p.add_argument("--sheet-id")
    p.add_argument("--service-account")
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("brand", help="regenerar brand.json desde guia_de_marca.pdf")
    p.set_defaults(fn=cmd_brand)
    p = sub.add_parser("run", help="procesar un video")
    p.add_argument("video")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("watch", help="vigilar 01_Entrada/")
    p.add_argument("--once", action="store_true")
    p.set_defaults(fn=cmd_watch)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
