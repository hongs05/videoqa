from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import shutil
import sys
from pathlib import Path

import yaml

from videoqa import backends, learning
from videoqa.brand import build_brand
from videoqa.checks.spelling import in_glossary, load_base_glossary, load_glossary
from videoqa.claude_runner import ClaudeError, Runner, UsageLimitError, run_claude
from videoqa.config import (
    Settings,
    default_config_path,
    load_all_settings,
    load_rules,
    load_settings,
    load_token,
    videoqa_home,
)
from videoqa.doctor_state import write_doctor_state, write_wait_state
from videoqa.findings import Finding, load_findings, sort_findings
from videoqa.glosario import agregar, candidatas
from videoqa.pipeline import process_video
from videoqa.report import fmt_t
from videoqa.sheet import SheetClient, SheetWriter
from videoqa.watcher import watch

log = logging.getLogger("videoqa")


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
    if res.status == "waiting":
        hora = f"{res.retry_at:%H:%M}" if res.retry_at else "dentro de una hora"
        print(f"EN_ESPERA hasta {hora}: Claude sin uso disponible; el video sigue en 01_Entrada")
        return 3
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
    except UsageLimitError as e:
        # La sesión está bien: lo que falta es uso disponible. No es "sesión caducada".
        if e.resets_at:
            write_wait_state(e.resets_at, "")
        motivo = f"{motivo}; sin uso disponible hasta las {e.resets_at:%H:%M}" if e.resets_at else f"{motivo}; sin uso disponible"
    except ClaudeError as e:
        ok = False
        motivo = "no encuentro el programa claude" if "no se pudo ejecutar" in str(e) else "la sesión caducó o no está guardada"
    except Exception as e:  # noqa: BLE001 — cualquier otro fallo (timeout de red, permisos…) también se reporta
        ok = False
        motivo = f"no pude comprobarlo: {type(e).__name__}"
    write_doctor_state(ok, motivo)
    print(f"CRITERIO {'OK' if ok else 'SIN SESIÓN'} · {motivo}")
    return 0 if ok else 1


_SEVERITY_WORD = {"blocker": "BLOQUEA", "warning": "AVISO", "info": "INFO"}


def _find_job(settings: Settings, name: str) -> Path | None:
    """Carpeta de trabajo de un video por su nombre, o por un trozo si es inequívoco."""
    jobs = settings.jobs_dir
    exact = jobs / Path(name).stem
    if exact.is_dir():
        return exact
    needle = " ".join(Path(name).stem.lower().split())
    matches = [d for d in jobs.iterdir() if d.is_dir() and needle in " ".join(d.name.lower().split())] if jobs.is_dir() else []
    if len(matches) == 1:
        return matches[0]
    if matches:
        print("VARIOS videos coinciden; di cuál:")
        for d in sorted(matches):
            print(f"- {d.name}")
    else:
        print(f"NO_ENCONTRADO: no hay ningún video revisado que se llame como «{name}»")
    return None


def _job_findings(job_dir: Path) -> list[Finding]:
    final = job_dir / "findings_final.json"
    if final.exists():
        return load_findings(final)
    out: list[Finding] = []
    for name in ("findings_code.json", "findings_claude.json"):
        if (job_dir / name).exists():
            out += load_findings(job_dir / name)
    return out


def cmd_hallazgos(args) -> int:
    """Lista numerada de lo que se marcó en un video, para poder corregirlo por su id."""
    job_dir = _find_job(load_settings(), args.video)
    if job_dir is None:
        return 1
    findings = sort_findings(_job_findings(job_dir))
    print(f"VIDEO {job_dir.name} · {len(findings)} hallazgo(s)")
    for f in findings:
        detalle = f.detail if len(f.detail) <= 160 else f.detail[:157] + "…"
        print(f"[{f.id}] {fmt_t(f.t_start)} {_SEVERITY_WORD.get(f.severity, f.severity)} · {f.title} — {detalle}")
    return 0


def cmd_corregir(args) -> int:
    """Guarda una corrección del equipo para que el juez aprenda de ella."""
    settings = load_settings()
    job_dir = _find_job(settings, args.video)
    if job_dir is None:
        return 1
    finding = None
    if args.hallazgo:
        by_id = {f.id: f for f in _job_findings(job_dir)}
        if args.hallazgo not in by_id:
            print(f"NO_ENCONTRADO: el video {job_dir.name} no tiene el hallazgo {args.hallazgo}")
            return 1
        finding = by_id[args.hallazgo].to_dict()
    tipo = "no_detectado" if args.no_detectado else "falso_positivo"
    entry = learning.add_correction(settings.config_dir, tipo=tipo, video=job_dir.name, motivo=args.motivo,
                                    finding=finding, segundo=args.segundo)
    print(f"GUARDADO ({tipo}) en {learning.path_for(settings.config_dir)}")
    repetidas = learning.repeated_words(learning.load_corrections(settings.config_dir), entry.get("palabras", []))
    if repetidas:
        print(f"SUGERIR_GLOSARIO: {', '.join(repetidas)}")
    return 0


def cmd_glosario(args) -> int:
    """Propone palabras ya vistas en los videos revisados, o las añade al glosario."""
    settings = load_settings()
    ruta = settings.config_dir / "glosario.txt"
    if args.agregar:
        palabras = [w.strip().lower() for w in args.agregar.split(",") if w.strip()]
        # Lo que el glosario de fábrica ya acepta no hace falta duplicarlo en el archivo
        # del equipo: se descarta aquí y se avisa aparte, para que quede claro por qué no
        # sale en "AGREGADAS" (agregar() solo dedupea contra el archivo del equipo).
        de_fabrica = [w for w in palabras if in_glossary(w, load_base_glossary())]
        nuevas = agregar(ruta, [w for w in palabras if w not in de_fabrica])
        print(f"AGREGADAS: {', '.join(nuevas) if nuevas else 'ninguna'}")
        if de_fabrica:
            print(f"YA_DE_FABRICA: {', '.join(de_fabrica)}")
        return 0
    glossary = load_glossary(ruta)
    try:
        checker = backends.get_speller()(settings.idiomas)
    except TypeError as e:  # backend de terceros sin soporte de idiomas
        log.debug("get_speller() no acepta idiomas, uso el constructor sin argumentos: %s", e)
        checker = backends.get_speller()()
    filas = candidatas(settings.jobs_dir, glossary, checker=checker)
    print(f"CANDIDATAS {len(filas)}")
    for palabra, veces, videos in filas:
        print(f"{palabra}\t{veces}\t{videos}")
    return 0


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
    p = sub.add_parser("hallazgos", help="listar lo que se marcó en un video revisado")
    p.add_argument("video")
    p.set_defaults(fn=cmd_hallazgos)
    p = sub.add_parser("corregir", help="guardar una corrección del equipo para que el juez aprenda")
    p.add_argument("video")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--hallazgo", metavar="ID", help="id del hallazgo que NO era un error")
    g.add_argument("--no-detectado", action="store_true", help="un error que la revisión no vio")
    p.add_argument("--motivo", required=True, help="por qué, en palabras de la persona")
    p.add_argument("--segundo", type=float, help="segundo aproximado (para --no-detectado)")
    p.set_defaults(fn=cmd_corregir)
    p = sub.add_parser("doctor", help="comprobar que Claude puede dar criterio")
    p.set_defaults(fn=cmd_doctor)
    p = sub.add_parser("glosario", help="proponer palabras para el glosario del equipo")
    p.add_argument("--agregar", metavar="PALABRAS", help="añadir estas palabras (separadas por comas)")
    p.set_defaults(fn=cmd_glosario)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
