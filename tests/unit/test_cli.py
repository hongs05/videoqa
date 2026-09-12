import yaml
from videoqa.cli import main

def test_init_writes_config_and_folders(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setenv("VIDEOQA_CONFIG", str(cfg))
    drive = tmp_path / "Revision_Videos"
    assert main(["init", "--drive-root", str(drive), "--sheet-id", "abc"]) == 0
    data = yaml.safe_load(cfg.read_text())
    assert data["drive_root"] == str(drive) and data["sheet_id"] == "abc"
    for d in ("_config", "01_Entrada", "02_Con_errores", "03_Aprobado"):
        assert (drive / d).is_dir()

def test_run_uses_injected_process(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setenv("VIDEOQA_CONFIG", str(cfg))
    drive = tmp_path / "drive"
    main(["init", "--drive-root", str(drive)])
    video = drive / "01_Entrada" / "v.mp4"; video.write_bytes(b"x")
    import videoqa.cli as cli
    from videoqa.pipeline import Result
    monkeypatch.setattr(cli, "process_video", lambda v, s, r, runner, sheet=None: Result("approved", [], drive / "03_Aprobado" / "v"))
    assert main(["run", str(video)]) == 0

def test_run_returns_1_on_error(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setenv("VIDEOQA_CONFIG", str(cfg))
    main(["init", "--drive-root", str(tmp_path / "drive")])
    import videoqa.cli as cli
    from videoqa.pipeline import Result
    monkeypatch.setattr(cli, "process_video", lambda v, s, r, runner, sheet=None: Result("error", [], None, "boom"))
    assert main(["run", str(tmp_path / "x.mp4")]) == 1
