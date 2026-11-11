"""8-direction character sprites, 1-angle scenery billboards and effects.

A tiny numpy ray-caster renders characters built from ellipsoids and capsules,
lights them with a fixed sun, quantises each material to a hand-picked colour
ramp and adds a 1px outline, giving crisp pixel art in every direction.
"""
import math
import numpy as np
from common import hexrgb, rgb15

LIGHT = np.array([-0.45, 0.72, 0.55]); LIGHT /= np.linalg.norm(LIGHT)
PITCH = 0.45


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


class Ell:
    def __init__(self, c, r, mat, rot=None, clip=None, pat=None):
        self.c = np.array(c, float); self.r = np.array(r, float); self.mat = mat
        self.rot = np.eye(3) if rot is None else rot
        self.clip = clip or {}; self.pat = pat


class Cap:
    def __init__(self, a, b, r, mat, r2=None, pat=None):
        self.a = np.array(a, float); self.b = np.array(b, float)
        self.r0 = r; self.r1 = r if r2 is None else r2; self.mat = mat; self.pat = pat


def transform_prims(prims, M, off=(0, 0, 0)):
    out = []
    off = np.array(off, float)
    for p in prims:
        if isinstance(p, Ell):
            out.append(Ell(M @ p.c + off, p.r, p.mat, M @ p.rot, None, p.pat))
        else:
            out.append(Cap(M @ p.a + off, M @ p.b + off, p.r0, p.mat, p.r1, p.pat))
    return out


def render(prims, W, H, ox, oy, scale, yaw, pitch, ramps, local_xf=None):
    R = rot_x(pitch) @ rot_y(yaw)
    xs = (np.arange(W) + 0.5 - ox) / scale
    ys = (oy - (np.arange(H) + 0.5)) / scale
    X, Y = np.meshgrid(xs, ys)
    depth = np.full((H, W), -1e9)
    mat = np.full((H, W), None, dtype=object)
    nrm = np.zeros((H, W, 3))
    for p in prims:
        if isinstance(p, Ell):
            c = R @ p.c
            A = R @ p.rot @ np.diag(p.r)
            Ai = np.linalg.inv(A)
            P0 = np.stack([X - c[0], Y - c[1], np.full_like(X, -c[2])], -1)
            q0 = P0 @ Ai.T
            qd = Ai[:, 2]
            a = qd @ qd
            b = 2 * (q0 @ qd)
            cc = np.sum(q0 * q0, -1) - 1
            disc = b * b - 4 * a * cc
            ok = disc >= 0
            sq = np.sqrt(np.maximum(disc, 0))
            best_z = np.full((H, W), -1e9)
            best_back = np.zeros((H, W), bool)
            for z, back in (((-b - sq) / (2 * a), True), ((-b + sq) / (2 * a), False)):
                pv = np.stack([X, Y, z], -1)
                loc = pv @ R
                v = ok.copy()
                for ax, k in (('y', 1), ('x', 0), ('z', 2)):
                    if ax + 'min' in p.clip:
                        v &= loc[..., k] >= p.clip[ax + 'min']
                    if ax + 'max' in p.clip:
                        v &= loc[..., k] <= p.clip[ax + 'max']
                upd = v & (z > best_z)
                best_z = np.where(upd, z, best_z)
                best_back = np.where(upd, back, best_back)
            hit = best_z > -1e8
            pv = np.stack([X, Y, best_z], -1)
            q = (pv - c) @ Ai.T
            n = q @ Ai
            n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9
            n = np.where(best_back[..., None], -n * 0.4 + np.array([0, 0, -0.6]), n)
            zz = best_z
        else:
            a3, b3 = R @ p.a, R @ p.b
            zz = np.full((H, W), -1e9)
            n = np.zeros((H, W, 3))
            for t in np.linspace(0, 1, 18):
                s = a3 + (b3 - a3) * t
                r = p.r0 + (p.r1 - p.r0) * t
                d2 = (X - s[0]) ** 2 + (Y - s[1]) ** 2
                ok = d2 < r * r
                z = s[2] + np.sqrt(np.maximum(r * r - d2, 0))
                upd = ok & (z > zz)
                zz = np.where(upd, z, zz)
                nn = np.stack([X - s[0], Y - s[1], z - s[2]], -1) / r
                n = np.where(upd[..., None], nn, n)
            hit = zz > -1e8
        upd = hit & (zz > depth)
        if p.pat is not None:
            pv = np.stack([X, Y, zz], -1)
            loc = pv @ R
            nloc = n @ R
            mm = np.full((H, W), None, dtype=object)
            for (yy, xx) in zip(*np.nonzero(upd)):
                mm[yy, xx] = p.pat(loc[yy, xx], nloc[yy, xx], p.mat)
            holes = upd & np.vectorize(lambda m: m is None)(mm)
            upd &= ~holes
            mat = np.where(upd, mm, mat)
        else:
            mat = np.where(upd, p.mat, mat)
        depth = np.where(upd, zz, depth)
        nrm = np.where(upd[..., None], n, nrm)
    out = np.zeros((H, W), np.int32)
    for yy in range(H):
        for xx in range(W):
            m = mat[yy, xx]
            if m is None:
                continue
            ramp = ramps[m]
            lam = float(nrm[yy, xx] @ LIGHT)
            k = int((lam + 0.3) / 1.15 * len(ramp))
            out[yy, xx] = ramp[max(0, min(len(ramp) - 1, k))]
    # outline: silhouette + depth discontinuities
    filled = out > 0
    edge = np.zeros_like(filled)
    edge[1:, :] |= filled[:-1, :]; edge[:-1, :] |= filled[1:, :]
    edge[:, 1:] |= filled[:, :-1]; edge[:, :-1] |= filled[:, 1:]
    res = out.copy()
    res[edge & ~filled] = 1
    for (dy, dx) in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        sh = np.roll(np.roll(depth, dy, 0), dx, 1)
        far = filled & (np.roll(np.roll(filled, dy, 0), dx, 1)) & (sh - depth > 3.0)
        res[far] = 1
    # keep image borders clean
    return res


# ------------------------------------------------------------------ characters
def skeleton(phase=None, pose='walk'):
    J = {}
    pel = np.array([0, 27.0, 0])
    aR = aL = 0.0
    bR = bL = 0.15
    armR = armL = 0.0
    bendR = bendL = 0.35          # elbow bend
    lean = 0.0                    # forward lean of the upper body
    breath = 0.0
    lift = 0.0
    if pose == 'run':
        s, c = math.sin(2 * math.pi * phase), math.cos(2 * math.pi * phase)
        aR, aL = 0.85 * s, -0.85 * s
        bR, bL = 0.3 + 1.45 * max(0, c), 0.3 + 1.45 * max(0, -c)
        armR, armL = -0.95 * s, 0.95 * s
        bendR = bendL = 1.35
        lean = 0.16
        lift = 1.6 * abs(math.cos(2 * math.pi * phase))     # airborne between strides
    elif pose == 'breathe':
        breath = phase
    if pose == 'walk':
        s, c = math.sin(2 * math.pi * phase), math.cos(2 * math.pi * phase)
        aR, aL = 0.5 * s, -0.5 * s
        bR, bL = 0.15 + 0.9 * max(0, c), 0.15 + 0.9 * max(0, -c)
        armR, armL = -0.4 * s, 0.4 * s
    J['pelvis'] = pel
    for side, a, b in (('R', aR, bR), ('L', aL, bL)):
        sx = -3.3 if side == 'R' else 3.3
        hip = pel + np.array([sx, -1.0, 0])
        th = np.array([0, -math.cos(a), math.sin(a)])
        knee = hip + 12.0 * th
        sh_ = np.array([0, -math.cos(a - b), math.sin(a - b)])
        ank = knee + 11.5 * sh_
        J['hip' + side], J['knee' + side], J['ank' + side] = hip, knee, ank
    low = min(J['ankR'][1], J['ankL'][1])
    dy = 3.0 - low + lift
    for k in J:
        J[k] = J[k] + np.array([0, dy, 0])
    for side in 'RL':
        J['toe' + side] = J['ank' + side] + np.array([0, -1.4, 4.2])
    up = np.array([0, dy, 0])
    lz = lambda y: np.array([0, breath * (y - 30) / 20, lean * (y - 27)])   # lean / breathing
    J['chest'] = np.array([0, 36.5, 0]) + up + lz(36.5)
    J['neck'] = np.array([0, 45.0, 0.4]) + up + lz(45)
    J['head'] = np.array([0, 49.6, 0.6]) + up + lz(49.6)
    for side, a, bend in (('R', armR, bendR), ('L', armL, bendL)):
        sx = -6.7 if side == 'R' else 6.7
        sh = np.array([sx, 41.5, 0]) + up + lz(41.5)
        el = sh + 8.0 * np.array([sx * 0.02, -math.cos(a), math.sin(a)])
        wr = el + 7.5 * np.array([sx * 0.015, -math.cos(a + bend), math.sin(a + bend)])
        J['sh' + side], J['el' + side], J['wr' + side] = sh, el, wr
    if pose == 'shoot':
        sh = J['shR']
        J['elR'] = sh + np.array([0.8, -0.8, 7.6])
        J['wrR'] = J['elR'] + np.array([0.8, 0.6, 7.2])
        J['elL'] = J['shL'] + np.array([-0.6, -7.2, 2.5])
        J['wrL'] = J['elL'] + np.array([-1.2, -5.0, 4.0])
    return J


def cowboy_prims(J, pose, outlaw=False):
    P = []
    pants = 'pants'
    for s in 'RL':
        P.append(Cap(J['ank' + s], J['toe' + s], 2.0, 'boot', 1.7))
        P.append(Cap(J['ank' + s], J['ank' + s] + 0.42 * (J['knee' + s] - J['ank' + s]), 2.55, 'boot'))
        P.append(Cap(J['knee' + s], J['ank' + s], 2.3, pants, 2.1))
        P.append(Cap(J['hip' + s], J['knee' + s], 2.9, pants, 2.4))
    pel = J['pelvis']
    P.append(Ell(pel + [0, 0.6, 0], (5.5, 3.7, 3.7), pants))
    P.append(Ell(pel + [0, 3.0, 0], (5.7, 1.3, 3.9), 'belt'))
    P.append(Ell(pel + [0, 3.0, 3.8], (1.3, 0.9, 0.5), 'metal'))
    if pose != 'shoot':  # holstered revolver
        P.append(Cap(pel + [-5.6, 2.0, 0.6], pel + [-5.9, -4.0, 1.4], 1.6, 'belt'))
        P.append(Cap(pel + [-5.7, 2.4, 0.3], pel + [-6.0, 4.6, -1.6], 1.05, 'metal'))
    ch = J['chest']
    if outlaw:
        P.append(Ell(ch + [0, -5.0, 0], (7.6, 15.5, 4.9), 'coat', clip={'ymin': ch[1] - 22.5, 'ymax': ch[1] + 7.5}))
        sleeve = 'coat'
    else:
        P.append(Ell(ch, (5.8, 7.6, 3.8), 'shirt'))

        def poncho_pat(loc, n, m, base=ch[1]):
            y = loc[1] - base
            if -5.4 < y < -4.2 or -2.4 < y < -1.7:
                return 'stripe'
            if -3.6 < y < -2.6 and (int((math.atan2(loc[0], loc[2]) + 4) * 6) % 2 == 0):
                return 'stripe'
            return m
        P.append(Ell(ch + [0, 0.6, 0], (9.2, 8.6, 6.0), 'poncho', clip={'ymin': ch[1] - 7.2}, pat=poncho_pat))
        sleeve = 'poncho'
    for s in 'RL':
        P.append(Cap(J['sh' + s], J['el' + s], 2.05, sleeve, 1.9))
        P.append(Cap(J['el' + s], J['wr' + s], 1.85, sleeve, 1.6))
        P.append(Ell(J['wr' + s] + (J['wr' + s] - J['el' + s]) * 0.18, (1.55, 1.75, 1.55), 'skin'))
    if pose == 'shoot':
        w = J['wrR']; d = (J['wrR'] - J['elR']); d /= np.linalg.norm(d)
        P.append(Cap(w + [0, 0.9, 0.4], w + [0, 1.5, 0] + d * 6.5, 0.9, 'metal'))
        P.append(Ell(w + [0, 1.2, 0] + d * 2.0, (1.2, 1.3, 1.3), 'metal'))
    nk = J['neck']
    P.append(Cap(nk + [0, -1, -0.2], nk + [0, 1.5, 0], 1.8, 'skin'))
    hd = J['head']

    def face_pat(loc, n, m):
        y = loc[1] - hd[1]; x = loc[0] - hd[0]; z = loc[2] - hd[2]
        if z > 2.4 and 0.0 < y < 1.1 and 0.9 < abs(x) < 2.3:
            return 'eye'
        if z < -1.2 and y > 0.5:
            return 'hair'
        if y < -1.8 and z > 0.5:
            return 'stubble'
        return m
    P.append(Ell(hd, (3.9, 4.4, 4.0), 'skin', pat=face_pat))
    P.append(Ell(hd + [0, -0.4, 3.8], (0.9, 1.1, 0.8), 'skin'))
    if outlaw:
        P.append(Ell(hd + [0, -2.2, 0.6], (4.25, 2.5, 3.9), 'bandana', clip={'zmin': hd[2] - 0.5}))
        P.append(Ell(nk + [0, 0, 0.3], (3.2, 1.6, 2.9), 'bandana'))
    else:
        P.append(Ell(nk + [0, -0.4, 0.3], (3.4, 1.7, 3.0), 'scarf'))
    hat = hd + [0, 3.2, -0.3]
    crown = (4.5, 3.6, 4.8) if not outlaw else (4.6, 4.0, 4.9)
    P.append(Ell(hat + [0, 2.4, 0], crown, 'hat', clip={'ymin': hat[1] + 0.3}))
    P.append(Ell(hat + [0, 0.9, 0], (crown[0] + 0.15, 0.9, crown[2] + 0.15), 'band'))
    brim = (10.2, 0.85, 9.6) if not outlaw else (9.2, 0.85, 8.8)
    P.append(Ell(hat, brim, 'hat2', rot=rot_x(-0.08)))
    return P


COWBOY_PAL = ['#000000', '#1b120d', '#7d4a2e', '#bf855b', '#e6c09a', '#2a1c13', '#4b3324', '#74513a',
              '#47301a', '#6c4a26', '#93693c', '#a8382a', '#2c3648', '#4c5d74', '#b9c2c8', '#3e2918']
COWBOY_RAMPS = {'skin': [2, 3, 4], 'stubble': [2, 3], 'eye': [1], 'hair': [5, 6], 'hat': [5, 6, 7], 'hat2': [5, 6, 7],
                'band': [15, 11], 'poncho': [8, 9, 10], 'stripe': [11, 4], 'shirt': [8, 9, 10], 'pants': [12, 13, 13],
                'boot': [1, 15, 15], 'belt': [15, 6], 'metal': [12, 14, 14], 'scarf': [11, 11, 4], 'coat': [8, 9, 10],
                'bandana': [11, 11, 4]}
OUTLAW_PAL = ['#000000', '#140e0c', '#7a4a30', '#b88058', '#dcb08a', '#121014', '#26222a', '#423c46',
              '#4a4238', '#6c604f', '#918268', '#a12d26', '#5e1814', '#353230', '#a7b0b6', '#3a2616']
OUTLAW_RAMPS = {'skin': [2, 3, 4], 'stubble': [2, 3], 'eye': [1], 'hair': [5, 6], 'hat': [5, 6, 7], 'hat2': [5, 6, 7],
                'band': [12, 11], 'coat': [8, 9, 10], 'pants': [1, 13, 13], 'boot': [1, 15, 15], 'belt': [15, 8],
                'metal': [13, 14, 14], 'bandana': [12, 11, 11], 'shirt': [8, 9, 10]}

N_FRAMES = 8          # outlaw: idle, walk x6, shoot
N_FRAMES_COWBOY = 16  # + run x6 (8..13), breathing idle x2 (14, 15)


def character_frames(outlaw, W):
    ramps = OUTLAW_RAMPS if outlaw else COWBOY_RAMPS
    frames = []
    poses = [('idle', None)] + [('walk', i / 6) for i in range(6)] + [('shoot', None)]
    if not outlaw:
        poses += [('run', i / 6) for i in range(6)] + [('breathe', 0.6), ('breathe', -0.3)]
    for d in range(8):
        yaw = d * math.pi / 4
        for pose, ph in poses:
            J = skeleton(ph if ph is not None else 0.0, pose)
            img = render(cowboy_prims(J, pose, outlaw), W, 64, W / 2, 62, 1.0, yaw, PITCH, ramps)
            frames.append(img)
    return frames


def dead_frame(outlaw):
    ramps = OUTLAW_RAMPS if outlaw else COWBOY_RAMPS
    J = skeleton(0.0, 'idle')
    prims = transform_prims(cowboy_prims(J, 'idle', outlaw), rot_x(-math.pi / 2), (0, 4.5, 0))
    return render(prims, 64, 32, 33, 26, 1.0, math.pi / 2 * 0.85, PITCH + 0.25, ramps)


# ------------------------------------------------------------------ scenery
PLANT_PAL = ['#000000', '#142010', '#2c4a22', '#46702e', '#6f9a45', '#a3c06a', '#4a4a24', '#6f6a34',
             '#9a9150', '#3a2a1c', '#5e4630', '#87694a', '#6a645c', '#a8a092', '#d8463a', '#e8dcb0']
PROP_PAL = ['#000000', '#1d1610', '#5d5248', '#83756a', '#a8998a', '#cbbca8', '#6b5636', '#977a4c',
            '#c2a36a', '#4a2e1a', '#6e4628', '#93633a', '#3b3b3f', '#74767c', '#e6dcc4', '#a07e52']
PLANT_RAMPS = {'cactus': [2, 3, 4, 5], 'rib': [2, 2, 3, 4], 'spine': [15], 'flower': [14, 15], 'bark': [9, 10, 11],
               'deadbark': [12, 13, 13], 'leaf': [6, 7, 8], 'jleaf': [2, 3, 4, 5], 'darkleaf': [2, 3]}
PROP_RAMPS = {'rock': [2, 3, 4, 5], 'tw': [6, 7, 8], 'barrel': [9, 10, 11], 'hoop': [12, 13], 'bone': [3, 14, 14]}


def hashf(*v):
    x = math.sin(sum((i + 1) * 12.9898 * a for i, a in enumerate(v))) * 43758.5453
    return x - math.floor(x)


def saguaro():
    def rib(loc, n, m):
        ang = math.atan2(n[0], n[2])
        k = int((ang / (2 * math.pi) + 1) * 16)
        if hashf(round(loc[0]), round(loc[1]), round(loc[2])) > 0.93:
            return 'spine'
        return 'rib' if k % 2 else 'cactus'
    P = [Cap((0, 0, 0), (0, 52, 0), 5.2, 'cactus', 4.6, pat=rib),
         Cap((0, 21, 0), (8.5, 23, 0), 3.4, 'cactus', pat=rib), Cap((9, 22.5, 0), (10, 39, 0), 3.3, 'cactus', 3.0, pat=rib),
         Cap((0, 29, 0), (-7.5, 31, 0.5), 3.2, 'cactus', pat=rib), Cap((-8, 30.5, 0.5), (-8.8, 43, 0.5), 3.0, 'cactus', 2.7, pat=rib),
         Ell((0, 56.5, 0), (1.6, 1.3, 1.6), 'flower'), Ell((-2.5, 55, 1), (1.3, 1.1, 1.3), 'flower')]
    return render(P, 32, 64, 16, 62, 1.0, 0.3, 0.35, PLANT_RAMPS)


def joshua():
    P = [Cap((0, 0, 0), (0, 26, 0), 3.4, 'bark', 2.6)]
    tips = []
    for (a, b, c) in (((0, 26, 0), (-12, 36, 2), (-16, 47, 2)), ((0, 26, 0), (10, 34, -1), (14, 44, -2)),
                      ((0, 24, 0), (3, 38, 4), (1, 50, 3)), ((-12, 36, 2), (-22, 40, 0), (-24, 46, 0)),
                      ((10, 34, -1), (20, 38, 2), (23, 44, 2))):
        P.append(Cap(a, b, 2.2, 'bark', 1.8)); P.append(Cap(b, c, 1.8, 'bark', 1.5)); tips.append(c)

    def spiky(loc, n, m):
        return 'jleaf' if hashf(round(loc[0] * 2), round(loc[1] * 2), round(loc[2] * 2)) > 0.25 else 'darkleaf'
    for t in tips:
        P.append(Ell(np.array(t) + [0, 2.5, 0], (4.5, 4.8, 4.5), 'jleaf', pat=spiky))
    return render(P, 64, 64, 32, 62, 1.0, 0.2, 0.35, PLANT_RAMPS)


def dead_tree():
    P = [Cap((0, 0, 0), (1, 30, 0), 3.0, 'deadbark', 2.2)]
    for (a, b) in (((1, 30, 0), (-12, 44, 1)), ((1, 30, 0), (10, 46, -1)), ((1, 28, 0), (3, 52, 2)),
                   ((-12, 44, 1), (-20, 50, 0)), ((-12, 44, 1), (-10, 55, 0)), ((10, 46, -1), (18, 54, 1)),
                   ((0, 18, 0), (12, 26, 2)), ((12, 26, 2), (17, 30, 1))):
        P.append(Cap(a, b, 1.6, 'deadbark', 0.8))
    return render(P, 64, 64, 32, 62, 1.0, 0.0, 0.35, PLANT_RAMPS)


def bush():
    P = []
    rng = np.random.default_rng(2)

    def leafy(loc, n, m):
        return 'leaf' if hashf(round(loc[0] * 1.5), round(loc[1] * 1.5), round(loc[2] * 1.5)) > 0.2 else 'darkleaf'
    for i in range(7):
        c = (rng.uniform(-7, 7), rng.uniform(4, 11), rng.uniform(-3, 3))
        P.append(Ell(c, (rng.uniform(3.5, 5.5), rng.uniform(3.5, 5), rng.uniform(3.5, 5)), 'leaf', pat=leafy))
    return render(P, 32, 32, 16, 30, 1.0, 0.0, 0.4, PLANT_RAMPS)


def rock(seed):
    rng = np.random.default_rng(seed)

    def bumpy(loc, n, m):
        return m
    P = [Ell((0, 5, 0), (10, 7.5, 8), 'rock', rot=rot_z(rng.uniform(-0.2, 0.2)), clip={'ymin': 0.3}),
         Ell((rng.uniform(-6, 6), 9, rng.uniform(-2, 2)), (5, 5, 5), 'rock', clip={'ymin': 0.3})]
    return render(P, 32, 32, 16, 30, 1.0, rng.uniform(0, 6), 0.4, PROP_RAMPS)


def barrel():
    def bands(loc, n, m):
        return 'hoop' if (2.6 < loc[1] < 3.6 or 13.4 < loc[1] < 14.4) else m
    P = [Ell((0, 8.5, 0), (6.4, 10.5, 6.4), 'barrel', clip={'ymin': 0.2, 'ymax': 16.8}, pat=bands)]
    return render(P, 32, 32, 16, 30, 1.0, 0.4, 0.45, PROP_RAMPS)


def tumbleweed(f):
    def holes(loc, n, m):
        h = hashf(round(loc[0] * 1.3 + f * 3), round(loc[1] * 1.3), round(loc[2] * 1.3))
        if h < 0.3:
            return None
        return 'tw'
    P = [Ell((0, 7.5, 0), (7.5, 7.2, 7.5), 'tw', pat=holes), Ell((0, 7.5, 0), (4.5, 4.4, 4.5), 'tw')]
    return render(P, 32, 32, 16, 30, 1.0, f * 0.7, 0.4, PROP_RAMPS)


def skull():
    P = [Ell((0, 2.5, 0), (3.2, 2.4, 4.2), 'bone'), Cap((-2.5, 3.5, -2), (-8, 6, -3), 0.9, 'bone', 0.5),
         Cap((2.5, 3.5, -2), (8, 6, -3), 0.9, 'bone', 0.5)]
    return render(P, 32, 32, 16, 30, 1.0, 0.3, 0.6, PROP_RAMPS)


# ------------------------------------------------------------------ effects (2D)
FX_PAL = ['#000000', '#2a1a0a', '#fff2a0', '#ffb040', '#e05020', '#ffffff', '#b89a70', '#d4bc94',
          '#ecdcbc', '#000000', '#ffe060', '#000000', '#000000', '#000000', '#000000', '#000000']


def fx_flash():
    img = np.zeros((16, 16), np.int32)
    for y in range(16):
        for x in range(16):
            dx, dy = x - 7.5, y - 7.5
            d = math.hypot(dx, dy)
            a = math.atan2(dy, dx)
            spike = 4.5 + 3.0 * max(0, math.cos(a * 4))
            if d < 2.2:
                img[y, x] = 5
            elif d < 3.6:
                img[y, x] = 2
            elif d < spike:
                img[y, x] = 3 if d < spike - 1.2 else 4
    return img


def fx_dust(f):
    img = np.zeros((16, 16), np.int32)
    rng = np.random.default_rng(3)
    r = 3 + f * 2
    for k in range(5):
        cx, cy = 8 + rng.uniform(-3, 3) * (1 + f * 0.4), 10 - k * 0.6 - f
        rr = r * rng.uniform(0.5, 0.9)
        for y in range(16):
            for x in range(16):
                d = math.hypot(x - cx, (y - cy) * 1.3)
                if d < rr:
                    img[y, x] = max(img[y, x], 8 if d < rr * 0.5 and f < 2 else (7 if d < rr * 0.8 else 6))
    if f == 2:
        img[(np.arange(16)[:, None] + np.arange(16)[None, :]) % 2 == 0] = 0
    return img


def fx_shadow():
    img = np.zeros((16, 32), np.int32)
    for y in range(16):
        for x in range(32):
            if ((x - 15.5) / 13) ** 2 + ((y - 7.5) / 5.5) ** 2 < 1:
                img[y, x] = 9
    return img


def fx_spark():
    img = np.zeros((16, 16), np.int32)
    for i in range(16):
        for (x, y) in ((i, 8), (8, i)):
            if abs(x - 8) + abs(y - 8) < 5:
                img[y, x] = 10 if abs(x - 8) + abs(y - 8) < 2 else 7
    for (x, y) in ((5, 5), (11, 5), (5, 11), (11, 11)):
        img[y, x] = 8
    return img


def pal15(pal):
    return [rgb15(hexrgb(c)) for c in pal]


# ------------------------------------------------------------------ horse
# Modelled in the same units as the cowboy (4 per world unit) so the rider fits
# the saddle; rendered at 0.58 px per unit (2.32 art px per world unit).
HORSE_PAL = ['#000000', '#1b120d', '#5a3218', '#8a5229', '#b47a42', '#2a1a12', '#4a2c18', '#7a4e2a',
             '#9c3426', '#bf855b', '#e6c09a', '#4b3324', '#74513a', '#6c4a26', '#93693c', '#4c5d74']
HORSE_RAMPS = {'coat': [2, 3, 4], 'mane': [1, 5], 'hoof': [1, 5], 'blanket': [8, 8], 'saddle': [6, 7],
               'blaze': [10], 'skin': [9, 10], 'stubble': [9], 'eye': [1], 'hair': [11], 'hat': [11, 12],
               'hat2': [11, 12], 'band': [6, 8], 'poncho': [13, 14], 'stripe': [8, 10], 'shirt': [13, 14],
               'pants': [15], 'boot': [1, 5], 'belt': [6, 7], 'metal': [15, 10], 'scarf': [8], 'coat_r': [2, 3]}
HORSE_SCALE = 0.58
HORSE_K = HORSE_SCALE * 4          # art pixels per world unit
HORSE_FRAMES = 26                  # idle, walk x6, gallop x6, then the same with the rider


def horse_prims(gait, phase, ridden):
    P = []
    two_pi = 2 * math.pi
    if gait == 'gallop':
        amp, bend, offs = 0.75, 1.4, {'LH': 0.0, 'RH': 0.12, 'LF': 0.45, 'RF': 0.57}
        bob = 3.0 * math.cos(two_pi * phase)
        pitch = 0.08 * math.sin(two_pi * phase)
    elif gait == 'walk':
        amp, bend, offs = 0.32, 0.9, {'LH': 0.0, 'LF': 0.25, 'RH': 0.5, 'RF': 0.75}
        bob = 0.8 * math.cos(2 * two_pi * phase)
        pitch = 0.0
    else:
        amp, bend, offs, bob, pitch = 0.0, 0.0, {'LH': 0, 'LF': 0, 'RH': 0, 'RF': 0}, 0.0, 0.0
    R = rot_x(-pitch)

    def B(v):  # body-space point -> horse space (pitch about the barrel centre, bob)
        v = np.array(v, float) - [0, 44, 0]
        return R @ v + [0, 44 + bob, 0]
    # barrel, chest, rump
    P.append(Ell(B((0, 44, 0)), (13, 15, 30), 'coat', rot=R))
    P.append(Ell(B((0, 45, 19)), (12, 15, 14), 'coat', rot=R))
    P.append(Ell(B((0, 47, -20)), (13.5, 15, 15), 'coat', rot=R))
    # neck + head
    P.append(Cap(B((0, 52, 22)), B((0, 70, 35)), 8.5, 'coat', 6.0))
    P.append(Cap(B((0, 74, 38)), B((0, 63, 50)), 6.5, 'coat', 4.6))
    P.append(Cap(B((0, 72, 41.5)), B((0, 64, 50.5)), 2.3, 'blaze', 1.5))
    for sx in (-1, 1):
        P.append(Cap(B((sx * 2.8, 79, 36.5)), B((sx * 3.4, 85, 35.5)), 1.5, 'coat', 0.9))
        P.append(Ell(B((sx * 4.6, 72, 41)), (0.9, 1.0, 1.0), 'eye'))
    # mane and tail
    P.append(Cap(B((0, 60, 17)), B((0, 78, 33)), 3.0, 'mane', 2.2))
    sway = 3.0 * math.sin(two_pi * phase) if gait != 'idle' else 0.0
    t0, t1 = B((0, 52, -34)), B((sway, 34, -41 - (6 if gait == 'gallop' else 0)))
    P.append(Cap(t0, t1, 3.4, 'mane', 1.6))
    # legs
    for name in ('LF', 'RF', 'LH', 'RH'):
        sx = -7.0 if name[0] == 'R' else 7.0
        front = name[1] == 'F'
        top = B((sx, 38 if front else 41, 18 if front else -20))
        ph = phase + offs[name]
        a = amp * math.sin(two_pi * ph)
        lift = max(0.0, math.cos(two_pi * ph)) * bend
        up = np.array([0, -math.cos(a), math.sin(a)])
        knee = top + 16 * up
        la = a - lift if front else a + lift * 0.7
        lo = np.array([0, -math.cos(la), math.sin(la)])
        hoof = knee + 17 * lo
        P.append(Cap(top, knee, 5.2, 'coat', 3.6))
        P.append(Cap(knee, hoof, 2.7, 'coat', 2.3))
        P.append(Cap(hoof, hoof + lo * 3.5 + [0, 0, 1.0], 3.0, 'hoof'))
    # tack
    P.append(Ell(B((0, 58.5, 0)), (15, 2.4, 12.5), 'blanket', rot=R, clip={'ymin': 50}))
    P.append(Ell(B((0, 60.5, -1)), (9.5, 2.6, 10), 'saddle', rot=R))
    P.append(Cap(B((0, 61, 8)), B((0, 66, 9.5)), 1.6, 'saddle'))
    if not ridden:
        for sx in (-1, 1):
            P.append(Cap(B((sx * 14, 59, 0)), B((sx * 14.5, 45, 1)), 0.9, 'saddle'))
        P.append(Cap(B((0, 66, 47)), B((0, 60, 30)), 0.7, 'saddle'))
    else:
        # the cowboy, sitting in the saddle
        lean = {'gallop': 3.5, 'walk': 1.0}.get(gait, 0.0)
        rb = bob * 0.6 + (1.2 * math.cos(two_pi * phase * 2) if gait == 'gallop' else 0)
        J = {}
        pel = np.array([0, 64.0, -1.0])
        J['pelvis'] = pel
        for side, sx in (('R', -1), ('L', 1)):
            J['hip' + side] = pel + [sx * 3.3, -1, 0]
            J['knee' + side] = np.array([sx * 11.0, 57.0, 7.0])
            J['ank' + side] = np.array([sx * 13.0, 42.0, 4.0])
            J['toe' + side] = J['ank' + side] + [0, -1.2, 4.2]
        up = np.array([0, 0, lean])
        J['chest'] = np.array([0, 73.5, -1.0]) + up
        J['neck'] = np.array([0, 82.0, -0.6]) + up * 1.4
        J['head'] = np.array([0, 86.6, -0.4]) + up * 1.6
        for side, sx in (('R', -6.7), ('L', 6.7)):
            J['sh' + side] = np.array([sx, 78.5, -1.0]) + up * 1.3
            J['el' + side] = J['sh' + side] + [sx * 0.1, -8.0, 4.0]
            J['wr' + side] = np.array([sx * 0.35, 67.5, 10.0]) + up
        rider = cowboy_prims(J, 'ride', False)
        P += transform_prims(rider, rot_x(-pitch * 0.5), (0, rb, 0))
        for side in ('R', 'L'):
            P.append(Cap(J['wr' + side] + [0, rb, 0], B((0, 66, 47)), 0.7, 'saddle'))
    return P


def horse_frames():
    frames = []
    seq = [('idle', 0.0)] + [('walk', i / 6) for i in range(6)] + [('gallop', i / 6) for i in range(6)]
    for d in range(8):
        yaw = d * math.pi / 4
        for ridden in (False, True):
            for gait, ph in seq:
                P = horse_prims(gait, ph, ridden)
                frames.append(render(P, 64, 64, 32, 62, HORSE_SCALE, yaw, PITCH, HORSE_RAMPS))
    return frames
