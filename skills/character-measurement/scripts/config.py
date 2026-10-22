"""Per-character measurement config: which references exist and what each is for.

One JSON file per character, kept in the project (not in the skill). Relative paths
resolve against the config file's directory. See references/config.md.
"""
import json
from pathlib import Path

# kind -> (render mode, render view). The gates a config gets follow from which
# kinds it lists; full_body_front is the only required one.
KINDS = {
    "full_body_front": ("fullbody", "front"),
    "full_body_back": ("fullbody", "back"),
    "head_front": ("head", "front"),
    "head_q_left": ("head", "q_left"),
    "head_q_right": ("head", "q_right"),
    "head_side_left": ("head", "left"),
    "head_side_right": ("head", "right"),
    "head_back": ("head", "back"),
    "head_front_derived": ("head", "front"),
    "expression": (None, None),
}
FRONT_AXES = ("-Y", "+Y", "+X", "-X")


class ConfigError(ValueError):
    pass


def load(path):
    path = Path(path).resolve()
    c = json.loads(path.read_text(encoding="utf-8"))
    base = path.parent

    def res(p):
        return str((base / p).resolve()) if p else None

    for key in ("character", "references"):
        if key not in c:
            raise ConfigError(f"{path.name}: missing '{key}'")
    c["front_axis"] = c.get("front_axis", "-Y")
    if c["front_axis"] not in FRONT_AXES:
        raise ConfigError(f"{path.name}: front_axis must be one of {FRONT_AXES}")
    refs = []
    for r in c["references"]:
        kind = r.get("kind")
        if kind not in KINDS:
            raise ConfigError(f"{path.name}: unknown reference kind {kind!r}; use one of {sorted(KINDS)}")
        if kind == "head_front_derived" and not r.get("approved_by"):
            raise ConfigError(f"{path.name}: a derived head reference needs 'approved_by' "
                              "(the user approves it after it passes the tier-1 check)")
        mode, view = KINDS[kind]
        refs.append({**r, "path": res(r["path"]), "matte": res(r.get("matte")),
                     "mode": mode, "view": r.get("view", view)})
    if not any(r["kind"] == "full_body_front" for r in refs):
        raise ConfigError(f"{path.name}: every character needs a full_body_front reference")
    c["references"] = refs
    cal = c.get("calibration", {})
    files = cal.get("files", {})
    unknown = set(files) - {"tier4", "tier1", "shape"}
    if unknown:
        raise ConfigError(f"{path.name}: calibration.files keys are tier4, tier1, shape; got {sorted(unknown)}")
    if "shape_renders" in cal:
        raise ConfigError(f"{path.name}: calibration.shape_renders is not supported -- thresholds are "
                          "never calibrated on renders of existing meshes, which are what is being improved")
    c["calibration"] = {
        # Extra front-facing 2D art of this character, beyond `references`. Never
        # a render or capture of an existing mesh.
        "images": [res(p) for p in cal.get("images", [])],
        # calibration outputs this character is gated against (shared per art style)
        "files": {k: res(v) for k, v in files.items()},
    }
    tol = c.get("tolerances")
    if tol is not None and not tol.get("set_by"):
        raise ConfigError(f"{path.name}: tolerances are a user decision, not a calibration -- "
                          "record who set them in tolerances.set_by")
    c["tolerances"] = tol or {}
    c["render"] = {"lens": 85.0, "cam_height": 0.5, **c.get("render", {})}
    c["evidence_root"] = res(c.get("evidence_root", "measure-out"))
    c["config_path"] = str(path)
    return c


def refs_of(c, *kinds):
    return [r for r in c["references"] if r["kind"] in kinds]


# Calibration pairs must look like the comparisons the gates make, and every gate
# compares a view with the same view; front-facing art is what every character has.
CALIBRATION_KINDS = ("full_body_front", "head_front", "expression")


def calibration_art(c):
    """The 2D images of this character that may set a threshold: front-facing
    references (never a derived head ref, which carries the generator's drift)
    plus calibration.images, which must be front-facing 2D art too."""
    seen, out = set(), []
    for p in [r["path"] for r in c["references"] if r["kind"] in CALIBRATION_KINDS] +             c["calibration"]["images"]:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out
