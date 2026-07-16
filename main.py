import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patchgen.generate import generate_patch_file


def _expand(paths):
    # wow isnt it great we can glob
    out = []
    for p in paths:
        out.extend(glob.glob(p) or [p])
    return out

# ret int int, count patchdata curves
def _count_curves(patchdata):
    clips = patchdata["animationDatabase"]["patchedAnimations"]
    return len(clips), sum(len(c["curves"]) for c in clips)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="patchgen",
        description="patchfile generation for <=ea25 rfcs")
    ap.add_argument("rfc", nargs="+", help="rfcs")
    ap.add_argument("-o", "--output", help="output path (opt)")
    ap.add_argument("-q", "--quiet", action="store_true", help="only print results")
    args = ap.parse_args(argv)

    inputs = _expand(args.rfc)
    if args.output and len(inputs) != 1:
        ap.error("-o/--output can only be used with a single input dude")
    # whatever bro
    log = (lambda *_: None) if args.quiet else print

    rc = 0
    for rfc in inputs:
        if not os.path.isfile(rfc):
            # wtf is this dude
            print(f"* skipping {rfc}", file=sys.stderr)
            rc = 1
            continue
        print(f"* patching {rfc}")
        try:
            out_path, patchdata = generate_patch_file(rfc, args.output, log=log)
        except Exception as e:
            print(f"** err: {e}", file=sys.stderr)
            rc = 1
            continue
        n_clips, n_curves = _count_curves(patchdata)
        size = os.path.getsize(out_path)
        print(f"* wrote {out_path}  ({n_clips} clips, {n_curves} curves, {size} bytes)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
