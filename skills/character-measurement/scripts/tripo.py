# /// script
# requires-python = ">=3.12"
# dependencies = ["requests>=2.31"]
# ///
"""Generate 3D models with the Tripo API (V3) and keep the provenance beside them.
The key comes from the TRIPO_API_KEY environment variable and is never printed.
Every command prints one JSON object to stdout.

  tripo.py balance
  tripo.py image-to-model IMAGE --out DIR [options]
  tripo.py multiview-to-model --front F [--left L] [--back B] [--right R] --out DIR [options]
  tripo.py task TASK_ID --out DIR        resume: poll an existing task and download it

Options (generation):
  --model ID               default v3.1-20260211 (H3.1); P1-20260311 / P2-20260801 for low-poly
  --texture-quality Q      fast | standard | detailed (default) | extreme (8K, extra credits)
  --geometry-quality Q     standard (default) | detailed (Ultra, finer geometry)
  --face-limit N           cap the polycount (default: adaptive)
  --model-seed N / --texture-seed N   reproducible geometry / texture
  --no-pbr                 base colour only (default: PBR maps)
  --autofix                let Tripo enhance a weak input image first
  --timeout SEC            polling limit (default 1200)

Writes into DIR: <stem>_<task>.glb, <stem>_<task>_preview.png, and
<stem>_<task>.json (inputs with their SHA-256, every request parameter, the task
record, credits consumed, balance before and after). Output URLs expire after
about 5 minutes, so the model is downloaded the moment the task succeeds.

Tripo exports X-forward by default: gate the result with front axis +X.
Each call spends credits (about 30-50 for a textured model); `balance` first.
Content moderation runs at submission (code 2008): a rejected image costs nothing,
but revealing outfits can be rejected even where Tripo Studio accepted them.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import requests

BASE = "https://openapi.tripo3d.ai/v3"
DONE = {"success", "failed", "cancelled", "banned", "expired"}


class TripoError(RuntimeError):
    pass


def key():
    k = os.environ.get("TRIPO_API_KEY")
    if not k and sys.platform == "win32":
        # A user variable set after this shell started is in the registry only.
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
                k = winreg.QueryValueEx(h, "TRIPO_API_KEY")[0]
        except OSError:
            k = None
    if not k:
        raise TripoError("TRIPO_API_KEY is not set")
    return k


def call(method, path, *, json_body=None, files=None, retries=5):
    """One API call with backoff on 429/5xx. Raises TripoError with Tripo's code."""
    url = path if path.startswith("http") else BASE + path
    for attempt in range(retries):
        r = requests.request(method, url, headers={"Authorization": f"Bearer {key()}"},
                             json=json_body, files=files, timeout=120)
        if r.status_code == 429 or r.status_code >= 500:
            wait = int(r.headers.get("Retry-After", 0)) or 2 ** attempt
            time.sleep(min(wait, 60))
            continue
        try:
            body = r.json()
        except ValueError:
            raise TripoError(f"HTTP {r.status_code}: non-JSON response")
        if r.status_code != 200 or body.get("code") != 0:
            raise TripoError(f"HTTP {r.status_code} code {body.get('code')}: {body.get('message')}"
                             + (f" ({body['suggestion']})" if body.get("suggestion") else ""))
        return body["data"]
    raise TripoError(f"{method} {path}: still rate-limited after {retries} attempts")


def balance():
    return call("GET", "/account/balance")


def upload(path):
    with open(path, "rb") as f:
        return call("POST", "/files", files={"file": (Path(path).name, f)})["file_token"]


def portable(path):
    """Records may be committed: keep paths relative to where the command ran."""
    try:
        return Path(path).resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def poll(task_id, timeout):
    t0 = time.time()
    while True:
        task = call("GET", f"/tasks/{task_id}")
        if task.get("status") in DONE:
            return task
        if time.time() - t0 > timeout:
            raise TripoError(f"task {task_id} still {task.get('status')} after {timeout}s; "
                             f"resume with: tripo.py task {task_id} --out DIR")
        time.sleep(2)   # the docs ask for at most one query per second


def download(url, dest):
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return str(dest)


def finish(task, out_dir, stem, record):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tid = task["task_id"].replace("task_", "")[:12]
    result = {"task_id": task["task_id"], "status": task.get("status"),
              "credits_consumed": task.get("credits_consumed"), "files": {}}
    if task.get("status") == "success":
        output = task.get("output") or {}
        if output.get("model_url"):
            ext = Path(output["model_url"].split("?")[0]).suffix or ".glb"
            result["files"]["model"] = download(output["model_url"], out_dir / f"{stem}_{tid}{ext}")
        if output.get("rendered_image_url"):
            result["files"]["preview"] = download(output["rendered_image_url"],
                                                  out_dir / f"{stem}_{tid}_preview.png")
    else:
        result["error"] = {"code": task.get("error_code"), "message": task.get("error_message")}
        if task.get("status") == "banned":
            result["error"]["hint"] = "content policy rejected the input; change the image"
    record = {**record, "task": {k: v for k, v in task.items() if k != "output"},
              "result": result}
    try:
        record["balance_after"] = balance()
    except TripoError as e:
        record["balance_after"] = f"unavailable: {e}"
    rec_path = out_dir / f"{stem}_{tid}.json"
    rec_path.write_text(json.dumps(record, indent=2))
    result["record"] = str(rec_path)
    result["balance_after"] = record["balance_after"]
    return result


def gen_params(a):
    p = {"model": a.model, "texture": True, "pbr": not a.no_pbr,
         "texture_quality": a.texture_quality, "geometry_quality": a.geometry_quality,
         "enable_image_autofix": a.autofix}
    if a.face_limit:
        p["face_limit"] = a.face_limit
    if a.model_seed is not None:
        p["model_seed"] = a.model_seed
    if a.texture_seed is not None:
        p["texture_seed"] = a.texture_seed
    if a.model.startswith("v2"):
        p.pop("geometry_quality")   # the docs: never with v2.5
    return p


def generate(a):
    before = balance()
    params = gen_params(a)
    if a.cmd == "image-to-model":
        inputs = {"image": a.image}
        body = {**params, "input": upload(a.image)}
        endpoint, stem = "/generation/image-to-model", Path(a.image).stem
    else:
        inputs = {v: getattr(a, v) for v in ("front", "left", "back", "right") if getattr(a, v)}
        if len(inputs) < 2:
            raise TripoError("multiview needs the front view plus at least one more")
        body = {**params, "inputs": [{v: upload(p)} for v, p in inputs.items()]}
        endpoint, stem = "/generation/multiview-to-model", Path(a.front).stem + "_mv"
    task_id = call("POST", endpoint, json_body=body)["task_id"]
    record = {"endpoint": endpoint, "params": params,
              "inputs": {k: {"path": portable(v), "sha256": sha256(v)} for k, v in inputs.items()},
              "balance_before": before, "export_orientation": "+x (Tripo default)"}
    return finish(poll(task_id, a.timeout), a.out, stem, record)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("balance")
    i = sub.add_parser("image-to-model")
    i.add_argument("image")
    m = sub.add_parser("multiview-to-model")
    for v in ("front", "left", "back", "right"):
        m.add_argument(f"--{v}", required=(v == "front"))
    t = sub.add_parser("task")
    t.add_argument("task_id")
    for p in (i, m, t):
        p.add_argument("--out", required=True)
        p.add_argument("--timeout", type=int, default=1200)
    for p in (i, m):
        p.add_argument("--model", default="v3.1-20260211")
        p.add_argument("--texture-quality", default="detailed",
                       choices=("fast", "standard", "detailed", "extreme"))
        p.add_argument("--geometry-quality", default="standard", choices=("standard", "detailed"))
        p.add_argument("--face-limit", type=int)
        p.add_argument("--model-seed", type=int)
        p.add_argument("--texture-seed", type=int)
        p.add_argument("--no-pbr", action="store_true")
        p.add_argument("--autofix", action="store_true")
    a = ap.parse_args()
    try:
        if a.cmd == "balance":
            out = balance()
        elif a.cmd == "task":
            out = finish(poll(a.task_id, a.timeout), a.out, a.task_id.replace("task_", "t"),
                         {"resumed": True})
        else:
            out = generate(a)
    except (TripoError, requests.RequestException) as e:
        out = {"error": str(e)}
        if "code 2008" in str(e):
            # Rejected at submission, so nothing was charged. Revealing outfits and
            # suggestive poses trip the filter even when Studio once accepted them.
            out["hint"] = ("content policy rejected the input image (no credits charged); "
                           "try a more covered outfit or a different view of the character")
        print(json.dumps(out, indent=2))
        sys.exit(1)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
