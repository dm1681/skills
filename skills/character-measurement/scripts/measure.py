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
"""Score renders of a character against reference art, and renders against each
other. Every command prints one JSON object to stdout.

  measure.py compare REF RENDER [--tier 4|1] [--bg R,G,B]
      tier 4 (default, head-scale): faces found by YuNet, aligned to the ArcFace
        template; EdgeFace identity cosine (higher = same) and DreamSim on the face
        crop (lower = closer). Needs >= 40 px between the eyes in both images.
      tier 1 (matched scale): REF and RENDER are full-body images framed alike.
        The face is located by body keypoints, not face detection, cropped from
        both at the same pixel size, and compared with DreamSim (identity only
        if detection still works on the crop). Use tier-1 thresholds only.
      Both tiers also report DreamSim on the full frame (report-only).

  measure.py diff BEFORE AFTER [--mask M.png] [--map heat.png]
      Spatial LPIPS between two renders from the same camera: mean, p99, the
      worst-1% hotspots, and with --mask how much of the change lies outside the
      region the pass was meant to touch.

  measure.py calibrate --config A.json --config B.json ... [--tier 4|1] [--face-px N]
      Same-character pairs (within one character's 2D reference art) against
      different-character pairs (across characters). Reports both distributions,
      whether they separate, the lookalike band between them, and a threshold.
      Inputs are each config's references plus calibration.images: 2D art only,
      never renders of existing meshes. Tier 4 uses the images with >= 40 px
      between the eyes; --tier 1 crops every image's face by keypoints and
      degrades it to N px (the face size in the full-body reference), so
      full-body refs count and the numbers apply at that scale.

Images with alpha are composited onto --bg so background colour does not leak
into a score; pass the reference's background colour.
"""
import argparse
import json
import sys
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config as cfg  # noqa: E402
import silhouette  # noqa: E402

CACHE = Path.home() / ".cache" / "character-measurement"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# torch 2.11's hub fork check does `del headers["Authorization"]` on a dict that
# only has the key when GITHUB_TOKEN is set, so every unauthenticated hub.load
# raises KeyError. DreamSim loads its backbones through hub and can't skip it.
torch.hub._validate_not_a_forked_repo = lambda *a, **k: None

YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")

# ArcFace 112x112 template: image-left eye, image-right eye, nose, image-left and
# image-right mouth corners -- the order YuNet emits.
ARCFACE_TEMPLATE = np.array([
    [38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
    [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float32)

# Below this inter-ocular distance the aligned crop is mostly upsampling and
# head-scale identity stops meaning anything.
MIN_EYE_DIST = 40.0


def log(*a):
    print(*a, file=sys.stderr)


def load_rgb(path, bg=(0, 0, 0)):
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        im = Image.alpha_composite(Image.new("RGBA", im.size, bg + (255,)), im)
    return np.asarray(im.convert("RGB"))


# ----------------------------------------------------------------------------- faces

_detector = None


def detector():
    global _detector
    if _detector is None:
        CACHE.mkdir(parents=True, exist_ok=True)
        onnx = CACHE / "face_detection_yunet_2023mar.onnx"
        if not onnx.exists():
            log("downloading YuNet face detector")
            urllib.request.urlretrieve(YUNET_URL, onnx)
        _detector = cv2.FaceDetectorYN.create(str(onnx), "", (320, 320), 0.6, 0.3, 50)
    return _detector


def face_info(rgb):
    h, w = rgb.shape[:2]
    det = detector()
    det.setInputSize((w, h))
    _, faces = det.detect(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if faces is None or len(faces) == 0:
        return None
    f = max(faces, key=lambda r: r[2] * r[3])
    lmk = f[4:14].reshape(5, 2).astype(np.float32)
    return {"score": round(float(f[14]), 3), "box": [round(float(v)) for v in f[:4]],
            "eye_dist_px": round(float(np.linalg.norm(lmk[1] - lmk[0])), 1), "lmk": lmk}


def align_face(rgb, lmk):
    m, _ = cv2.estimateAffinePartial2D(lmk, ARCFACE_TEMPLATE, method=cv2.LMEDS)
    return cv2.warpAffine(rgb, m, (112, 112), borderValue=0)


def landmark_crop(rgb, lmk, size=224):
    """Square crop around the 5 landmarks, wide enough for brows, chin and ears."""
    c = lmk.mean(axis=0)
    half = 1.6 * max(np.ptp(lmk[:, 0]), np.ptp(lmk[:, 1]))
    return box_crop(rgb, (c[0] - half, c[1] - half * 0.9, 2 * half, 2 * half), size)


def box_crop(rgb, box, size):
    x, y, w, h = [int(round(v)) for v in box]
    pad = max(0, -x, -y, x + w - rgb.shape[1], y + h - rgb.shape[0])
    if pad:
        rgb = cv2.copyMakeBorder(rgb, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
        x, y = x + pad, y + pad
    crop = rgb[y:y + h, x:x + w]
    interp = cv2.INTER_AREA if crop.shape[0] > size else cv2.INTER_CUBIC
    return cv2.resize(crop, (size, size), interpolation=interp)


def degrade(rgb, px):
    """Down to px then back up: the information a px-sized face actually holds."""
    small = cv2.resize(rgb, (px, px), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (224, 224), interpolation=cv2.INTER_CUBIC)


_edgeface = None


def edgeface():
    global _edgeface
    if _edgeface is None:
        torch.hub.set_dir(str(CACHE / "hub"))
        _edgeface = torch.hub.load("otroshi/edgeface", "edgeface_base", source="github",
                                   pretrained=True, trust_repo=True,
                                   skip_validation=True).to(DEVICE).eval()
    return _edgeface


@torch.no_grad()
def embed(aligned):
    x = torch.from_numpy(aligned).permute(2, 0, 1).float().div(255).sub(0.5).div(0.5)
    return torch.nn.functional.normalize(edgeface()(x.unsqueeze(0).to(DEVICE)), dim=-1)[0]


_dreamsim = None


@torch.no_grad()
def dreamsim(a, b):
    global _dreamsim
    if _dreamsim is None:
        from dreamsim import dreamsim as ds
        _dreamsim = ds(pretrained=True, device=DEVICE, cache_dir=str(CACHE / "dreamsim"))
    model, prep = _dreamsim
    return float(model(prep(Image.fromarray(a)).to(DEVICE),
                       prep(Image.fromarray(b)).to(DEVICE)).item())


# ------------------------------------------------------------------------- compare

def identity_from_crops(ca, cb):
    """Identity on two face crops, if YuNet can still find both faces."""
    fa, fb = face_info(ca), face_info(cb)
    if not (fa and fb):
        return None
    return round(float(embed(align_face(ca, fa["lmk"])) @ embed(align_face(cb, fb["lmk"]))), 4)


def compare(ref_path, render_path, tier=4, bg=(0, 0, 0)):
    ref, ren = load_rgb(ref_path, bg), load_rgb(render_path, bg)
    out = {"ref": str(ref_path), "render": str(render_path), "tier": tier,
           "dreamsim_full": round(dreamsim(ref, ren), 4)}
    warnings = []
    if ref.shape[:2] != ren.shape[:2]:
        warnings.append("sizes differ; dreamsim_full also measures framing")

    if tier == 4:
        fr, fn = face_info(ref), face_info(ren)
        out["face_ref"] = {k: v for k, v in fr.items() if k != "lmk"} if fr else None
        out["face_render"] = {k: v for k, v in fn.items() if k != "lmk"} if fn else None
        if fr and fn:
            out["dreamsim_face"] = round(dreamsim(landmark_crop(ref, fr["lmk"]),
                                                  landmark_crop(ren, fn["lmk"])), 4)
            out["identity_cosine"] = round(float(embed(align_face(ref, fr["lmk"]))
                                                 @ embed(align_face(ren, fn["lmk"]))), 4)
            small = [n for n, f in (("ref", fr), ("render", fn)) if f["eye_dist_px"] < MIN_EYE_DIST]
            if small:
                warnings.append(f"face below {MIN_EYE_DIST:.0f} px eye distance in "
                                f"{', '.join(small)}: head-scale thresholds do not apply; use --tier 1")
        else:
            out["dreamsim_face"] = out["identity_cosine"] = None
            warnings.append("no face detected in " + ", ".join(
                n for n, f in (("ref", fr), ("render", fn)) if f is None))
    else:
        lr, ln = silhouette.landmarks(ref_path), silhouette.landmarks(render_path)
        if not (lr and ln and "head_box" in lr and "head_box" in ln):
            out["dreamsim_face"] = out["identity_cosine"] = None
            warnings.append("no head box from keypoints")
        else:
            # Compare at the smaller face's real resolution: never invent detail
            # one side doesn't have.
            px = int(min(lr["head_box"][2], ln["head_box"][2]))
            ca = degrade(box_crop(ref, lr["head_box"], max(px, 8)), max(px, 8))
            cb = degrade(box_crop(ren, ln["head_box"], max(px, 8)), max(px, 8))
            out["face_px"] = px
            out["eye_dist_px"] = {"ref": lr.get("eye_dist_px"), "render": ln.get("eye_dist_px")}
            out["dreamsim_face"] = round(dreamsim(ca, cb), 4)
            out["identity_cosine"] = identity_from_crops(ca, cb)
    out["warnings"] = warnings
    return out


_lpips = None


@torch.no_grad()
def diff(before_path, after_path, mask_path=None, map_path=None, bg=(0, 0, 0)):
    global _lpips
    import lpips
    if _lpips is None:
        _lpips = lpips.LPIPS(net="alex", spatial=True, verbose=False).to(DEVICE).eval()
    a, b = load_rgb(before_path, bg), load_rgb(after_path, bg)
    if a.shape != b.shape:
        raise SystemExit(f"diff needs identical framing: {a.shape} vs {b.shape}")

    def t(x):
        return torch.from_numpy(x).permute(2, 0, 1).float().div(127.5).sub(1).unsqueeze(0).to(DEVICE)

    m = _lpips(t(a), t(b))[0, 0].cpu().numpy()
    hot = m >= np.percentile(m, 99)
    out = {"before": str(before_path), "after": str(after_path),
           "lpips_mean": round(float(m.mean()), 5), "lpips_p99": round(float(np.percentile(m, 99)), 5)}
    if mask_path:
        mask = np.asarray(Image.open(mask_path).convert("L").resize(m.shape[::-1])) > 127
        out.update({
            "mask": str(mask_path), "mask_frac": round(float(mask.mean()), 4),
            "lpips_in_mask": round(float(m[mask].mean()), 5) if mask.any() else None,
            "lpips_outside_mask": round(float(m[~mask].mean()), 5) if (~mask).any() else None,
            # share of the worst-1% pixels that fall outside the targeted region
            "hot_outside_mask_frac": round(float((hot & ~mask).sum() / max(hot.sum(), 1)), 4),
        })
    n, _, stats, _ = cv2.connectedComponentsWithStats(hot.astype(np.uint8), connectivity=8)
    out["hotspots"] = [{"x": int(x), "y": int(y), "w": int(w), "h": int(h), "px": int(px)}
                       for x, y, w, h, px in sorted(stats[1:], key=lambda s: -s[4])[:5]]
    if map_path:
        norm = np.clip(m / max(float(np.percentile(m, 99.5)), 1e-6), 0, 1)
        heat = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
        bgr = cv2.cvtColor(b, cv2.COLOR_RGB2BGR)
        Path(map_path).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(map_path), np.hstack([bgr, cv2.addWeighted(bgr, 0.45, heat, 0.55, 0)]))
        out["map"] = str(map_path)
    return out


# ------------------------------------------------------------------------ calibrate

def portable(path):
    try:
        return Path(path).resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)


def calibrate(config_paths, tier=4, face_px=None):
    if tier == 1 and not face_px:
        raise SystemExit("--tier 1 needs --face-px: the face box size in the full-body reference "
                         "(silhouette.py landmarks REF -> head_box[2])")
    items, missing = [], []
    for cp in config_paths:
        c = cfg.load(cp)
        for p in cfg.calibration_art(c):
            (items if Path(p).exists() else missing).append((c["character"], p))
    faces = {}
    for char, p in items:
        rgb = load_rgb(p)
        if tier == 1:
            # Exactly the tier-1 compare pipeline: keypoint head box, then the
            # crop degraded to the full-body face size.
            lm = silhouette.landmarks(p)
            if not (lm and "head_box" in lm):
                log(f"no head box: {p}")
                continue
            crop = degrade(box_crop(rgb, lm["head_box"], 224), face_px)
            ff = face_info(crop)
            emb = embed(align_face(crop, ff["lmk"])) if ff else None
            faces[p] = (char, lm.get("eye_dist_px", 0.0), emb, crop)
            continue
        f = face_info(rgb)
        if f is None:
            log(f"no face: {p}")
            continue
        faces[p] = (char, f["eye_dist_px"], embed(align_face(rgb, f["lmk"])),
                    landmark_crop(rgb, f["lmk"]))

    pairs = []
    keys = list(faces)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            ca, ea, ma, ka = faces[keys[i]]
            cb, eb, mb, kb = faces[keys[j]]
            pairs.append({"a": keys[i], "b": keys[j], "same": ca == cb, "chars": [ca, cb],
                          "identity_cosine": (round(float(ma @ mb), 4)
                                              if ma is not None and mb is not None else None),
                          "dreamsim_face": round(dreamsim(ka, kb), 4),
                          "min_eye_dist_px": min(ea, eb)})
    usable = [p for p in pairs if tier == 1 or p["min_eye_dist_px"] >= MIN_EYE_DIST]

    def summary(metric, higher_is_same):
        same = np.array([p[metric] for p in usable if p["same"] and p[metric] is not None])
        diff_ = np.array([p[metric] for p in usable if not p["same"] and p[metric] is not None])
        if not len(same) or not len(diff_):
            return {"calibrated": False, "reason": "need both same- and different-character pairs"}
        st = lambda a: {"n": len(a), "min": round(float(a.min()), 4),
                        "median": round(float(np.median(a)), 4), "max": round(float(a.max()), 4)}
        s = {"same": st(same), "different": st(diff_)}
        if higher_is_same:
            weakest_true, closest_impostor = float(same.min()), float(diff_.max())
            sep = weakest_true > closest_impostor
        else:
            weakest_true, closest_impostor = float(same.max()), float(diff_.min())
            sep = weakest_true < closest_impostor
        s.update({"separated": bool(sep), "calibrated": bool(sep),
                  "pass_at": round(weakest_true, 4), "fail_at": round(closest_impostor, 4),
                  "threshold": round((weakest_true + closest_impostor) / 2, 4),
                  "higher_is_same": higher_is_same})
        if not sep:
            s["reason"] = "distributions overlap: add pairs or do not gate on this metric"
        return s

    chars = sorted({c for c, _ in items})
    # Calibration files get committed: record paths relative to where the
    # command ran (run it from the project root), never machine-local ones.
    for p in pairs:
        p["a"], p["b"] = portable(p["a"]), portable(p["b"])
    out = {"tier": tier, "face_px": face_px, "characters": chars,
           "images_used": len(faces), "missing_inputs": [portable(p) for _, p in missing],
           "pairs_scored": len(usable), "pairs_excluded_small_face": len(pairs) - len(usable),
           "identity_cosine": summary("identity_cosine", True),
           "dreamsim_face": summary("dreamsim_face", False),
           "pairs": sorted(usable, key=lambda p: (p["same"], p["dreamsim_face"]))}
    if len(chars) < 2:
        out["warning"] = "only one character: no impostors, nothing can be calibrated"
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare")
    c.add_argument("ref")
    c.add_argument("render")
    c.add_argument("--tier", type=int, choices=(1, 4), default=4)
    d = sub.add_parser("diff")
    d.add_argument("before")
    d.add_argument("after")
    d.add_argument("--mask")
    d.add_argument("--map")
    k = sub.add_parser("calibrate")
    k.add_argument("--config", action="append", required=True)
    k.add_argument("--tier", type=int, choices=(1, 4), default=4)
    k.add_argument("--face-px", type=int)
    k.add_argument("--out")
    for p in (c, d):
        p.add_argument("--bg", default="0,0,0")
    a = ap.parse_args()

    # Libraries print progress to stdout; stdout carries only the final JSON.
    with redirect_stdout(sys.stderr):
        bg = tuple(int(v) for v in getattr(a, "bg", "0,0,0").split(","))
        if a.cmd == "compare":
            r = compare(a.ref, a.render, a.tier, bg)
        elif a.cmd == "diff":
            r = diff(a.before, a.after, a.mask, a.map, bg)
        else:
            r = calibrate(a.config, a.tier, a.face_px)
            if a.out:
                Path(a.out).parent.mkdir(parents=True, exist_ok=True)
                Path(a.out).write_text(json.dumps(r, indent=2))
                r = {k_: v for k_, v in r.items() if k_ != "pairs"} | {"written": a.out}
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
