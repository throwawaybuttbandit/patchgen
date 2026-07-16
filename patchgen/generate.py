# generator code

import json

import UnityPy

from . import lzf
from .core import build_tos, decode_clip

GAME_BUILD_VERSION = 26
PRECISION = 100000


def _noop(*_):
    pass

# Mathf.RoundToInt
def _encode(v):
    return int(round(v * PRECISION))

# fixed point encode 1 single raw curve, collapse any curve that is constant (if more than 2 frames and all values equal)
# to just their 1st and last keyframe
def _encode_curve(curve):
    times = [_encode(t) for t in curve["times"]]
    values = [_encode(v) for v in curve["values"]]

    if len(values) > 2 and all(v == values[0] for v in values):
        times = [times[0], times[-1]]
        values = [values[0], values[-1]]

    return {
        "relativePath": curve["relativePath"],
        "propertyName": curve["propertyName"],
        "times": times,
        "values": values,
    }

# decode every clip by an AnimatorController into raw patchdata
def build_patchdata(env, log=_noop):
    tos = build_tos(env)

    # path_id -> (meta, curve_raw)
    clip_cache = {}
    for o in env.objects:
        if o.type.name != "AnimationClip":
            continue
        tt = o.read_typetree()
        try:
            clip_cache[o.path_id] = decode_clip(tt, tos)
        except Exception as e: 
            log(f"** cant decode clip {tt.get('m_Name')}: {e}")

    patched = []
    controllers = 0
    for o in env.objects:
        if o.type.name != "AnimatorController":
            continue
        controllers += 1
        ctt = o.read_typetree()
        controller_name = ctt.get("m_Name")

        for ref in ctt.get("m_AnimationClips", []) or []:
            pid = ref.get("m_PathID") if isinstance(ref, dict) else None
            if pid not in clip_cache:
                continue

            meta, curves = clip_cache[pid]

            encoded = [_encode_curve(c) for c in curves]

            patched.append({
                "controllerName": controller_name,
                "clipName": meta["clipName"],
                "frameRate": meta["frameRate"],
                "wrapMode": meta["wrapMode"],
                "curves": encoded,
            })

            log(f"* {controller_name}/{meta['clipName']}: {len(encoded)} curves")

    log(f"* controllers {controllers} patchedAnimations {len(patched)}")
    return {
        "version": GAME_BUILD_VERSION,
        "animationDatabase": {"patchedAnimations": patched},
    }

# turn it to compact json
def patchdata_to_json(patchdata):
    return json.dumps(patchdata, separators=(",", ":"), ensure_ascii=False)

# returns compressed patched bytes and patchdata dict
def generate_patch_bytes(rfc_path, log=_noop):
    env = UnityPy.load(rfc_path)
    patchdata = build_patchdata(env, log=log)
    if not patchdata["animationDatabase"]["patchedAnimations"]:
        # theres nothing for me to patch, or something went wrong idk
        raise ValueError("cant find patchable anims")
    payload = patchdata_to_json(patchdata).encode("utf-8")
    return lzf.compress(payload), patchdata

def generate_patch_file(rfc_path, out_path=None, log=_noop):
    if out_path is None:
        out_path = rfc_path + ".patch"

    data, patchdata = generate_patch_bytes(rfc_path, log=log)

    with open(out_path, "wb") as f:
        f.write(data)
    return out_path, patchdata
