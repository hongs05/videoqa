"""Datos del video en texto compacto para el prompt del juez."""
from videoqa.config import load_rules
from videoqa.findings import Finding
from videoqa.judge_data import render, zone

R = load_rules()


def app(text, t=1.0, bbox=(0.1, 0.4, 0.6, 0.1), **kw):
    return {"text": text, "bbox": list(bbox), "t_start": t, "t_end": t + 1, "frame": "frames/sec_0003.jpg",
            "frames": ["frames/sec_0003.jpg"], "color_candidates": ["#FFFFFF"], **kw}


def _render(apps=(), findings=(), corrections=None, photo_of=None):
    return render({"palette": [{"name": "Blanco", "hex": "#FFFFFF"}], "rules": ["Texto siempre en blanco"],
                   "logo_required": True}, "TikTok\n# comentario\n",
                  {"segments": [{"start": 0, "end": 2.4, "text": "hola a todos"}]}, list(apps),
                  {"scene_cuts": [3.2], "black": [], "freeze": [], "silence": [{"start": 5, "end": 8}], "audio": None},
                  list(findings), R, photo_of or {}, corrections)


def test_zonas():
    assert zone([0.1, 0.05, 0.5, 0.1], R) == "arriba"
    assert zone([0.1, 0.45, 0.5, 0.1], R) == "centro"
    assert zone([0.1, 0.84, 0.5, 0.1], R) == "abajo (banda de la UI)"
    assert zone([0.5, 0.45, 0.45, 0.1], R) == "centro (borde derecho)"


def test_una_linea_por_texto_con_escena_y_sin_ruido():
    out = _render([app("Oferta"), app("SUSHICD", motion=0.1), app("nka", conf=0.2)])
    assert '1.0–2.0 s · "Oferta" · centro · #FFFFFF' in out
    assert '"SUSHICD" · centro · #FFFFFF · escena' in out
    assert "nka" not in out and "(+1 lecturas de confianza baja omitidas" in out
    assert "bbox" not in out and "frames/sec_0003.jpg" not in out  # nada de datos crudos


def test_secciones_y_contenido():
    out = _render()
    for s in ("## Marca", "Paleta: Blanco #FFFFFF", "Logo obligatorio: sí", "- Texto siempre en blanco",
              "## Glosario (palabras válidas)\nTikTok", "0.0–2.4 s · hola a todos", "Cortes de escena (s): 3.2",
              "Silencios: 5.0–8.0 s", "## Hallazgos del código — confirma o descarta cada [id]\n(ninguno)"):
        assert s in out, s
    assert "comentario" not in out and "## Criterio aprendido" not in out


def test_hallazgos_con_id_y_foto():
    f = Finding(id="spell-3", type="ortografia", severity="blocker", t_start=19, t_end=19.5,
                title="Posible error ortográfico: SUSHICD", detail="x" * 500, frame="frames/sec_0039.jpg",
                check="spelling_unknown_word")
    out = _render(findings=[f], photo_of={"frames/sec_0039.jpg": "claude_frames/03_0019.0s.jpg"})
    line = next(ln for ln in out.splitlines() if ln.startswith("[spell-3]"))
    assert line.startswith("[spell-3] BLOQUEA · ortografia · 19.0–19.5 s · Posible error ortográfico: SUSHICD — ")
    assert line.endswith("(foto: claude_frames/03_0019.0s.jpg)") and "x" * 300 not in line


def test_criterio_del_equipo():
    out = _render(corrections=[{"tipo": "no_detectado", "motivo": "precio distinto", "segundo": 12}])
    assert "## Criterio aprendido del equipo\n- [se escapó] precio distinto (seg. 12.0)" in out
