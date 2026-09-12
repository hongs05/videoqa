import json, os, time
from pathlib import Path
from videoqa.brand import EMPTY_BRAND, brand_is_stale, build_brand, load_brand

RESP = '```json\n{"palette":[{"name":"Rojo","hex":"#ff0000"}],"fonts":["Inter"],"rules":["x"],"logo_required":true}\n```'

def runner_ok(prompt, cwd):
    assert "guia_de_marca.pdf" in prompt
    return RESP

def test_load_brand_without_pdf_returns_empty(tmp_path):
    assert load_brand(tmp_path, runner_ok) == EMPTY_BRAND

def test_build_brand_writes_json_with_sha_and_upper_hex(tmp_path):
    (tmp_path / "guia_de_marca.pdf").write_bytes(b"%PDF fake")
    b = build_brand(tmp_path, runner_ok)
    assert b["palette"][0]["hex"] == "#FF0000" and b["logo_required"] is True
    saved = json.loads((tmp_path / "brand.json").read_text())
    assert len(saved["source_pdf_sha256"]) == 64

def test_load_brand_uses_cache_when_fresh(tmp_path):
    (tmp_path / "guia_de_marca.pdf").write_bytes(b"%PDF fake")
    build_brand(tmp_path, runner_ok)
    calls = []
    def runner_count(prompt, cwd):
        calls.append(1); return RESP
    load_brand(tmp_path, runner_count)
    assert calls == []
    assert brand_is_stale(tmp_path) is False

def test_manual_edit_after_pdf_change_is_kept(tmp_path):
    pdf = tmp_path / "guia_de_marca.pdf"; pdf.write_bytes(b"%PDF v1")
    build_brand(tmp_path, runner_ok)
    pdf.write_bytes(b"%PDF v2")
    old = time.time() - 100
    os.utime(pdf, (old, old))            # el PDF cambió pero brand.json es más reciente
    assert brand_is_stale(tmp_path) is False

def test_pdf_newer_than_brand_triggers_rebuild(tmp_path):
    pdf = tmp_path / "guia_de_marca.pdf"; pdf.write_bytes(b"%PDF v1")
    build_brand(tmp_path, runner_ok)
    old = time.time() - 100
    os.utime(tmp_path / "brand.json", (old, old))
    pdf.write_bytes(b"%PDF v2")
    assert brand_is_stale(tmp_path) is True
