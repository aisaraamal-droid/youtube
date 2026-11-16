#!/usr/bin/env python3
"""Generate clips through BytePlus ModelArk (Seedance 2.0 mini, 480p).

Auth is injected by the environment proxy (Authorization header), so no key is
read or stored here. Never print or commit keys.

Usage:
  seedance.py submit SPEC.json CLIP_ID [CLIP_ID ...]   # submit tasks, write tasks/<id>.json
  seedance.py wait   CLIP_ID [CLIP_ID ...]             # poll until done, download mp4, print usage
"""
import base64, json, mimetypes, os, sys, time
import requests

BASE = "https://ark.ap-southeast.bytepluses.com/api/v3/contents/generations/tasks"
MODEL = "dreamina-seedance-2-0-mini-260615"
HERE = os.getcwd()  # run from the project folder; outputs go to ./tasks ./clips ./work
TASKS = os.path.join(HERE, "tasks")
CLIPS = os.path.join(HERE, "clips")
os.makedirs(TASKS, exist_ok=True)
os.makedirs(CLIPS, exist_ok=True)


def data_uri(path):
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def submit(spec, clip_id):
    clip = next(c for c in spec["clips"] if c["id"] == clip_id)
    content = [{"type": "text", "text": spec["style"].strip() + "\n\n" + clip["prompt"].strip()}]
    for ref in spec["refs"] + clip.get("extra_refs", []):  # extra_refs: per-clip images (e.g. Rico)
        content.append({
            "type": "image_url",
            "image_url": {"url": data_uri(os.path.join(HERE, ref))},
            "role": "reference_image",
        })
    body = {
        "model": MODEL,
        "content": content,
        "resolution": "480p",
        "ratio": "9:16",
        "duration": clip["duration"],
        "generate_audio": clip.get("audio", True),
        "watermark": False,
    }
    r = requests.post(BASE, json=body, timeout=120)
    print(clip_id, "submit", r.status_code, r.text[:400])
    r.raise_for_status()
    tid = r.json()["id"]
    with open(os.path.join(TASKS, f"{clip_id}.json"), "w") as f:
        json.dump({"task_id": tid, "clip": clip, "submitted": time.time()}, f)


def wait(clip_id):
    meta = json.load(open(os.path.join(TASKS, f"{clip_id}.json")))
    tid = meta["task_id"]
    while True:
        r = requests.get(f"{BASE}/{tid}", timeout=60)
        r.raise_for_status()
        d = r.json()
        st = d.get("status")
        if st in ("succeeded", "failed", "cancelled", "expired"):
            break
        time.sleep(10)
    with open(os.path.join(TASKS, f"{clip_id}.result.json"), "w") as f:
        json.dump(d, f, indent=1)
    if st != "succeeded":
        print(clip_id, st, json.dumps(d.get("error")))
        return None
    url = d["content"]["video_url"]
    out = os.path.join(CLIPS, f"{clip_id}.mp4")
    v = requests.get(url, timeout=300)
    v.raise_for_status()
    open(out, "wb").write(v.content)
    print(clip_id, "ok", out, "usage:", json.dumps(d.get("usage")), "dur:", d.get("duration"),
          "res:", d.get("resolution"), "ratio:", d.get("ratio"), "audio:", d.get("generate_audio"))
    return out


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "submit":
        spec = json.load(open(sys.argv[2]))
        for cid in sys.argv[3:]:
            submit(spec, cid)
    elif cmd == "wait":
        for cid in sys.argv[2:]:
            wait(cid)
