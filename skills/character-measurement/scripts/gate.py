# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "torch>=2.7", "torchvision>=0.22", "dreamsim>=0.2.1", "lpips>=0.1.4", "timm>=1.0",
#   "numpy>=2", "opencv-python>=4.10", "pillow>=10",
#   "rtmlib>=0.0.16", "onnxruntime>=1.20", "rembg>=2.0.60",
# ]
# [tool.uv.sources]
# torch = { index = "pytorch-cu128" }
# torchvision = { index = "pytorch-cu128" }
# [[tool.uv.index]]
# name = "pytorch-cu128"
# url = "https://download.pytorch.org/whl/cu128"
# explicit = true
# ///
"""Run one pipeline stage's measurement gates for a character and record evidence.

  gate.py run CONFIG --stage STAGE --mesh MESH [--run ID] [--prev STAGE_DIR]
              [--target-mask SHOT=MASK.png ...] [--blender PATH]
      Renders the locked shots, runs every gate the config's references allow,
      and writes <evidence_root>/<character>/<run>/<stage>/ with renders, per-gate
      JSON, overlays, heatmaps, a structural checklist and summary.json.
      STAGE is one of: generated, cleanup, texture, rig.
      --prev points at the previous stage's evidence folder: enables the
      regression gate (LPIPS heatmaps + likeness-drop check). SHOT names a
      render without its prefix, e.g. head_front or fullbody_front; the mask
      marks what the pass was meant to change.

  gate.py plan CONFIG
      Validates the config and lists, without rendering anything: the gates its
      references enable, each metric's calibration status, the tolerances, and
      whether Blender was found.

  gate.py finalize STAGE_DIR
      Reads the ticked structural checklist and writes the final verdict.

  --pose-changed (run): the mesh is no longer in the reference's pose (e.g. a
      T-pose rig from an A-pose reference). Silhouette and proportion gates turn
      NOT_RUN and the regression skips full-body shots; face gates still run.

Verdicts: PASS, FAIL, LOOKALIKE (face score between the closest impostor and the
weakest true match), BORDERLINE (shape metric between the impostor fail line and
the user's tolerance), REPORT (no calibration or tolerance for this metric --
recorded, never gating), MANUAL, SETUP_ERROR, NOT_RUN.

Every threshold comes from 2D reference art or an explicit user tolerance. Renders
of existing meshes never set one: those meshes are what the gates are judging.
Prints summary.json to stdout.
"""
import argparse
import datetime as dt
import glob
import json
import os
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config as cfg  # noqa: E402
import measure  # noqa: E402
import silhouette  # noqa: E402

STAGES = ("generated", "cleanup", "texture", "rig")
FRAMING_TOLERANCE_PX = 2          # camera-solve residual: a setup check, not a likeness gate
JITTER_DEG = 2.0                  # noise-floor renders turn the camera this far each way
GATING = ("PASS", "FAIL", "LOOKALIKE", "BORDERLINE", "SETUP_ERROR")
RANK = {"FAIL": 4, "SETUP_ERROR": 4, "LOOKALIKE": 3, "BORDERLINE": 3, "PASS": 1}

CHECKLIST = """# Structural checklist -- {character} / {stage}

Tick each line ([x]) after looking at the renders in this folder, then run
`gate.py finalize {stage_dir}`. Any unticked line keeps the stage open.

- [ ] Back of the character plausible (single-image generators hallucinate it)
- [ ] Arms separated from the torso; no webbing at the armpits
- [ ] Fingers distinct (minor fusing is acceptable if the rig skips finger bones)
- [ ] Legs separated; feet distinct
- [ ] No floating shards or islands
- [ ] Texture seams acceptable on face and chest
- [ ] Nothing visibly wrong that no gate measures (write it below)

Notes:
"""


def log(*a):
    print(*a, file=sys.stderr)


def find_blender(explicit=None):
    cands = [explicit, os.environ.get("BLENDER")]
    # scoop's `current` junction and shim fail from some shells: take a real version dir
    cands += sorted(glob.glob(os.path.expanduser("~/scoop/apps/blender/[0-9]*/blender.exe")))[::-1]
    cands += sorted(glob.glob(r"C:/Program Files/Blender Foundation/Blender */blender.exe"))[::-1]
    cands += ["/Applications/Blender.app/Contents/MacOS/Blender", shutil.which("blender")]
    for c in cands:
        if c and Path(c).is_file():
            return c
    raise SystemExit("Blender not found: pass --blender or set BLENDER")


def blender(bl, args, logfile):
    cmd = [bl, "-b", "--factory-startup", "-P", str(HERE / "render_character.py"), "--", *args]
    with open(logfile, "w") as f:
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        raise SystemExit(f"Blender failed ({r.returncode}); see {logfile}")


# --------------------------------------------------------------------------- verdicts

def load_cal(c):
    out = {}
    for k, p in c["calibration"]["files"].items():
        if p and Path(p).exists():
            out[k] = json.loads(Path(p).read_text())
        elif p:
            log(f"calibration file missing: {p}")
    return out


def band(value, s, band_name, noise=0.0):
    """PASS or FAIL only when the score clears the line by more than this run's
    measured noise: a score within noise of a line is not on either side of it."""
    if value is None:
        return "NOT_RUN"
    if not s or not s.get("calibrated"):
        return "REPORT"
    sign = 1 if s["higher_is_same"] else -1
    if sign * (value - s["pass_at"]) > noise:
        return "PASS"
    if sign * (s["fail_at"] - value) > noise:
        return "FAIL"
    return band_name


def shape_verdict(value, cal, tolerance):
    """Fail line: calibrated from other characters' 2D references. Pass line: only
    a user tolerance -- never calibrated, because that would need existing meshes."""
    if value is None:
        return "NOT_RUN"
    hi = (cal or {}).get("higher_is_same", True)
    fail_at = (cal or {}).get("fail_at")
    if fail_at is not None and ((value <= fail_at) if hi else (value >= fail_at)):
        return "FAIL"
    if tolerance is None:
        return "REPORT"
    return "PASS" if ((value >= tolerance) if hi else (value <= tolerance)) else "BORDERLINE"


def noise_floor(r, jittered):
    """Largest score change from turning the camera +-JITTER_DEG: below this, a
    difference between two runs is not evidence of anything."""
    return {m: round(max(abs((j.get(m) or 0) - r[m]) for j in jittered), 4)
            for m in ("identity_cosine", "dreamsim_face")
            if r.get(m) is not None and all(j.get(m) is not None for j in jittered)}


def worst(verdicts):
    gating = [v for v in verdicts if v in RANK]
    if gating:
        return max(gating, key=lambda v: RANK[v])
    return "REPORT" if "REPORT" in verdicts else "NOT_RUN"


def face_verdict(r, cal):
    noise = r.get("noise_floor") or {}
    vs = {m: band(r.get(m), (cal or {}).get(m), "LOOKALIKE", noise.get(m, 0.0))
          for m in ("identity_cosine", "dreamsim_face")}
    return worst(list(vs.values())), vs


# ------------------------------------------------------------------------------- run

def border_rgb(path):
    """The reference's background colour: transparent renders are composited onto
    it, because DreamSim weighs colour and layout."""
    rgb = np.asarray(Image.open(path).convert("RGB"))
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    return tuple(int(v) for v in np.median(border, axis=0))


def save(d, name, obj):
    p = d / "gates" / f"{name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, default=str))
    return str(p)


def run(a):
    c = cfg.load(a.config)
    if a.stage not in STAGES:
        raise SystemExit(f"--stage must be one of {STAGES}")
    run_id = a.run or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = Path(c["evidence_root"]) / c["character"] / run_id / a.stage
    (d / "renders").mkdir(parents=True, exist_ok=True)
    (d / "overlays").mkdir(exist_ok=True)
    cal = load_cal(c)
    bl = find_blender(a.blender)
    gates, notes = {}, []
    rend = c["render"]
    # "=" form: argparse would read a bare "-Y" as a flag
    common = [f"--front-axis={c['front_axis']}", "--lens", str(rend["lens"]), "--tag", "r"]

    # 1. Full-body shots solved onto each full-body reference's silhouette box.
    fb = {}
    for ref in cfg.refs_of(c, "full_body_front", "full_body_back"):
        mask, info = silhouette.get_mask(ref["path"], ref.get("matte"))
        t, b, l, r_ = silhouette.bbox(mask)
        w, h = Image.open(ref["path"]).size
        Image.fromarray(mask.astype(np.uint8) * 255).save(d / "overlays" / f"ref_mask_{ref['view']}.png")
        views = [ref["view"]] + ([f"{ref['view']}@{JITTER_DEG:g}", f"{ref['view']}@-{JITTER_DEG:g}"]
                                 if ref["kind"] == "full_body_front" else [])
        blender(bl, [a.mesh, str(d / "renders"), "--mode", "fullbody", "--views", ",".join(views),
                     "--res", f"{w}x{h}", "--target-bbox", f"{t},{b},{(l + r_) / 2}",
                     "--cam-height", str(rend["cam_height"]), *common],
                d / "renders" / f"blender_fullbody_{ref['view']}.log")
        fb[ref["kind"]] = (ref, d / "renders" / f"r_fullbody_{ref['view']}.png")

    # 2. Silhouette + proportions (+ the camera-solve check) for each full-body ref.
    for kind, (ref, render) in (() if a.pose_changed else fb.items()):
        r = silhouette.compare(ref["path"], str(render), ref_matte=ref.get("matte"),
                               overlay=str(d / "overlays" / f"silhouette_{ref['view']}.png"))
        fe = r["framing_error_px"]
        setup_ok = isinstance(fe, dict) and max(abs(fe["top"]), abs(fe["bottom"]),
                                                abs(fe["center_x"])) <= FRAMING_TOLERANCE_PX
        shape, tol = cal.get("shape", {}), c["tolerances"]
        v_iou = shape_verdict(r["iou_aligned"], shape.get("iou_aligned"), tol.get("iou_aligned"))
        v_bd = shape_verdict(r["boundary_mean_pct_h"], shape.get("boundary_mean_pct_h"),
                             tol.get("boundary_mean_pct_h"))
        name = "silhouette_front" if kind == "full_body_front" else "silhouette_back"
        gates[name] = {"verdict": "SETUP_ERROR" if not setup_ok else worst([v_iou, v_bd]),
                       "metrics": {"iou_aligned": v_iou, "boundary_mean_pct_h": v_bd},
                       "evidence": save(d, name, r)}
        if not setup_ok:
            notes.append(f"{name}: render framing off by {fe} px -- fix the render, not the model")
        if kind == "full_body_front" and r.get("proportion_deltas"):
            ptol = tol.get("proportions", {})
            pv = {k: ("REPORT" if k not in ptol else "PASS" if abs(v) <= ptol[k] else "FAIL")
                  for k, v in r["proportion_deltas"].items()}
            gates["proportions"] = {"verdict": worst(list(pv.values())), "metrics": pv,
                                    "evidence": gates[name]["evidence"]}

    if a.pose_changed:
        for g in ("silhouette_front", "proportions") + (("silhouette_back",) if "full_body_back" in fb else ()):
            gates[g] = {"verdict": "NOT_RUN", "note": "--pose-changed: mesh is not in the reference pose"}

    # 3. Face tier 1 (always) + its noise floor from the jittered full-body renders.
    ref, render = fb["full_body_front"]
    bg = border_rgb(ref["path"])
    t1 = measure.compare(ref["path"], str(render), tier=1, bg=bg)
    jit = [measure.compare(ref["path"], str(render).replace("_front.png", f"_front@{s}.png"), tier=1, bg=bg)
           for s in (f"{JITTER_DEG:g}", f"-{JITTER_DEG:g}")]
    t1["noise_floor"] = noise_floor(t1, jit)
    cal1 = cal.get("tier1")
    if cal1 and cal1.get("face_px") and t1.get("face_px") and \
            abs(cal1["face_px"] - t1["face_px"]) > 0.2 * cal1["face_px"]:
        notes.append(f"face_tier1: calibrated at {cal1['face_px']} px, this face is {t1['face_px']} px "
                     "-- recalibrate at this size; scored as REPORT")
        cal1 = None
    v, mv = face_verdict(t1, cal1)
    gates["face_tier1"] = {"verdict": v, "tier": 1, "metrics": mv, "evidence": save(d, "face_tier1", t1)}
    gates["dreamsim_full"] = {"verdict": "REPORT", "value": t1["dreamsim_full"],
                              "note": "uncalibrated: report only, never gates"}

    # 4. Head close-ups, framed from keypoints on the solved full-body front render.
    lm = silhouette.landmarks(str(render))
    m_r, _ = silhouette.get_mask(str(render))
    top, bot, _, _ = silhouette.bbox(m_r)
    head_refs = cfg.refs_of(c, "head_front", "head_q_left", "head_q_right", "head_side_left",
                            "head_side_right", "head_back", "head_front_derived")
    ref_views = sorted({r["view"] for r in head_refs})
    views = sorted({"front", "q_left", "q_right"} | set(ref_views))
    views += [f"{v}@{s}" for v in ref_views for s in (f"{JITTER_DEG:g}", f"-{JITTER_DEG:g}")]
    hz = None
    if lm and lm["keypoints"]["chin"][2] >= silhouette.MIN_SCORE:
        hz = f"1.0,{(bot - lm['keypoints']['chin'][1]) / (bot - top):.4f}"
    else:
        notes.append("no chin keypoint on the full-body render: head framing used the 7.5-heads default")
    blender(bl, [a.mesh, str(d / "renders"), "--mode", "head", "--views", ",".join(views), "--res", "1024x1024",
                 *(["--head-z", hz] if hz else []), *common], d / "renders" / "blender_head.log")

    # 5. Face tier 4 (real head sheet) and tier 3 (approved derived reference).
    for ref in head_refs:
        bg = border_rgb(ref["path"])
        r = measure.compare(ref["path"], str(d / "renders" / f"r_head_{ref['view']}.png"), tier=4, bg=bg)
        jit = [measure.compare(ref["path"], str(d / "renders" / f"r_head_{ref['view']}@{s}.png"), tier=4, bg=bg)
               for s in (f"{JITTER_DEG:g}", f"-{JITTER_DEG:g}")]
        r["noise_floor"] = noise_floor(r, jit)
        derived = ref["kind"] == "head_front_derived"
        v, mv = face_verdict(r, cal.get("tier4"))
        name = f"face_tier{3 if derived else 4}_{ref['kind']}"
        if name in gates:   # two references of one kind: keep both, named by file
            name += "_" + Path(ref["path"]).stem
        gates[name] = {"verdict": v, "tier": 3 if derived else 4, "metrics": mv,
                       "label": "vs derived ref" if derived else "vs real head reference",
                       "evidence": save(d, name, r)}

    # 6. Regression against the previous stage, same shots.
    if a.prev:
        prev = Path(a.prev)
        masks = dict(m.split("=", 1) for m in (a.target_mask or []))
        reg = {}
        for p in sorted((prev / "renders").glob("r_*.png")):
            cur = d / "renders" / p.name
            if "@" in p.name or not cur.exists() or (a.pose_changed and "_fullbody_" in p.name):
                continue
            shot = p.stem[2:]            # "fullbody_front", "head_q_left", ...
            r = measure.diff(str(p), str(cur), masks.get(shot),
                             str(d / "overlays" / f"regression_{p.stem}.png"))
            reg[p.stem] = r
        prev_summary = json.loads((prev / "summary.json").read_text()) if (prev / "summary.json").exists() else {}
        drops = {}
        for gname, g in gates.items():
            if not gname.startswith("face_"):
                continue
            pg = prev_summary.get("gates", {}).get(gname)
            if not pg:
                continue
            now = json.loads(Path(g["evidence"]).read_text())
            was = json.loads(Path(pg["evidence"]).read_text())
            for m, worse in (("identity_cosine", lambda o, n: o - n), ("dreamsim_face", lambda o, n: n - o)):
                if now.get(m) is not None and was.get(m) is not None:
                    # a difference of two noisy measurements: both runs' noise counts
                    allowed = round(max((now.get("noise_floor") or {}).get(m, 0.0) +
                                        (was.get("noise_floor") or {}).get(m, 0.0), 0.005), 4)
                    delta = round(worse(was[m], now[m]), 4)
                    drops[f"{gname}.{m}"] = {"worse_by": delta, "allowed": allowed,
                                             "verdict": "FAIL" if delta > allowed else "PASS"}
        outside = {k: r.get("hot_outside_mask_frac") for k, r in reg.items() if "hot_outside_mask_frac" in r}
        gates["regression"] = {
            "verdict": worst([x["verdict"] for x in drops.values()]) if drops else "REPORT",
            "likeness_drops": drops, "hot_outside_mask_frac": outside,
            "note": ("heatmaps in overlays/regression_*.png must light up only what the pass "
                     "targeted; hot_outside_mask_frac is report-only until calibrated on labelled passes"),
            "evidence": save(d, "regression", reg)}

    # 7. Structural checklist (manual) and summary.
    (d / "structural_checklist.md").write_text(
        CHECKLIST.format(character=c["character"], stage=a.stage, stage_dir=d))
    gates["structural"] = {"verdict": "MANUAL", "evidence": str(d / "structural_checklist.md")}
    return summarise(c, a.stage, run_id, d, gates, notes, a.mesh)


def summarise(c, stage, run_id, d, gates, notes, mesh):
    gating = [g["verdict"] for g in gates.values() if g["verdict"] in GATING]
    overall = worst(gating) if gating else "REPORT"
    if any(g["verdict"] == "MANUAL" for g in gates.values()) and overall == "PASS":
        overall = "PENDING_MANUAL"
    s = {"character": c["character"], "stage": stage, "run": run_id, "mesh": mesh,
         "config": c["config_path"], "time": dt.datetime.now().isoformat(timespec="seconds"),
         "verdict": overall, "gates": gates, "notes": notes,
         "next": advice(c, stage, gates, d)}
    (d / "summary.json").write_text(json.dumps(s, indent=2, default=str))
    return s


def advice(c, stage, gates, d):
    """The escalation rules, applied mechanically."""
    out = []
    shape_fail = any(gates.get(g, {}).get("verdict") == "FAIL" for g in ("silhouette_front", "proportions"))
    face_fail = any(g["verdict"] == "FAIL" for k, g in gates.items() if k.startswith("face_"))
    lookalike = any(g["verdict"] == "LOOKALIKE" for k, g in gates.items() if k.startswith("face_"))
    if shape_fail or face_fail:
        past = 0
        for p in Path(c["evidence_root"], c["character"]).glob(f"*/{stage}/summary.json"):
            if p.parent == d:
                continue
            g = json.loads(p.read_text()).get("gates", {})
            if any(v.get("verdict") == "FAIL" for k, v in g.items()
                   if k in ("silhouette_front", "proportions") or k.startswith("face_")):
                past += 1
        if past + 1 >= 2:
            out.append(f"{past + 1} failed {stage} runs on shape/face: change the input image or the "
                       "generator, not the settings")
        else:
            out.append("shape/face FAIL: regenerate or fix geometry before any texture work")
    if lookalike:
        out.append("face LOOKALIKE: this is geometry work (face shape), not texture work -- "
                   "texture passes do not move identity")
    if gates.get("regression", {}).get("verdict") == "FAIL":
        out.append("regression FAIL: revert this pass; do not compensate downstream")
    if any(g["verdict"] == "SETUP_ERROR" for g in gates.values()):
        out.append("SETUP_ERROR: the render does not match the reference framing -- fix the shot first")
    if any(g["verdict"] == "REPORT" for g in gates.values()):
        out.append("REPORT gates are uncalibrated: they are evidence, not pass/fail")
    return out


def plan(config_path, blender_path=None):
    c = cfg.load(config_path)
    out = {"character": c["character"], "config": c["config_path"], "errors": [], "warnings": []}
    out["references"] = [{"kind": r["kind"], "view": r["view"], "path": r["path"],
                          "exists": Path(r["path"]).exists()} for r in c["references"]]
    for r in out["references"]:
        if not r["exists"]:
            out["errors"].append(f"missing reference: {r['path']}")
    kinds = {r["kind"] for r in c["references"]}
    gates = ["silhouette_front", "proportions", "face_tier1", "dreamsim_full (report)",
             "structural (manual)", "regression (with --prev)"]
    if "full_body_back" in kinds:
        gates.append("silhouette_back")
    for r in c["references"]:
        if r["mode"] != "head":
            continue
        name = f"face_tier{3 if r['kind'] == 'head_front_derived' else 4}_{r['kind']}"
        gates.append(name + "_" + Path(r["path"]).stem if name in gates else name)
    out["gates"] = gates

    cal = load_cal(c)
    status = {}
    for key, metrics in (("tier4", ("identity_cosine", "dreamsim_face")),
                         ("tier1", ("identity_cosine", "dreamsim_face")),
                         ("shape", ("iou_aligned", "boundary_mean_pct_h"))):
        if key not in c["calibration"]["files"]:
            status[key] = "no file configured: report-only"
            continue
        if key not in cal:
            status[key] = "configured file missing: run the calibration"
            continue
        status[key] = {m: ("calibrated" if cal[key].get(m, {}).get("calibrated")
                           else "report-only: " + cal[key].get(m, {}).get("reason", "not calibrated"))
                       for m in metrics}
    out["calibration"] = status
    fb = cfg.refs_of(c, "full_body_front")[0]
    if Path(fb["path"]).exists() and "tier1" in cal:
        lm = silhouette.landmarks(fb["path"])
        px = int(lm["head_box"][2]) if lm and "head_box" in lm else None
        cpx = cal["tier1"].get("face_px")
        out["tier1_face_px"] = {"reference": px, "calibrated_at": cpx}
        if px and cpx and abs(px - cpx) > 0.2 * cpx:
            out["warnings"].append(f"tier-1 calibration is at {cpx} px but this reference's face is "
                                   f"{px} px: recalibrate with --face-px {px}")
    out["tolerances"] = c["tolerances"] or "none: shape gates can FAIL but never PASS"
    try:
        out["blender"] = find_blender(blender_path)
    except SystemExit as e:
        out["errors"].append(str(e))
    return out


def finalize(stage_dir):
    d = Path(stage_dir)
    s = json.loads((d / "summary.json").read_text())
    text = (d / "structural_checklist.md").read_text()
    open_items = [line.strip() for line in text.splitlines() if line.strip().startswith("- [ ]")]
    s["gates"]["structural"]["verdict"] = "PASS" if not open_items else "MANUAL"
    s["gates"]["structural"]["open_items"] = open_items
    gating = [g["verdict"] for g in s["gates"].values() if g["verdict"] in GATING]
    s["verdict"] = worst(gating) if gating else "REPORT"
    if open_items and s["verdict"] == "PASS":
        s["verdict"] = "PENDING_MANUAL"
    (d / "summary.json").write_text(json.dumps(s, indent=2, default=str))
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("config")
    r.add_argument("--stage", required=True, choices=STAGES)
    r.add_argument("--mesh", required=True)
    r.add_argument("--run")
    r.add_argument("--prev")
    r.add_argument("--target-mask", action="append")
    r.add_argument("--blender")
    r.add_argument("--pose-changed", action="store_true")
    pl = sub.add_parser("plan")
    pl.add_argument("config")
    pl.add_argument("--blender")
    f = sub.add_parser("finalize")
    f.add_argument("stage_dir")
    a = ap.parse_args()
    with redirect_stdout(sys.stderr):
        if a.cmd == "run":
            out = run(a)
        elif a.cmd == "plan":
            out = plan(a.config, a.blender)
        else:
            out = finalize(a.stage_dir)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
