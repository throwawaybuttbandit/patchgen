# core animation stuff
import binascii
import math
import struct

FLT_MAX = 3.4e38

ATTR_POSITION = 1
ATTR_SCALE = 3
ATTR_ROTATION = 4  # euler angles in deg


# vector3 attribs
VECTOR3_AXES = {
    ATTR_POSITION: "localPosition",
    ATTR_SCALE: "localScale",
}


def p(x):
    return struct.pack("<I", x & 0xFFFFFFFF)


def up(b):
    return struct.unpack("<f", b)[0]

# reinterpret a uint32 to a f32
def _u32_to_f32(x):
    return up(p(x))

def _crc32(s):
    return binascii.crc32(s.encode("utf-8")) & 0xFFFFFFFF


# given (t, v), build curve dict
def _curve(path, prop, samples):
    return {
        "relativePath": path,
        "propertyName": prop,
        "times": [t for t, _ in samples],
        "values": [v for _, v in samples],
    }


# bone path resolvers

# builds a crc32(path) to path map to resolve path hashes to bone paths
# animator path hashes are just crc32s of the path that are relative to the animator root
def build_tos(env):
    objs = list(env.objects)

    # path_id -> name, parent path_id
    transforms = {}
    for o in objs:

        if o.type.name != "Transform":
            continue

        tt = o.read_typetree()
        go = tt.get("m_GameObject", {})
        go_pid = go.get("m_PathID", 0) if isinstance(go, dict) else 0
        name = None

        if go_pid:
            try:
                name = o.assets_file.files[go_pid].read_typetree().get("m_Name")
            except Exception:
                name = None
        
        father = tt.get("m_Father", {})
        parent_id = father.get("m_PathID", 0) if isinstance(father, dict) else 0
        transforms[o.path_id] = {"name": name, "parent": parent_id}
    # names from this node up to root
    def path_segments(pid):
        segs = []
        seen = set()
        while pid and pid in transforms and pid not in seen:
            seen.add(pid)
            name = transforms[pid]["name"]
            if not name:
                break
            segs.append(name)
            pid = transforms[pid]["parent"]
        segs.reverse()
        return segs

    hmap = {0: ""}
    for pid in transforms:
        segs = path_segments(pid)
        for i in range(len(segs)):  # hash the suffix
            path = "/".join(segs[i:])
            hmap.setdefault(_crc32(path), path)

    # deal with Avatar last
    for o in objs:
        if o.type.name != "Avatar":
            continue
        for e in o.read_typetree().get("m_TOS", []):
            if isinstance(e, dict):
                hmap[e["first"]] = e["second"]
            else:
                hmap[e[0]] = e[1]
    return hmap


# i didnt write this part if you couldnt tell
def _quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def euler_to_quat_zyx(x_deg, y_deg, z_deg):
    hx, hy, hz = (math.radians(a) * 0.5 for a in (x_deg, y_deg, z_deg))
    qx = (math.sin(hx), 0.0, 0.0, math.cos(hx))
    qy = (0.0, math.sin(hy), 0.0, math.cos(hy))
    qz = (0.0, 0.0, math.sin(hz), math.cos(hz))
    return _quat_mul(qz, _quat_mul(qy, qx))

# fix sampling problem attempt #2
def _sample_at(samples, t):
    if t <= samples[0][0]:
        return samples[0][1]
    if t >= samples[-1][0]:
        return samples[-1][1]
    for k in range(len(samples) - 1):
        t0, v0 = samples[k]
        t1, v1 = samples[k + 1]
        if t <= t1:
            r = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            return v0 + (v1 - v0) * r
    return samples[-1][1]


def _rotation_curves(path, euler_x, euler_y, euler_z):
    times = sorted({t for s in (euler_x, euler_y, euler_z) for t, _ in s})
    components = ([], [], [], [])  # x, y, z, w
    prev = None
    for t in times:
        ex = _sample_at(euler_x, t)
        ey = _sample_at(euler_y, t)
        ez = _sample_at(euler_z, t)
        q = euler_to_quat_zyx(ex, ey, ez)
        if prev is not None and sum(a * b for a, b in zip(q, prev)) < 0:
            q = tuple(-c for c in q)
        prev = q
        for comp, value in zip(components, q):
            comp.append(value)

    axes = ("localRotation.x", "localRotation.y", "localRotation.z", "localRotation.w")
    return [
        {"relativePath": path, "propertyName": prop, "times": times, "values": values}
        for prop, values in zip(axes, components)
    ]


def _parse_streamed(u32):
    per = {}
    clamp = {}
    pos, n = 0, len(u32)
    while pos < n:
        time = _u32_to_f32(u32[pos])
        count = u32[pos + 1]
        pos += 2
        real = abs(time) < FLT_MAX and math.isfinite(time)
        for _ in range(count):
            idx = u32[pos]
            coeffs = (
                _u32_to_f32(u32[pos + 1]),
                _u32_to_f32(u32[pos + 2]),
                _u32_to_f32(u32[pos + 3]),
                _u32_to_f32(u32[pos + 4]),
            )
            pos += 5
            if real:
                per.setdefault(idx, []).append((time, coeffs))
            else:
                clamp.setdefault(idx, coeffs[3])
    for segs in per.values():
        segs.sort()
    return per, clamp


def _resample_segments(segs, rate):
    out = []
    for k in range(len(segs) - 1):
        t0, c0 = segs[k]
        t1 = segs[k + 1][0]
        out.append((t0, c0[3]))
        moving = abs(c0[0]) > 1e-9 or abs(c0[1]) > 1e-9 or abs(c0[2]) > 1e-9
        steps = int(round((t1 - t0) * rate)) if moving and rate > 0 else 0
        for s in range(1, steps):
            dt = (t1 - t0) * s / steps
            out.append((t0 + dt, ((c0[0] * dt + c0[1]) * dt + c0[2]) * dt + c0[3]))
    out.append((segs[-1][0], segs[-1][1][3]))
    return out


def _decode_scalar_curves(clipd, start_time, stop_time, fallback_rate):
    scalars = {}

    dense = clipd["m_DenseClip"]
    dense_rate = dense["m_SampleRate"]

    streamed = clipd["m_StreamedClip"]
    stream_count = streamed["curveCount"]
    per, clamp = _parse_streamed(streamed["data"])
    srate = dense_rate if dense_rate > 0 else fallback_rate
    for idx, segs in per.items():
        scalars[idx] = _resample_segments(segs, srate)
    for idx, val in clamp.items():
        if idx not in scalars:
            scalars[idx] = [(start_time, val), (stop_time, val)]

    dense_count = dense["m_CurveCount"]
    frame_count = dense["m_FrameCount"]
    rate = dense["m_SampleRate"]
    begin = dense["m_BeginTime"]
    samples = dense["m_SampleArray"]
    for f in range(frame_count):
        t = begin + f / rate
        base = f * dense_count
        for c in range(dense_count):
            scalars.setdefault(stream_count + c, []).append((t, samples[base + c]))

    # constantclip, one const float per curve, keep their own frame span
    const = clipd["m_ConstantClip"]["data"]
    rate = rate or fallback_rate
    const_end = frame_count / rate if frame_count else stop_time
    for c in range(len(const)):
        idx = stream_count + dense_count + c
        scalars[idx] = [(start_time, const[c]), (const_end, const[c])]

    return scalars


# decode one AnimationClip dict into meta, curves
def decode_clip(tt, tos):
    mc = tt["m_MuscleClip"]
    clipd = mc["m_Clip"]["data"]
    start_time = float(mc["m_StartTime"])
    stop_time = float(mc["m_StopTime"])
    fallback_rate = float(tt.get("m_SampleRate", 0)) or 1.0

    scalars = _decode_scalar_curves(clipd, start_time, stop_time, fallback_rate)

    curves = []
    for g, b in enumerate(tt["m_ClipBindingConstant"]["genericBindings"]):
        # cant resolve it, alright fall back to the games path + hash thing
        path = tos.get(b["path"], "path_%d" % b["path"])
        group = [scalars.get(3 * g + k, []) for k in range(3)]
        if not any(group):
            continue

        attr = b["attribute"]
        if attr in VECTOR3_AXES:
            prefix = VECTOR3_AXES[attr]
            curves += [_curve(path, f"{prefix}.{ax}", samples)
                       for ax, samples in zip("xyz", group) if samples]
        elif attr == ATTR_ROTATION and all(group):
            curves += _rotation_curves(path, *group)

    meta = {
        "clipName": tt["m_Name"],
        "frameRate": float(tt["m_SampleRate"]),
        "wrapMode": int(tt.get("m_WrapMode", 0)),
    }
    return meta, curves
