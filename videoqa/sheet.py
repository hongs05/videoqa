from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Callable

from videoqa.findings import Finding, count_by_severity
from videoqa.report import fmt_t

log = logging.getLogger("videoqa")

HEADERS = ["Video", "Fecha", "Estado", "Bloqueantes", "Advertencias", "Reporte", "Video (ruta)", "Duración"]
STATUS_LABEL = {"processing": "⏳", "approved": "🟢", "rejected": "🔴", "error": "⏸️ Pendiente",
                "waiting": "⏳ En espera"}
MAX_ATTEMPTS = 5


def row_for(video_name: str, status: str, findings: list[Finding], report_path: str, video_path: str,
            duration: float, when: datetime, note: str = "") -> list[str]:
    c = count_by_severity(findings)
    return [video_name, f"{when:%Y-%m-%d %H:%M}", STATUS_LABEL[status], str(c["blocker"]) if status not in ("processing", "waiting") else "",
            str(c["warning"]) if status not in ("processing", "waiting") else "", note or report_path, video_path, fmt_t(duration) if duration else ""]


class SheetClient:
    def __init__(self, worksheet):
        self.ws = worksheet

    @classmethod
    def connect(cls, sheet_id: str, service_account_json: Path) -> "SheetClient":
        import gspread

        gc = gspread.service_account(filename=str(service_account_json))
        return cls(gc.open_by_key(sheet_id).sheet1)

    def ensure_headers(self) -> None:
        rows = self.ws.get_all_values()
        if not rows:
            self.ws.append_row(HEADERS)
        elif rows[0] != HEADERS:
            self.ws.update([HEADERS], range_name="A1:H1")

    def upsert(self, row: list[str]) -> None:
        self.ensure_headers()
        rows = self.ws.get_all_values()
        for idx, existing in enumerate(rows[1:], start=2):
            if existing and existing[0] == row[0]:
                self.ws.update([row], range_name=f"A{idx}:H{idx}")
                return
        self.ws.append_row(row)


class SheetWriter:
    def __init__(self, client_factory: Callable[[], SheetClient] | None, pending_path: Path):
        self.factory = client_factory
        self.pending_path = pending_path

    def _pending(self) -> list[dict]:
        if not self.pending_path.exists():
            return []
        try:
            data = json.loads(self.pending_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Cola de pendientes ilegible (%s: %s); se descarta", type(e).__name__, e)
            return []
        # Acepta entradas heredadas (fila plana) además del formato {"row", "attempts"}.
        return [entry if isinstance(entry, dict) else {"row": entry, "attempts": 0} for entry in data]

    def _save_pending(self, entries: list[dict]) -> None:
        if entries:
            self.pending_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.pending_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(entries, ensure_ascii=False))
            os.replace(tmp, self.pending_path)
        elif self.pending_path.exists():
            self.pending_path.unlink()

    def write(self, row: list[str]) -> None:
        if self.factory is None:
            return
        queue = self._pending() + [{"row": row, "attempts": 0}]
        try:
            client = self.factory()
        except Exception as e:  # noqa: BLE001 — red/credenciales; se reintenta después
            log.warning("Sheet no disponible (%s: %s); %d fila(s) en cola", type(e).__name__, e, len(queue))
            self._save_pending(queue)
            return

        remaining: list[dict] = []
        for entry in queue:
            try:
                client.upsert(entry["row"])
            except Exception as e:  # noqa: BLE001 — red/credenciales; se reintenta después
                entry["attempts"] = entry.get("attempts", 0) + 1
                if entry["attempts"] >= MAX_ATTEMPTS:
                    log.error("Descartando fila tras %d intento(s) fallidos (%s: %s): %s",
                              entry["attempts"], type(e).__name__, e, entry["row"])
                else:
                    log.warning("Sheet no disponible para fila %s (%s: %s); %d intento(s)",
                                entry["row"][0] if entry["row"] else "?", type(e).__name__, e, entry["attempts"])
                    remaining.append(entry)
        self._save_pending(remaining)
