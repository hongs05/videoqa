import json
from pathlib import Path
import pytest
from PIL import Image
from videoqa.claude_runner import ClaudeError
from videoqa.config import load_rules
from videoqa.findings import Finding
from videoqa.job import Job
from videoqa.judge import JudgeError, build_prompt, parse_verdict, prepare_inputs, run_judge, select_frames

R = load_rules()
SKILL = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "revisor-video" / "SKILL.md"

GOOD = json.dumps({
    "findings": [{"type": "blooper", "severity": "blocker", "t_start": 3.0, "t_end": 4.0,
                  "title": "Toma fallida", "detail": "dice otra vez", "suggestion": "cortar", "frame": None}],
    "confirmed_code_findings": ["spell-0"],
    "dismissed_code_findings": [{"id": "spell-1", "reason": "nombre propio"}],
    "guion_real_md": "## Escena 1 [0:00]\nHola",
})

def frames_list(n=24, period=0.5):
    fr = [{"file": f"frames/sec_{i+1:04d}.jpg", "t": i * period, "kind": "second"} for i in range(n)]
    fr.append({"file": "frames/scene_001.jpg", "t": 5.1, "kind": "scene"})
    return sorted(fr, key=lambda f: f["t"])

def make_job(tmp_path, n=24):
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    (job.dir / "frames").mkdir()
    for f in frames_list(n):
        Image.new("RGB", (108, 192), (20, 20, 20)).save(job.path(f["file"]))
    return job

def test_select_frames_prioritizes_scene_text_and_findings():
    frames = frames_list()
    apps = [{"text": "x", "frame": "frames/sec_0003.jpg", "bbox": [0, 0, 1, 1], "t_start": 1.0, "t_end": 2.0, "frames": []}]
    fnd = [Finding(id="a", type="marca", severity="blocker", t_start=8, t_end=9, title="t", detail="d", frame="frames/sec_0017.jpg")]
    sel = select_frames(frames, apps, fnd, max_frames=6)
    assert len(sel) == 6
    assert {"frames/scene_001.jpg", "frames/sec_0003.jpg", "frames/sec_0017.jpg"} <= set(sel)
    ts = [next(f["t"] for f in frames if f["file"] == s) for s in sel]
    assert ts == sorted(ts)

def test_select_frames_respects_cap_and_dedupes():
    frames = frames_list()
    assert len(select_frames(frames, [], [], max_frames=3)) == 3
    assert len(set(select_frames(frames, [], [], max_frames=100))) == len(frames)

def test_select_frames_quota_reserves_findings_and_appearances():
    fps, duration, n_scenes = 2, 60.0, 20
    step = 1.0 / fps
    n_seconds = round(duration * fps)
    seconds = [{"file": f"frames/sec_{i+1:04d}.jpg", "t": round(i * step, 2), "kind": "second"} for i in range(n_seconds)]
    scenes = [{"file": f"frames/scene_{i+1:03d}.jpg", "t": round(i * (duration / n_scenes) + 0.05, 2), "kind": "scene"}
              for i in range(n_scenes)]
    frames = sorted(seconds + scenes, key=lambda f: f["t"])
    app_files = [seconds[i]["file"] for i in (10, 20, 30, 40, 50)]
    apps = [{"text": "x", "frame": f} for f in app_files]
    finding_files = [seconds[5]["file"], seconds[60]["file"]]
    fnd = [Finding(id=f"f{i}", type="marca", severity="blocker", t_start=0, t_end=1, title="t", detail="d", frame=ff)
           for i, ff in enumerate(finding_files)]

    sel = select_frames(frames, apps, fnd, max_frames=15)
    scene_files = {s["file"] for s in scenes}
    assert set(finding_files) <= set(sel)
    assert len(set(app_files) & set(sel)) >= 3
    assert len([s for s in sel if s in scene_files]) <= 10

def test_select_frames_even_fill_reaches_last_second():
    fps, duration = 2, 58.0
    step = 1.0 / fps
    n_seconds = round(duration * fps)
    seconds = [{"file": f"frames/sec_{i+1:04d}.jpg", "t": round(i * step, 2), "kind": "second"} for i in range(n_seconds)]
    scenes = [{"file": f"frames/scene_{i+1:03d}.jpg", "t": round(i * 15 + 2, 2), "kind": "scene"} for i in range(3)]
    frames = sorted(seconds + scenes, key=lambda f: f["t"])
    assert seconds[-1]["t"] == pytest.approx(57.5)
    sel = select_frames(frames, [], [], max_frames=15)
    assert seconds[-1]["file"] in sel

def test_prepare_inputs_writes_files_and_resizes(tmp_path):
    job = make_job(tmp_path)
    m = prepare_inputs(job, {"palette": []}, "TikTok\n", {"segments": []}, {"appearances": []},
                       {"scene_cuts": []}, [], frames_list(), R)
    assert (job.dir / "judge_input" / "brand.json").exists()
    assert (job.dir / "judge_input" / "glosario.txt").read_text() == "TikTok\n"
    assert len(m["frames"]) <= R["claude"]["max_frames"]
    img = Image.open(job.path(m["frames"][0]["file"]))
    assert img.size[1] <= R["claude"]["frame_height"]
    assert m["frames"][0]["file"].startswith("claude_frames/") and "s.jpg" in m["frames"][0]["file"]

def test_build_prompt_includes_skill_and_manifest():
    p = build_prompt("# Rol\nrevisor", {"frames": [{"file": "claude_frames/00_0000.0s.jpg", "t": 0.0}], "inputs": ["judge_input/brand.json"]}, 12.0)
    assert "# Rol" in p and "claude_frames/00_0000.0s.jpg" in p and "12.0" in p

def test_parse_verdict_valid():
    v = parse_verdict(GOOD)
    assert v["findings"][0]["severity"] == "blocker" and v["dismissed_code_findings"][0]["id"] == "spell-1"

@pytest.mark.parametrize("bad", [
    '{"findings": "no"}',
    '{"findings": [{"type": "x", "severity": "blocker", "t_start": 0, "t_end": 1, "title": "t", "detail": "d"}], "guion_real_md": ""}',
    '{"findings": [{"type": "marca", "severity": "grave", "t_start": 0, "t_end": 1, "title": "t", "detail": "d"}], "guion_real_md": ""}',
    '{"findings": [], "guion_real_md": 5}',
    '{"findings": [], "guion_real_md": "", "confirmed_code_findings": "spell-0"}',
    '{"findings": [], "guion_real_md": "", "dismissed_code_findings": "nope"}',
])
def test_parse_verdict_invalid(bad):
    with pytest.raises(ValueError):
        parse_verdict(bad)

def test_parse_verdict_dismissal_without_reason_is_dropped():
    bad = json.dumps({"findings": [], "guion_real_md": "",
                       "dismissed_code_findings": [{"id": "spell-1"}, {"id": "spell-2", "reason": ""}]})
    v = parse_verdict(bad)
    assert v["dismissed_code_findings"] == []

def test_parse_verdict_dismissal_without_id_is_dropped():
    bad = json.dumps({"findings": [], "guion_real_md": "",
                       "dismissed_code_findings": [{"reason": "nombre propio"}, {"id": "", "reason": "x"}]})
    v = parse_verdict(bad)
    assert v["dismissed_code_findings"] == []

def test_parse_verdict_dismissal_valid_kept():
    v = parse_verdict(GOOD)
    assert v["dismissed_code_findings"] == [{"id": "spell-1", "reason": "nombre propio"}]

def test_run_judge_happy_path(tmp_path):
    job = make_job(tmp_path)
    calls = []
    def runner(prompt, cwd):
        calls.append(cwd); return GOOD
    cf = [Finding(id="spell-1", type="ortografia", severity="warning", t_start=0, t_end=1, title="t", detail="d")]
    out = run_judge(job, {"palette": []}, "", {"segments": []}, {"appearances": []}, {"scene_cuts": []},
                    cf, frames_list(), R, runner=runner, skill_path=SKILL)
    assert calls == [job.dir]
    assert out["findings"][0].source == "claude" and out["findings"][0].id == "claude-0"
    assert out["dismissed"] == [{"id": "spell-1", "reason": "nombre propio"}]
    assert job.path("guion_real.md").read_text().startswith("## Escena 1")
    assert job.path("findings_claude.json").exists()

def test_run_judge_retries_then_succeeds(tmp_path):
    job = make_job(tmp_path)
    answers = iter(["esto no es json", GOOD])
    out = run_judge(job, {}, "", {"segments": []}, {"appearances": []}, {}, [], frames_list(), R,
                    runner=lambda p, c: next(answers), skill_path=SKILL)
    assert len(out["findings"]) == 1

def test_run_judge_fails_after_two_attempts(tmp_path):
    job = make_job(tmp_path)
    def runner(p, c):
        raise ClaudeError("rate limit")
    with pytest.raises(JudgeError):
        run_judge(job, {}, "", {"segments": []}, {"appearances": []}, {}, [], frames_list(), R, runner=runner, skill_path=SKILL)

def test_run_judge_drops_unknown_dismissal_id(tmp_path):
    job = make_job(tmp_path)
    out = run_judge(job, {}, "", {"segments": []}, {"appearances": []}, {}, [], frames_list(), R,
                    runner=lambda p, c: GOOD, skill_path=SKILL)
    assert out["dismissed"] == []

def test_run_judge_keeps_known_dismissal_id(tmp_path):
    job = make_job(tmp_path)
    cf = [Finding(id="spell-1", type="ortografia", severity="warning", t_start=0, t_end=1, title="t", detail="d")]
    out = run_judge(job, {}, "", {"segments": []}, {"appearances": []}, {}, cf, frames_list(), R,
                    runner=lambda p, c: GOOD, skill_path=SKILL)
    assert out["dismissed"] == [{"id": "spell-1", "reason": "nombre propio"}]

def test_run_judge_wraps_prepare_inputs_errors(tmp_path):
    job = make_job(tmp_path)
    job.path("frames/scene_001.jpg").unlink()
    with pytest.raises(JudgeError):
        run_judge(job, {}, "", {"segments": []}, {"appearances": []}, {}, [], frames_list(), R,
                  runner=lambda p, c: GOOD, skill_path=SKILL)

def test_run_judge_wraps_missing_skill_path(tmp_path):
    job = make_job(tmp_path)
    missing = tmp_path / "no_such_skill.md"
    with pytest.raises(JudgeError):
        run_judge(job, {}, "", {"segments": []}, {"appearances": []}, {}, [], frames_list(), R,
                  runner=lambda p, c: GOOD, skill_path=missing)

def test_run_judge_uses_explicit_duration(tmp_path):
    job = make_job(tmp_path)
    captured = {}
    def runner(prompt, cwd):
        captured["prompt"] = prompt
        return GOOD
    run_judge(job, {}, "", {"segments": []}, {"appearances": []}, {}, [], frames_list(), R,
              runner=runner, skill_path=SKILL, duration=99.9)
    assert "99.9" in captured["prompt"]

def test_run_judge_appends_retry_note_on_second_attempt(tmp_path):
    job = make_job(tmp_path)
    prompts = []
    answers = iter(["esto no es json", GOOD])
    def runner(prompt, cwd):
        prompts.append(prompt)
        return next(answers)
    run_judge(job, {}, "", {"segments": []}, {"appearances": []}, {}, [], frames_list(), R,
              runner=runner, skill_path=SKILL)
    assert "no fue válida" not in prompts[0]
    assert "no fue válida" in prompts[1]

def test_run_judge_drops_invalid_frame(tmp_path):
    job = make_job(tmp_path)
    verdict = json.dumps({
        "findings": [{"type": "blooper", "severity": "blocker", "t_start": 3.0, "t_end": 4.0,
                      "title": "t", "detail": "d", "suggestion": "", "frame": "frames/does_not_exist.jpg"}],
        "confirmed_code_findings": [], "dismissed_code_findings": [], "guion_real_md": "",
    })
    out = run_judge(job, {}, "", {"segments": []}, {"appearances": []}, {}, [], frames_list(), R,
                    runner=lambda p, c: verdict, skill_path=SKILL)
    assert out["findings"][0].frame is None

def test_run_judge_keeps_existing_frames_path(tmp_path):
    job = make_job(tmp_path)
    existing = frames_list()[0]["file"]
    verdict = json.dumps({
        "findings": [{"type": "blooper", "severity": "blocker", "t_start": 3.0, "t_end": 4.0,
                      "title": "t", "detail": "d", "suggestion": "", "frame": existing}],
        "confirmed_code_findings": [], "dismissed_code_findings": [], "guion_real_md": "",
    })
    out = run_judge(job, {}, "", {"segments": []}, {"appearances": []}, {}, [], frames_list(), R,
                    runner=lambda p, c: verdict, skill_path=SKILL)
    assert out["findings"][0].frame == existing
