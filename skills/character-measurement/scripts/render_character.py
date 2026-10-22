"""Reproducible character renders for measurement. Runs inside Blender:

  blender -b --factory-startup -P render_character.py -- MODEL OUTDIR [options]

  --mode fullbody|head          default fullbody
  --views front,q_left,...      front q_left left back right q_right; append @DEG to
                                turn the camera a further DEG (front@2 = 2 deg toward
                                the character's left) -- used to measure score noise
                                (fullbody default: front; head default: front,q_left,q_right)
  --front-axis=-Y|+Y|+X|-X      direction the character faces in the file (default -Y);
                                write it with "=": argparse reads a bare -Y as a flag
  --res WxH                     default 1024x1024
  --lens MM                     default 85
  --look studio|clay|flat       studio = file materials + fixed light rig;
                                clay = geometry only; flat = unlit base colour
  --samples N                   default 64
  --tag NAME                    output prefix (default: model file stem)

  fullbody framing
  --target-bbox TOP,BOTTOM,CX   solve the camera so the silhouette's top row, bottom
                                row and centre column land here (px). Take them from
                                the reference matte: silhouette.py matte REF.
  --fill F                      without --target-bbox: silhouette fills F of the frame
                                height (default 0.9)
  --cam-height F                camera height as a fraction of character height
                                (default 0.5); the camera never tilts

  head framing
  --head-z TOP,CHIN             head top and chin as fractions of character height.
                                Without it a 7.5-heads default is used and the JSON
                                says so -- pass keypoint-derived values (gate.py does).
  --head-fill F                 head (top to chin) fills F of the frame height (0.6)

Outputs <tag>_<mode>_<view>.png (RGBA, transparent background) and <tag>_<mode>.json
with everything needed to reproduce the shot: camera, solve residual, normalisation.

View names: the camera orbits toward the character's own left for q_left/left, so in
q_left/left the nose points image-LEFT. Check a reference's nose direction, not its
file name, when you pair it with a view.
"""
import argparse
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

AZ = {"front": 0.0, "q_left": 45.0, "left": 90.0, "back": 180.0, "right": -90.0, "q_right": -45.0}
FRONT_ROT = {"-Y": 0.0, "+X": -90.0, "-X": 90.0, "+Y": 180.0}   # rotate about Z to face -Y
TARGET_H = 1.75
SENSOR_H = 24.0
DEFAULT_CHIN = 1.0 - 1.0 / 7.5
HEAD_TOP_MARGIN = 0.08
# camera-relative rig (camera looks along +Y from -Y): key, fill, rim
RIG = [("key", (2.5, -2.5, 2.5), 600.0), ("fill", (-2.5, -1.5, 1.5), 260.0), ("rim", (0.5, 3.0, 2.2), 420.0)]


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="render_character.py")
    ap.add_argument("model")
    ap.add_argument("outdir")
    ap.add_argument("--mode", choices=("fullbody", "head"), default="fullbody")
    ap.add_argument("--views")
    ap.add_argument("--front-axis", choices=tuple(FRONT_ROT), default="-Y")
    ap.add_argument("--res", default="1024x1024")
    ap.add_argument("--lens", type=float, default=85.0)
    ap.add_argument("--look", choices=("studio", "clay", "flat"), default="studio")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--tag")
    ap.add_argument("--target-bbox")
    ap.add_argument("--fill", type=float, default=0.9)
    ap.add_argument("--cam-height", type=float, default=0.5)
    ap.add_argument("--head-z")
    ap.add_argument("--head-fill", type=float, default=0.6)
    a = ap.parse_args(argv)
    a.res = tuple(int(v) for v in a.res.lower().split("x"))
    a.views = (a.views or ("front" if a.mode == "fullbody" else "front,q_left,q_right")).split(",")
    bad = [v for v in a.views if v.partition("@")[0] not in AZ]
    if bad:
        raise SystemExit(f"unknown view(s) {bad}; use {sorted(AZ)}")
    a.tag = a.tag or os.path.splitext(os.path.basename(a.model))[0]
    return a


# ------------------------------------------------------------------------------ scene

def import_model(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=path)
        # A file saved in Edit/Texture Paint mode breaks later operators.
        for o in list(bpy.context.view_layer.objects):
            if o.mode != "OBJECT":
                bpy.context.view_layer.objects.active = o
                try:
                    bpy.ops.object.mode_set(mode="OBJECT")
                except RuntimeError:
                    pass
        for o in bpy.context.scene.objects:      # the file's own rig never renders
            if o.type in ("LIGHT", "CAMERA"):
                o.hide_render = True
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise SystemExit("unsupported model type " + ext)


def render_meshes(sc):
    return [o for o in sc.objects if o.type == "MESH" and not o.hide_render and o.visible_get()]


def world_verts(sc):
    dg = bpy.context.evaluated_depsgraph_get()
    chunks = []
    for o in render_meshes(sc):
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        n = len(me.vertices)
        if n:
            co = np.empty(n * 3, np.float64)
            me.vertices.foreach_get("co", co)
            M = np.array(ev.matrix_world)
            chunks.append(co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3])
        ev.to_mesh_clear()
    if not chunks:
        raise SystemExit("no renderable mesh")
    return np.concatenate(chunks)


def normalise(sc, front_axis):
    """Parent everything under one root, face -Y, scale to TARGET_H, feet on z=0,
    centred on x/y. Rigs are shown in rest pose (the bind pose is what the mesh
    gates compare). Returns the final world-space vertices."""
    for o in sc.objects:
        if o.type == "ARMATURE":
            o.data.pose_position = "REST"
    root = bpy.data.objects.new("CM_ROOT", None)
    sc.collection.objects.link(root)
    for o in [o for o in sc.objects if o.parent is None and o is not root
              and o.type not in ("CAMERA", "LIGHT")]:
        mw = o.matrix_world.copy()
        o.parent = root
        o.matrix_world = mw
    bpy.context.view_layer.update()
    V0 = world_verts(sc)
    ang = math.radians(FRONT_ROT[front_axis])
    R = np.array([[math.cos(ang), -math.sin(ang), 0], [math.sin(ang), math.cos(ang), 0], [0, 0, 1]])
    V1 = V0 @ R.T
    s = TARGET_H / (V1[:, 2].max() - V1[:, 2].min())
    V2 = V1 * s
    t = np.array([-(V2[:, 0].min() + V2[:, 0].max()) / 2,
                  -(V2[:, 1].min() + V2[:, 1].max()) / 2, -V2[:, 2].min()])
    root.rotation_euler = (0, 0, ang)
    root.scale = (s, s, s)
    root.location = Vector(t)
    bpy.context.view_layer.update()
    return V2 + t, {"front_axis": front_axis, "scale": round(float(s), 6), "height_m": TARGET_H,
                    "vertices": int(len(V0))}


def apply_look(sc, look):
    def mat(name):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        return m
    if look == "clay":
        clay = mat("CM_clay")
        b = clay.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.62, 0.60, 0.58, 1)
        b.inputs["Roughness"].default_value = 0.42
        for o in render_meshes(sc):
            o.data.materials.clear()
            o.data.materials.append(clay)
    elif look == "flat":
        for o in render_meshes(sc):
            for m in o.data.materials:
                if not m or not m.node_tree:
                    continue
                nt = m.node_tree
                out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
                tex = next((n for n in nt.nodes if n.type == "TEX_IMAGE" and n.image), None)
                if not out:
                    continue
                em = nt.nodes.new("ShaderNodeEmission")
                if tex:
                    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
                else:
                    em.inputs["Color"].default_value = (0.8, 0.8, 0.8, 1)
                nt.links.new(em.outputs["Emission"], out.inputs["Surface"])


def setup_render(sc, a):
    world = bpy.data.worlds.new("CM_world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = \
        (0, 0, 0, 1) if a.look == "flat" else (0.05, 0.05, 0.06, 1)
    sc.world = world
    sc.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        sc.cycles.device = "GPU"
    except Exception as e:  # CPU fallback renders the same image, slower
        print("[RC] GPU setup failed, using CPU:", e)
    sc.cycles.samples = a.samples
    sc.cycles.seed = 0
    sc.cycles.use_denoising = True
    sc.render.film_transparent = True
    sc.render.resolution_x, sc.render.resolution_y = a.res
    sc.render.resolution_percentage = 100
    sc.render.pixel_aspect_x = sc.render.pixel_aspect_y = 1
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.image_settings.color_depth = "8"
    # Standard, not AgX/Filmic: those wash out product renders and shift colour.
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    sc.view_settings.gamma = 1.0
    sc.display_settings.display_device = "sRGB"


# ----------------------------------------------------------------------------- camera

def azimuth(view):
    name, _, off = view.partition("@")
    return AZ[name] + float(off or 0.0)


class Rig:
    def __init__(self, sc, lens):
        cd = bpy.data.cameras.new("CM_cam")
        cd.lens = lens
        cd.sensor_fit = "VERTICAL"
        cd.sensor_height = SENSOR_H
        cd.clip_start, cd.clip_end = 0.01, 1000.0
        self.cam = bpy.data.objects.new("CM_cam", cd)
        sc.collection.objects.link(self.cam)
        sc.camera = self.cam
        self.sc = sc
        self.lights = []
        for name, _, _ in RIG:
            L = bpy.data.lights.new("CM_" + name, "AREA")
            ob = bpy.data.objects.new("CM_" + name, L)
            sc.collection.objects.link(ob)
            self.lights.append(ob)

    def place(self, view, dist, zc, pivot=(0.0, 0.0), look="studio"):
        a = math.radians(azimuth(view))
        px, py = pivot
        self.cam.location = (px + math.sin(a) * dist, py - math.cos(a) * dist, zc)
        self.cam.rotation_euler = Vector((px - self.cam.location.x, py - self.cam.location.y, 0.0)) \
            .to_track_quat("-Z", "Y").to_euler()
        # The light rig turns with the camera: every view is lit the same way.
        k = max(dist / 3.2, 0.12)
        for ob, (_, off, energy) in zip(self.lights, RIG):
            x, y, z = off
            rx, ry = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
            ob.location = Vector((px, py, zc)) + Vector((rx, ry, z)) * k
            ob.rotation_euler = Vector((rx, ry, z)).to_track_quat("Z", "Y").to_euler()
            ob.data.energy = 0.0 if look == "flat" else energy * k * k
            ob.data.size = 3.0 * k
        bpy.context.view_layer.update()

    def project(self, V, res):
        dg = bpy.context.evaluated_depsgraph_get()
        P = np.array(self.cam.calc_matrix_camera(dg, x=res[0], y=res[1]))
        W = np.array(self.cam.matrix_world.inverted())
        h = np.c_[V, np.ones(len(V))] @ (P @ W).T
        ndc = h[:, :2] / h[:, 3:4]
        return (ndc[:, 0] + 1) / 2 * res[0], (1 - ndc[:, 1]) / 2 * res[1]


def solve_fullbody(rig, view, V, a, target):
    """Distance + lens shift so the projected silhouette hits (top, bottom, cx).
    The camera stays level: verticals stay vertical, like a turnaround sheet."""
    res = a.res
    T, B, CX = target
    zc = a.cam_height * TARGET_H
    f_px = a.lens / SENSOR_H * res[1]
    d = TARGET_H * f_px / (B - T)
    cd = rig.cam.data
    cd.shift_x = cd.shift_y = 0.0

    def measure():
        rig.place(view, d, zc, look=a.look)
        u, v = rig.project(V, res)
        return v.min(), v.max(), (u.min() + u.max()) / 2

    it, err = 0, None
    for it in range(1, 16):
        top, bot, cx = measure()
        d *= (bot - top) / (B - T)
        top, bot, cx = measure()
        # shift is linear in pixel offset: measure the slope once per iteration
        e_y, e_x = (top + bot) / 2 - (T + B) / 2, cx - CX
        cd.shift_y += 0.01
        t2, b2, c2 = measure()
        dv = ((t2 + b2) / 2 - (top + bot) / 2) / 0.01
        cd.shift_y -= 0.01
        cd.shift_x += 0.01
        t3, b3, c3 = measure()
        du = (c3 - cx) / 0.01
        cd.shift_x -= 0.01
        cd.shift_y -= e_y / dv if dv else 0.0
        cd.shift_x -= e_x / du if du else 0.0
        top, bot, cx = measure()
        err = {"top": round(top - T, 2), "bottom": round(bot - B, 2), "center_x": round(cx - CX, 2)}
        if max(abs(v) for v in err.values()) < 0.5:
            break
    return {"distance_m": round(d, 4), "camera_z_m": round(zc, 4), "iterations": it,
            "residual_px": err, "target_px": {"top": T, "bottom": B, "center_x": CX}}


def frame_head(rig, view, V, a, head_z):
    top_n, chin_n = head_z
    z_top, z_chin = top_n * TARGET_H, chin_n * TARGET_H
    head_h = z_top - z_chin
    band = V[(V[:, 2] >= z_chin) & (V[:, 2] <= z_top)]
    pivot = (float(np.median(band[:, 0])), float(np.median(band[:, 1])))
    F = head_h / a.head_fill
    zc = z_top + HEAD_TOP_MARGIN * F - F / 2
    d = (F / 2) / ((SENSOR_H / 2) / a.lens)
    rig.cam.data.shift_x = rig.cam.data.shift_y = 0.0
    rig.place(view, d, zc, pivot, look=a.look)
    return {"distance_m": round(d, 4), "camera_z_m": round(zc, 4), "pivot_xy": [round(v, 4) for v in pivot],
            "head_height_m": round(head_h, 4), "frame_height_m": round(F, 4)}


def main():
    a = parse()
    import_model(os.path.abspath(a.model))
    sc = bpy.context.scene
    V, norm = normalise(sc, a.front_axis)
    apply_look(sc, a.look)
    setup_render(sc, a)
    rig = Rig(sc, a.lens)
    os.makedirs(a.outdir, exist_ok=True)

    info = {"model": os.path.abspath(a.model), "mode": a.mode, "look": a.look, "res": list(a.res),
            "lens_mm": a.lens, "sensor_height_mm": SENSOR_H, "samples": a.samples,
            "view_transform": "Standard", "blender": bpy.app.version_string,
            "normalisation": norm, "views": {}}
    if a.mode == "head":
        if a.head_z:
            head_z = tuple(float(v) for v in a.head_z.split(","))
            info["head_z"] = {"top": head_z[0], "chin": head_z[1], "source": "--head-z"}
        else:
            head_z = (1.0, DEFAULT_CHIN)
            info["head_z"] = {"top": 1.0, "chin": round(DEFAULT_CHIN, 4), "source": "default-7.5-heads",
                              "warning": "head bounds guessed; pass --head-z from keypoints"}
    for view in a.views:
        if a.mode == "fullbody":
            if a.target_bbox:
                target = tuple(float(v) for v in a.target_bbox.split(","))
                T, B, CX = target
                if not (0 <= T < B <= a.res[1] and 0 <= CX <= a.res[0]):
                    raise SystemExit(f"--target-bbox {a.target_bbox} lies outside a {a.res[0]}x{a.res[1]} "
                                     "frame: measure the box at the render resolution")
            else:
                m = a.res[1] * (1 - a.fill) / 2
                target = (m, a.res[1] - m, a.res[0] / 2)
            shot = solve_fullbody(rig, view, V, a, target)
            if max(abs(v) for v in shot["residual_px"].values()) > 1.0:
                raise SystemExit(f"camera solve did not converge for {view}: {shot['residual_px']}")
        else:
            shot = frame_head(rig, view, V, a, head_z)
        cd = rig.cam.data
        shot.update({"shift_x": round(cd.shift_x, 6), "shift_y": round(cd.shift_y, 6),
                     "location": [round(v, 4) for v in rig.cam.location],
                     "azimuth_deg": azimuth(view)})
        path = os.path.join(os.path.abspath(a.outdir), f"{a.tag}_{a.mode}_{view}.png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        shot["file"] = path
        info["views"][view] = shot
        print("[RC]", path)
    js = os.path.join(os.path.abspath(a.outdir), f"{a.tag}_{a.mode}.json")
    with open(js, "w") as f:
        json.dump(info, f, indent=2)
    print("[RC] JSON", js)
    print("[RC] DONE")


main()
