# ENTRY POINT pyodide
import UnityPy

from .generate import build_patchdata, patchdata_to_json
from . import lzf


def run(path):
    env = UnityPy.load(path)
    logs = []
    patchdata = build_patchdata(env, log=logs.append)
    clips = patchdata["animationDatabase"]["patchedAnimations"]
    if not clips:
        raise ValueError("no patchable anims wtf")
    js = patchdata_to_json(patchdata).encode("utf-8")
    data = lzf.compress(js)
    return {
        "bytes": data,
        "clips": len(clips),
        "curves": sum(len(c["curves"]) for c in clips),
        "size": len(data),
        "log": logs,
    }
