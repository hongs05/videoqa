import json
from datetime import datetime

from videoqa.findings import Finding
from videoqa.sheet import HEADERS, SheetClient, SheetWriter, row_for


class FakeWS:
    def __init__(self, rows=None): self.rows = rows or []
    def get_all_values(self): return [list(r) for r in self.rows]
    def update(self, values, range_name=None):
        r = int(range_name.split("!")[-1].lstrip("A").split(":")[0]) if "!" in range_name else int(range_name.lstrip("A").split(":")[0])
        self.rows[r - 1] = list(values[0])
    def append_row(self, values): self.rows.append(list(values))


def fnd(sev):
    return Finding(id="x", type="marca", severity=sev, t_start=0, t_end=1, title="t", detail="d")


def test_row_for():
    row = row_for("promo.mp4", "rejected", [fnd("blocker"), fnd("warning")], "02_Con_errores/promo/reporte.md",
                  "02_Con_errores/promo/promo.mp4", 58.0, datetime(2026, 9, 11, 14, 32))
    assert row == ["promo.mp4", "2026-09-11 14:32", "🔴", "1", "1", "02_Con_errores/promo/reporte.md", "02_Con_errores/promo/promo.mp4", "0:58"]


def test_row_for_error_note_goes_in_report_column():
    row = row_for("x.mp4", "error", [], "", "", 0, datetime(2026, 1, 1), note="ffprobe falló")
    assert row[2] == "⏸️ Pendiente" and row[5] == "ffprobe falló"


def test_upsert_appends_then_updates():
    ws = FakeWS()
    c = SheetClient(ws)
    c.ensure_headers()
    assert ws.rows[0] == HEADERS
    c.upsert(["a.mp4", "f", "⏳", "", "", "", "", ""])
    c.upsert(["b.mp4", "f", "⏳", "", "", "", "", ""])
    c.upsert(["a.mp4", "f2", "🟢", "0", "0", "r", "v", "0:10"])
    assert len(ws.rows) == 3 and ws.rows[1][2] == "🟢" and ws.rows[2][0] == "b.mp4"


def test_writer_queues_on_failure_and_flushes_later(tmp_path):
    pending = tmp_path / "pending.json"

    class Boom:
        def upsert(self, row): raise ConnectionError("sin red")

    w = SheetWriter(lambda: Boom(), pending)
    w.write(["a.mp4", "f", "⏳", "", "", "", "", ""])
    assert json.loads(pending.read_text()) == [{"row": ["a.mp4", "f", "⏳", "", "", "", "", ""], "attempts": 1}]
    ws = FakeWS([HEADERS])
    w2 = SheetWriter(lambda: SheetClient(ws), pending)
    w2.write(["b.mp4", "f", "🟢", "0", "0", "", "", ""])
    assert [r[0] for r in ws.rows[1:]] == ["a.mp4", "b.mp4"] and not pending.exists()


def test_writer_without_factory_is_noop(tmp_path):
    SheetWriter(None, tmp_path / "p.json").write(["a"])
    assert not (tmp_path / "p.json").exists()


def test_writer_tolerates_corrupt_pending_file(tmp_path):
    pending = tmp_path / "pending.json"
    pending.write_text("{not json")
    ws = FakeWS([HEADERS])
    w = SheetWriter(lambda: SheetClient(ws), pending)
    w.write(["a.mp4", "f", "⏳", "", "", "", "", ""])
    assert [r[0] for r in ws.rows[1:]] == ["a.mp4"]


def test_writer_saves_pending_atomically_no_tmp_left_behind(tmp_path):
    pending = tmp_path / "pending.json"

    class Boom:
        def upsert(self, row): raise ConnectionError("sin red")

    w = SheetWriter(lambda: Boom(), pending)
    w.write(["a.mp4", "f", "⏳", "", "", "", "", ""])
    assert pending.exists()
    assert not pending.with_suffix(".json.tmp").exists()


def test_writer_drops_persistently_failing_row_after_max_attempts_but_keeps_writing_others(tmp_path):
    pending = tmp_path / "pending.json"

    class Selective:
        def __init__(self): self.written = []
        def upsert(self, row):
            if row[0] == "bad.mp4":
                raise RuntimeError("siempre falla")
            self.written.append(row[0])

    client = Selective()
    w = SheetWriter(lambda: client, pending)
    w.write(["bad.mp4", "f", "⏳", "", "", "", "", ""])
    for i in range(4):
        w.write([f"good{i}.mp4", "f", "⏳", "", "", "", "", ""])

    assert client.written == ["good0.mp4", "good1.mp4", "good2.mp4", "good3.mp4"]
    assert not pending.exists()
