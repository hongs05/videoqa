from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

from videoqa.findings import Finding, count_by_severity

log = logging.getLogger("videoqa")

HEADERS = ["Video", "Fecha", "Estado", "Bloqueantes", "Advertencias", "Reporte", "Video (ruta)", "Duración"]
STATUS_LABEL = {"processing": "⏳", "approved": "🟢", "rejected": "🔴", "error": "❌ Error"}


def _fmt_t(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return f"{sec // 60}:{sec % 60:02d}"


def row_for(video_name: str, status: str, findings: list[Finding], report_path: str, video_path: str,
            duration: float, when: datetime, note: str = "") -> list[str]:
    c = count_by_severity(findings)
    return [video_name, f"{when:%Y-%m-%d %H:%M}", STATUS_LABEL[status], str(c["blocker"]) if status != "processing" else "",
            str(c["warning"]) if status != "processing" else "", note or report_path, video_path, _fmt_t(duration) if duration else ""]


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
            self.ws.update("A1:H1", [HEADERS])

    def upsert(self, row: list[str]) -> None:
        self.ensure_headers()
        rows = self.ws.get_all_values()
        for idx, existing in enumerate(rows[1:], start=2):
            if existing and existing[0] == row[0]:
                self.ws.update(f"A{idx}:H{idx}", [row])
                return
        self.ws.append_row(row)


class SheetWriter:
    def __init__(self, client_factory: Callable[[], SheetClient] | None, pending_path: Path):
        self.factory = client_factory
        self.pending_path = pending_path

    def _pending(self) -> list[list[str]]:
        return json.loads(self.pending_path.read_text()) if self.pending_path.exists() else []

    def _save_pending(self, rows: list[list[str]]) -> None:
        if rows:
            self.pending_path.parent.mkdir(parents=True, exist_ok=True)
            self.pending_path.write_text(json.dumps(rows, ensure_ascii=False))
        elif self.pending_path.exists():
            self.pending_path.unlink()

    def write(self, row: list[str]) -> None:
        if self.factory is None:
            return
        queue = self._pending() + [row]
        try:
            client = self.factory()
            while queue:
                client.upsert(queue[0])
                queue.pop(0)
        except Exception as e:  # noqa: BLE001 — red/credenciales; se reintenta después
            log.warning("Sheet no disponible (%s); %d fila(s) en cola", e, len(queue))
        self._save_pending(queue)
