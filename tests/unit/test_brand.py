import json, os, time
from pathlib import Path
import pytest
from videoqa.brand import EMPTY_BRAND, brand_is_stale, build_brand, load_brand
from videoqa.claude_runner import ClaudeError

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


# --- Fix round 1: hardening tests ---

def test_load_brand_without_pdf_uses_manual_brand_json(tmp_path):
    """Sin PDF, un brand.json escrito a mano es una configuración válida y se respeta."""
    manual = {
        "palette": [{"name": "Old", "hex": "#000000"}],
        "fonts": ["OldFont"], "rules": ["old"], "logo_required": True,
        "source_pdf_sha256": "deadbeef",
    }
    (tmp_path / "brand.json").write_text(json.dumps(manual))

    def runner_should_not_be_called(prompt, cwd):
        raise AssertionError("runner should not be called when the PDF is missing")

    assert load_brand(tmp_path, runner_should_not_be_called) == manual


def test_load_brand_without_pdf_and_corrupt_brand_json_is_empty(tmp_path):
    (tmp_path / "brand.json").write_text("{no es json")

    def runner_should_not_be_called(prompt, cwd):
        raise AssertionError("runner should not be called when the PDF is missing")

    assert load_brand(tmp_path, runner_should_not_be_called) == EMPTY_BRAND


def test_load_brand_rebuilds_when_brand_json_is_corrupt(tmp_path):
    (tmp_path / "guia_de_marca.pdf").write_bytes(b"%PDF fake")
    (tmp_path / "brand.json").write_text("{not valid json")
    calls = []

    def runner_count(prompt, cwd):
        calls.append(1)
        return RESP

    result = load_brand(tmp_path, runner_count)
    assert calls == [1]
    assert result["palette"][0]["hex"] == "#FF0000"
    assert result["logo_required"] is True


def test_build_brand_rejects_non_dict_top_level(tmp_path, monkeypatch):
    (tmp_path / "guia_de_marca.pdf").write_bytes(b"%PDF fake")
    monkeypatch.setattr("videoqa.brand.extract_json", lambda text: ["not", "a", "dict"])
    with pytest.raises(ClaudeError):
        build_brand(tmp_path, lambda prompt, cwd: "irrelevant")


def test_build_brand_coerces_off_schema_fields(tmp_path, monkeypatch):
    (tmp_path / "guia_de_marca.pdf").write_bytes(b"%PDF fake")
    monkeypatch.setattr("videoqa.brand.extract_json", lambda text: {
        "palette": "rojo", "fonts": "Inter", "rules": None, "logo_required": "yes",
    })
    b = build_brand(tmp_path, lambda prompt, cwd: "irrelevant")
    assert b["palette"] == []
    assert b["fonts"] == []
    assert b["rules"] == []
    assert b["logo_required"] is True


def test_build_brand_skips_invalid_hex_and_normalizes_valid_ones(tmp_path, monkeypatch):
    (tmp_path / "guia_de_marca.pdf").write_bytes(b"%PDF fake")
    monkeypatch.setattr("videoqa.brand.extract_json", lambda text: {
        "palette": [
            {"name": "NoHash", "hex": "ff0000"},
            {"name": "Invalid", "hex": "zzzzzz"},
            {"name": "AlreadyHashed", "hex": "#00ff00"},
        ],
        "fonts": [], "rules": [], "logo_required": False,
    })
    b = build_brand(tmp_path, lambda prompt, cwd: "irrelevant")
    assert b["palette"] == [
        {"name": "NoHash", "hex": "#FF0000"},
        {"name": "AlreadyHashed", "hex": "#00FF00"},
    ]
