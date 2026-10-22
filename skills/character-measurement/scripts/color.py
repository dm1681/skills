# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy>=2", "opencv-python>=4.10", "pillow>=10", "scikit-image>=0.24",
#                 "rtmlib>=0.0.16", "onnxruntime>=1.20", "rembg>=2.0.60"]
# ///
"""Per-region colour comparison between a reference and a render framed alike
(gate.py's solved full-body front shot). Prints one JSON object.

  color.py compare REF RENDER [--swatches out.png]

Regions come from each image's own body keypoints, so they match by anatomy, not
by pixel position: face (eyes to chin), torso (below the chest, between the
shoulders), thigh_l, thigh_r. No hair region: keypoint boxes cannot find hair. Each region is
intersected with the foreground matte; its colour is the median CIELAB.

Per region: dE2000 on full Lab, and d_chroma on a*b* only. The reference is lit
however the artist lit it and the render uses the locked studio rig, so
lightness differences are partly lighting: read d_chroma first for "wrong
colour", dE for "wrong overall". To split albedo from lighting, compare again
against a `--look flat` render (unlit base colour). Report-only: never
calibrated, never gating.
"""
import argparse
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from skimage.color import deltaE_ciede2000, rgb2lab

sys.path.insert(0, str(Path(__file__).resolve().parent))
import silhouette  # noqa: E402


def regions(lm, shape):
    """Boxes (x0, y0, x1, y1) per region from keypoints; None where a keypoint is missing."""
    k = lambda n: silhouette._kp(lm, n)
    h, w = shape
    out = {}
    el, er, chin = k("eye_l"), k("eye_r"), k("chin")
    if el and er and chin:
        ex0, ex1 = sorted((el[0], er[0]))
        ey = (el[1] + er[1]) / 2
        fh = chin[1] - ey
        out["face"] = (ex0, ey + 0.15 * fh, ex1, chin[1] - 0.1 * fh)
        # No hair region: hair placement varies too much for keypoint boxes (they
        # land on forehead, ears or empty space). Hair needs semantic masks.
    sl, sr, hl, hr = k("shoulder_l"), k("shoulder_r"), k("hip_l"), k("hip_r")
    if sl and sr and hl and hr:
        x0, x1 = sorted((sl[0], sr[0]))
        sy, hy = (sl[1] + sr[1]) / 2, (hl[1] + hr[1]) / 2
        out["torso"] = (x0 + 0.3 * (x1 - x0), sy + 0.55 * (hy - sy), x1 - 0.3 * (x1 - x0), sy + 0.85 * (hy - sy))
        for side, hip, knee in (("l", hl, k("knee_l")), ("r", hr, k("knee_r"))):
            if knee:
                cx, cy = (hip[0] + knee[0]) / 2, (hip[1] + knee[1]) / 2
                hw, hh = 0.125 * abs(hl[0] - hr[0]), 0.15 * abs(knee[1] - hip[1])
                out[f"thigh_{side}"] = (cx - hw, cy - hh, cx + hw, cy + hh)
    clip = lambda b: (max(0, int(b[0])), max(0, int(b[1])), min(w, int(b[2])), min(h, int(b[3])))
    return {n: clip(b) for n, b in out.items()}


def region_lab(rgb, mask, box):
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        return None, 0
    px = rgb[y0:y1, x0:x1][mask[y0:y1, x0:x1]]
    if len(px) < 20:
        return None, int(len(px))
    lab = rgb2lab(px.reshape(-1, 1, 3).astype(np.float64) / 255.0).reshape(-1, 3)
    return np.median(lab, axis=0), int(len(px))


def compare(ref, render, swatches=None):
    data = {}
    for name, path in (("ref", ref), ("render", render)):
        rgb = np.asarray(Image.open(path).convert("RGB"))
        mask, _ = silhouette.get_mask(path)
        lm = silhouette.landmarks(path)
        data[name] = (rgb, mask, regions(lm, mask.shape) if lm else {})
    out = {"ref": ref, "render": render, "regions": {},
           "note": "report-only; read d_chroma for hue/saturation, dE2000 for overall"}
    for reg in sorted(set(data["ref"][2]) & set(data["render"][2])):
        a, na = region_lab(data["ref"][0], data["ref"][1], data["ref"][2][reg])
        b, nb = region_lab(data["render"][0], data["render"][1], data["render"][2][reg])
        if a is None or b is None:
            out["regions"][reg] = {"skipped": "too few foreground pixels", "px": [na, nb]}
            continue
        out["regions"][reg] = {
            "ref_lab": [round(float(v), 1) for v in a], "render_lab": [round(float(v), 1) for v in b],
            "dE2000": round(float(deltaE_ciede2000(a, b)), 2),
            "d_chroma": round(float(np.hypot(a[1] - b[1], a[2] - b[2])), 2),
            "dL": round(float(b[0] - a[0]), 1), "px": [na, nb]}
    if swatches:
        rows = [(r, v) for r, v in out["regions"].items() if "ref_lab" in v]
        img = Image.new("RGB", (420, 40 * max(len(rows), 1)), (18, 18, 22))
        d = ImageDraw.Draw(img)
        from skimage.color import lab2rgb
        for i, (r, v) in enumerate(rows):
            for j, key in enumerate(("ref_lab", "render_lab")):
                c = lab2rgb(np.array(v[key], dtype=float).reshape(1, 1, 3)).reshape(3)
                d.rectangle([110 + j * 70, i * 40 + 4, 170 + j * 70, i * 40 + 36],
                            fill=tuple(int(round(255 * x)) for x in c))
            d.text((8, i * 40 + 14), r, fill=(230, 230, 235))
            d.text((260, i * 40 + 14), f"dE {v['dE2000']}  dC {v['d_chroma']}", fill=(230, 230, 235))
        img.save(swatches)
        out["swatches"] = swatches
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare")
    c.add_argument("ref")
    c.add_argument("render")
    c.add_argument("--swatches")
    a = ap.parse_args()
    with redirect_stdout(sys.stderr):
        r = compare(a.ref, a.render, a.swatches)
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
