from videoqa.findings import Finding, save_findings, load_findings, sort_findings, count_by_severity

def make(id, severity, t):
    return Finding(id=id, type="tecnico", severity=severity, t_start=t, t_end=t + 1,
                   title="t", detail="d")

def test_roundtrip_json(tmp_path):
    f = Finding(id="a", type="marca", severity="blocker", t_start=1.0, t_end=2.0,
                title="Color", detail="x", suggestion="y", frame="frames/sec_0001.jpg",
                bbox=[0.1, 0.2, 0.3, 0.4], source="code", check="brand_color")
    p = tmp_path / "f.json"
    save_findings(p, [f])
    assert load_findings(p) == [f]

def test_from_dict_ignores_unknown_keys():
    f = Finding.from_dict({"id": "a", "type": "blooper", "severity": "warning", "t_start": 0,
                           "t_end": 1, "title": "t", "detail": "d", "extra": 1})
    assert f.id == "a" and f.suggestion == ""

def test_sort_by_severity_then_time():
    fs = [make("w2", "warning", 5), make("b", "blocker", 9), make("w1", "warning", 2), make("i", "info", 0)]
    assert [f.id for f in sort_findings(fs)] == ["b", "w1", "w2", "i"]

def test_count_by_severity():
    fs = [make("a", "blocker", 0), make("b", "warning", 0), make("c", "warning", 0)]
    assert count_by_severity(fs) == {"blocker": 1, "warning": 2, "info": 0}
