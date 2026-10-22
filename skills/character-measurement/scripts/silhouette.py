# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy>=2", "opencv-python>=4.10", "pillow>=10", "rtmlib>=0.0.16", "onnxruntime>=1.20", "rembg>=2.0.60"]
# ///
"""Silhouette and proportion measurements between a reference image and a render.
Every command prints one JSON object to stdout.

  silhouette.py matte IMAGE [--out mask.png]
      Foreground mask: real alpha if the image has it, else rembg
      (isnet-general-use; --model isnet-anime for anime art), largest component,
      holes filled. --key uses a border-colour key instead: fine for a flat
      render background, wrong for a vignette or floor glow. Look at the PNG
      before trusting any matte; --matte takes a hand-made one.

  silhouette.py landmarks IMAGE
      Body keypoints (RTMPose whole-body), the chin, and the head box used for
      the matched-scale face check.

  silhouette.py compare REF RENDER [--ref-matte M] [--render-matte M] [--overlay out.png]
      IoU raw (as framed) and aligned (render mask scaled/shifted so its bbox
      height, top and centre match the reference -- shape, not framing), the
      mean/p95 boundary distance as % of height, and height-normalised
      proportions for both images with their deltas.

  silhouette.py calibrate --config A.json --config B.json ... [--out shape.json]
      Fail lines from 2D art only: each character's full-body reference against
      every other character's. A mesh no closer to its own reference than another
      character is has failed. There is no calibrated pass line (that would need
      renders of existing meshes, which never set thresholds); a pass line is a
      user tolerance in the config.

Raw IoU verifies the camera solve; aligned IoU and proportions are the shape gates.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# COCO-WholeBody indices (rtmlib Wholebody output).
KP = {"nose": 0, "eye_l": 1, "eye_r": 2, "ear_l": 3, "ear_r": 4,
      "shoulder_l": 5, "shoulder_r": 6, "hip_l": 11, "hip_r": 12,
      "knee_l": 13, "knee_r": 14, "ankle_l": 15, "ankle_r": 16, "chin": 31}
FACE = slice(23, 91)          # the 68 face landmarks
MIN_SCORE = 0.3


def log(*a):
    print(*a, file=sys.stderr)


# ----------------------------------------------------------------------------- masks

def load_rgba(path):
    return np.asarray(Image.open(path).convert("RGBA"))


def has_alpha(rgba):
    a = rgba[..., 3]
    return a.min() < 250 and (a < 128).mean() > 0.01


def key_mask(rgb, tol=None):
    """Foreground = far from the border colour. Largest component, holes filled."""
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]).astype(np.float32)
    bg = np.median(border, axis=0)
    d = np.linalg.norm(rgb.astype(np.float32) - bg, axis=-1)
    if tol is None:
        spread = np.percentile(np.linalg.norm(border - bg, axis=-1), 99)
        tol = max(12.0, 2.5 * spread)
    m = (d > tol).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return largest_filled(m), {"bg_rgb": bg.round().tolist(), "tol": round(float(tol), 1)}


def largest_filled(m):
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n <= 1:
        return np.zeros_like(m, dtype=bool)
    keep = (lab == 1 + int(np.argmax(st[1:, 4]))).astype(np.uint8)
    # fill holes: flood the background from the border, anything not reached is inside
    ff = keep.copy()
    pad = np.pad(ff, 1)
    cv2.floodFill(pad, None, (0, 0), 2)
    return (pad[1:-1, 1:-1] != 2)


# rembg's own default model is RMBG-2.0, which is CC BY-NC. Always name the model.
REMBG_MODEL = "isnet-general-use"
_sessions = {}


def rembg_mask(rgb, model):
    from rembg import new_session, remove
    if model not in _sessions:
        _sessions[model] = new_session(model)
    a = np.asarray(remove(Image.fromarray(rgb), session=_sessions[model], only_mask=True))
    return largest_filled((a > 127).astype(np.uint8))


def get_mask(path, matte=None, key=False, model=REMBG_MODEL):
    if matte:
        return np.asarray(Image.open(matte).convert("L")) > 127, {"source": "matte", "path": matte}
    rgba = load_rgba(path)
    if has_alpha(rgba):
        return largest_filled((rgba[..., 3] > 127).astype(np.uint8)), {"source": "alpha"}
    if key:
        m, info = key_mask(rgba[..., :3])
        return m, {"source": "key", **info}
    return rembg_mask(rgba[..., :3], model), {"source": "rembg", "model": model}


def bbox(m):
    ys, xs = np.nonzero(m)
    return int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())


# ------------------------------------------------------------------------- keypoints

_wb = None


def wholebody():
    global _wb
    if _wb is None:
        from rtmlib import Wholebody
        _wb = Wholebody(mode="balanced", backend="onnxruntime", device="cpu")
    return _wb


def landmarks(path):
    rgb = load_rgba(path)[..., :3]
    kps, sc = wholebody()(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if len(kps) == 0:
        return None
    i = int(np.argmax(sc.mean(1)))
    k, s = kps[i], sc[i]
    pts = {n: [round(float(k[j][0]), 1), round(float(k[j][1]), 1), round(float(s[j]), 2)]
           for n, j in KP.items()}
    face = k[FACE][s[FACE] >= MIN_SCORE]
    out = {"keypoints": pts, "persons": int(len(kps))}
    if len(face) >= 10:
        x0, y0 = face.min(0)
        x1, y1 = face.max(0)
        cx, cy, side = (x0 + x1) / 2, (y0 + y1) / 2, 1.6 * max(x1 - x0, y1 - y0)
        out["head_box"] = [round(float(v), 1) for v in (cx - side / 2, cy - side * 0.6, side, side)]
        out["eye_dist_px"] = round(float(np.hypot(*(k[1] - k[2]))), 1)
    return out


def _kp(lm, name):
    p = lm["keypoints"][name]
    return None if p[2] < MIN_SCORE else (p[0], p[1])


def proportions(mask, lm):
    """Height-normalised ratios. Every value uses the same rule on both images, so
    the deltas are comparable even where the landmark is a proxy (leg = hip joint
    to ankle, not a tailor's inseam)."""
    top, bot, _, _ = bbox(mask)
    H = float(bot - top)
    g = lambda n: _kp(lm, n)
    p = {}
    sl, sr, hl, hr = g("shoulder_l"), g("shoulder_r"), g("hip_l"), g("hip_r")
    if g("chin"):
        p["head_height"] = (g("chin")[1] - top) / H
    if sl and sr:
        p["shoulder_width"] = abs(sl[0] - sr[0]) / H
        p["shoulder_y"] = ((sl[1] + sr[1]) / 2 - top) / H
    if hl and hr:
        p["hip_joint_width"] = abs(hl[0] - hr[0]) / H
        p["hip_y"] = ((hl[1] + hr[1]) / 2 - top) / H
    if sl and sr and hl and hr:
        p["torso_length"] = p["hip_y"] - p["shoulder_y"]
        # waist: narrowest body run between shoulders and hips, measured on the run
        # that contains the hip midpoint column (arms hanging free are excluded)
        cx = int(round((hl[0] + hr[0]) / 2))
        y0 = int((sl[1] + sr[1]) / 2 + 0.25 * (hl[1] - sl[1]))
        y1 = int((hl[1] + hr[1]) / 2)
        widths = [w for w in (_run_width(mask[y], cx) for y in range(y0, y1)) if w]
        if widths:
            p["waist_width"] = min(widths) / H
            yh = np.arange(y1, min(int(y1 + 0.1 * H), mask.shape[0]))
            hw = [w for w in (_run_width(mask[y], cx) for y in yh) if w]
            if hw:
                p["hip_width"] = max(hw) / H
    al, ar = g("ankle_l"), g("ankle_r")
    if hl and hr and al and ar:
        p["leg_length"] = ((al[1] + ar[1]) / 2 - (hl[1] + hr[1]) / 2) / H
    return {k: round(v, 4) for k, v in p.items()}


def _run_width(row, cx):
    if cx < 0 or cx >= len(row) or not row[cx]:
        return None
    l = cx
    while l > 0 and row[l - 1]:
        l -= 1
    r = cx
    while r < len(row) - 1 and row[r + 1]:
        r += 1
    return r - l + 1


# --------------------------------------------------------------------------- compare

def align_to(src, ref):
    """Scale/translate src so its bbox height, top and centre-x match ref's."""
    t0, b0, l0, r0 = bbox(src)
    t1, b1, l1, r1 = bbox(ref)
    s = (b1 - t1) / max(b0 - t0, 1)
    M = np.float32([[s, 0, (l1 + r1) / 2 - s * (l0 + r0) / 2],
                    [0, s, t1 - s * t0]])
    out = cv2.warpAffine(src.astype(np.uint8) * 255, M, (ref.shape[1], ref.shape[0]),
                         flags=cv2.INTER_LINEAR)
    return out > 127


def iou(a, b):
    return float((a & b).sum() / max((a | b).sum(), 1))


def boundary_distance(a, b):
    """Symmetric contour distance in px: mean and p95."""
    def contour(m):
        return m & ~cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    ca, cb = contour(a), contour(b)
    da = cv2.distanceTransform((~ca).astype(np.uint8), cv2.DIST_L2, 5)
    db = cv2.distanceTransform((~cb).astype(np.uint8), cv2.DIST_L2, 5)
    d = np.concatenate([db[ca], da[cb]])
    return float(d.mean()), float(np.percentile(d, 95))


def compare(ref, render, ref_matte=None, render_matte=None, overlay=None, key=False,
            model=REMBG_MODEL):
    mr, ir = get_mask(ref, ref_matte, key, model)
    mn, inn = get_mask(render, render_matte, key, model)
    out = {"ref": ref, "render": render, "ref_mask": ir, "render_mask": inn}
    t, b, _, _ = bbox(mr)
    H = b - t
    if mr.shape == mn.shape:
        out["iou_raw"] = round(iou(mr, mn), 4)
        tn, bn, ln, rn = bbox(mn)
        _, _, l, r = bbox(mr)
        out["framing_error_px"] = {"top": tn - t, "bottom": bn - b,
                                   "center_x": round((ln + rn - l - r) / 2, 1)}
    else:
        out["iou_raw"] = None
        out["framing_error_px"] = f"sizes differ {mr.shape[::-1]} vs {mn.shape[::-1]}"
    al = align_to(mn, mr)
    out["iou_aligned"] = round(iou(mr, al), 4)
    mean, p95 = boundary_distance(mr, al)
    out["boundary_mean_pct_h"] = round(100 * mean / H, 3)
    out["boundary_p95_pct_h"] = round(100 * p95 / H, 3)

    lr, ln_ = landmarks(ref), landmarks(render)
    if lr and ln_:
        pr, pn = proportions(mr, lr), proportions(mn, ln_)
        out["proportions_ref"], out["proportions_render"] = pr, pn
        out["proportion_deltas"] = {k: round(pn[k] - pr[k], 4) for k in pr if k in pn}
    else:
        out["proportions_ref"] = out["proportions_render"] = out["proportion_deltas"] = None
        out["warning"] = "no person detected in " + ("ref" if not lr else "render")

    if overlay:
        # white = both, red = reference only, cyan = render only
        vis = np.zeros(mr.shape + (3,), np.uint8)
        vis[mr & al] = (235, 235, 235)
        vis[mr & ~al] = (230, 40, 40)
        vis[~mr & al] = (40, 210, 230)
        Image.fromarray(vis).save(overlay)
        out["overlay"] = overlay
    return out


# ------------------------------------------------------------------------ calibrate

def calibrate(config_paths):
    """A fail line from 2D art only: how close another character's reference
    silhouette comes to this one. A mesh that matches its own reference no better
    than a different character does has failed. There is deliberately no pass
    line -- that would need same-character examples, and renders of existing
    meshes are never used to set thresholds. A pass line is a user tolerance
    (config `tolerances`), recorded as such."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import config as cfg
    chars = [cfg.load(p) for p in config_paths]
    refs = {c["character"]: cfg.refs_of(c, "full_body_front")[0] for c in chars}
    rows = []
    for a_name, a_ref in refs.items():
        for b_name, b_ref in refs.items():
            if a_name == b_name:
                continue
            r = compare(a_ref["path"], b_ref["path"], ref_matte=a_ref.get("matte"),
                        render_matte=b_ref.get("matte"))
            rows.append({"ref": a_name, "impostor": b_name, "iou_aligned": r["iou_aligned"],
                         "boundary_mean_pct_h": r["boundary_mean_pct_h"],
                         "abs_deltas": {k: abs(v) for k, v in (r["proportion_deltas"] or {}).items()}})
    if not rows:
        return {"characters": list(refs), "calibrated": False,
                "reason": "need full-body references of at least two characters"}

    def stats(vals):
        v = np.array(vals)
        return {"n": len(v), "min": round(float(v.min()), 4), "median": round(float(np.median(v)), 4),
                "max": round(float(v.max()), 4)}
    ious = [r["iou_aligned"] for r in rows]
    bds = [r["boundary_mean_pct_h"] for r in rows]
    return {
        "characters": list(refs), "basis": "2D full-body references of other characters",
        "iou_aligned": {"impostors": stats(ious), "fail_at": round(max(ious), 4), "higher_is_same": True,
                        "calibrated": True, "pass_at": None},
        "boundary_mean_pct_h": {"impostors": stats(bds), "fail_at": round(min(bds), 4),
                                "higher_is_same": False, "calibrated": True, "pass_at": None},
        # Characters of one style often share proportions, so impostor deltas make no
        # fail line here: proportions gate only against a user tolerance.
        "proportions_impostor_deltas": {k: stats([r["abs_deltas"][k] for r in rows if k in r["abs_deltas"]])
                                        for k in sorted({k for r in rows for k in r["abs_deltas"]})},
        "note": "impostor refs in a different pose than the character's ref give a lenient fail line",
        "rows": rows,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("matte")
    m.add_argument("image")
    m.add_argument("--matte")
    m.add_argument("--out")
    l = sub.add_parser("landmarks")
    l.add_argument("image")
    c = sub.add_parser("compare")
    c.add_argument("ref")
    c.add_argument("render")
    c.add_argument("--ref-matte")
    c.add_argument("--render-matte")
    c.add_argument("--overlay")
    k = sub.add_parser("calibrate")
    k.add_argument("--config", action="append", required=True)
    k.add_argument("--out")
    for p_ in (m, c):
        p_.add_argument("--key", action="store_true", help="border-colour key instead of rembg")
        p_.add_argument("--model", default=REMBG_MODEL, help="rembg model")
    a = ap.parse_args()

    # Libraries print progress to stdout (rtmlib model loads, rembg downloads);
    # stdout carries only the final JSON.
    real_stdout, sys.stdout = sys.stdout, sys.stderr
    try:
        r_ = run(a)
    finally:
        sys.stdout = real_stdout
    print(json.dumps(r_, indent=2))


def run(a):
    if a.cmd == "matte":
        mask, info = get_mask(a.image, a.matte, a.key, a.model)
        t, b, l_, r = bbox(mask)
        if a.out:
            Image.fromarray(mask.astype(np.uint8) * 255).save(a.out)
        r_ = {"image": a.image, **info, "bbox": {"top": t, "bottom": b, "left": l_, "right": r},
              "coverage": round(float(mask.mean()), 4), "out": a.out}
    elif a.cmd == "landmarks":
        r_ = landmarks(a.image) or {"error": "no person detected"}
    elif a.cmd == "calibrate":
        r_ = calibrate(a.config)
        if a.out:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(json.dumps(r_, indent=2))
            r_ = {k: v for k, v in r_.items() if k != "rows"} | {"written": a.out}
    else:
        r_ = compare(a.ref, a.render, a.ref_matte, a.render_matte, a.overlay, a.key, a.model)
    return r_


if __name__ == "__main__":
    main()
