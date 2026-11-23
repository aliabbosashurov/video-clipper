"""Vertical framing: find where the person is (facecam overlay, camera shot, or nobody) and build the
ffmpeg filter that turns the wide frame into 1080x1920.

To add a layout: return a new "mode" from detect(), handle it in plan(), and add it to config.LAYOUTS.
"""
from __future__ import annotations

import os
import statistics
from dataclasses import dataclass
from pathlib import Path

from .config import CFG, Quality
from .util import log


@dataclass
class Plan:
    """What render needs from a layout."""
    filter: str  # ffmpeg filter graph from [0:v] to [base] (1080x1920)
    seam: int    # y of the hook box
    cap_y: int   # y of the caption line (captions.py clamps it into the safe zone)


def detect(video: Path, W: int, H: int) -> dict:
    """{"mode": "facecam", "box": [x, y, w, h], "face": [...]} / {"mode": "cam", "face": [...]} / {"mode": "full"}.
    Detection runs on frames scaled to at most 1920 wide (fast, same thresholds for 1440p/4K
    sources); the box and face come back in source pixels."""
    s = min(1.0, 1920 / W)
    res = _detect(video, int(W * s), int(H * s), s)
    if "face" in res:
        res["face"] = [v / s for v in res["face"]]
    if "box" in res:
        L, T, cw, ch = (int(v / s) for v in res["box"])
        res["box"] = [L, T, min(cw, W - L), min(ch, H - T)]
    return res


def _detect(video: Path, W: int, H: int, scale: float = 1.0) -> dict:
    """Sample frames, find a face that sits in the same spot (anywhere in the frame).
    facecam: the face is inside a box with static edges AND the rest of the frame moves (gameplay,
    screen share) -> overlay. cam: a camera shot of a person (podcast, interview, vlog). full: no steady face."""
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(video))
    nfr = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 300
    det = None
    ym = CFG.get("yunet_model")
    if ym and Path(ym).exists():
        det = cv2.FaceDetectorYN.create(ym, "", (W, H), 0.75, 0.3, 50)
    haar = None
    if det is None and hasattr(cv2, "CascadeClassifier"):
        haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces, grads, smalls = [], [], []
    for i in range(12):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(nfr * (i + 0.5) / 12))
        ok, fr = cap.read()
        if not ok:
            continue
        if scale < 1:
            fr = cv2.resize(fr, (W, H), interpolation=cv2.INTER_AREA)
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        smalls.append(cv2.resize(g, (160, 90), interpolation=cv2.INTER_AREA).astype(np.float32))
        grads.append((np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0)), np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1))))
        found = []
        if det is not None:
            _, res = det.detect(fr)
            if res is not None:
                found = [tuple(map(float, r[:4])) for r in res]
        elif haar is not None:
            found = [tuple(map(float, f)) for f in haar.detectMultiScale(g, 1.1, 6, minSize=(40, 40))]
        faces.append(found)
    cap.release()
    flat = [f for fs in faces for f in fs]
    if not flat:
        return {"mode": "full"}
    # cluster by centre; keep the most persistent cluster
    best, best_n = None, 0
    for f in flat:
        cx, cy = f[0] + f[2] / 2, f[1] + f[3] / 2
        members = [g for g in flat if abs(g[0] + g[2] / 2 - cx) < W * 0.06 and abs(g[1] + g[3] / 2 - cy) < H * 0.08]
        if len(members) > best_n:
            best, best_n = members, len(members)
    if best_n < max(3, len(faces) * 0.4):
        return {"mode": "full"}
    fx = statistics.median(m[0] for m in best); fy = statistics.median(m[1] for m in best)
    fw = statistics.median(m[2] for m in best); fh = statistics.median(m[3] for m in best)
    face = [fx, fy, fw, fh]
    shot = {"mode": "cam", "face": face} if fw > W * 0.05 else {"mode": "full", "face": face}
    if fw > W * 0.2:  # face fills the screen: it's a camera view, not an overlay
        return shot

    gx = np.median(np.stack([g[0] for g in grads]), axis=0)  # vertical edges, static over time
    gy = np.median(np.stack([g[1] for g in grads]), axis=0)  # horizontal edges

    def scan(profile, start, stop, nearest=False):
        """Strongest static edge between start (near the face) and stop. nearest=True takes the strong edge
        closest to the face instead: overlay graphics right under / over a cam (a viewer-count bar, a name
        plate) make a second, often stronger, edge further out."""
        rng = range(int(start), int(stop), 1 if stop > start else -1)
        vals = [(profile[i], i) for i in rng if 0 <= i < len(profile)]
        if len(vals) < 5:
            return None
        top, i = max(vals)
        if not (top > 3.5 * (statistics.median(x for x, _ in vals) + 1e-3) and top > 6):
            return None
        return next(j for v, j in vals if v >= 0.6 * top) if nearest else i

    x0, x1 = int(max(0, fx - fw * 0.5)), int(min(W, fx + fw * 1.5))
    rowp = gy[:, x0:x1].mean(axis=1)
    T = scan(rowp, fy - fh * 0.15, fy - fh * 2.2, nearest=True)
    B = scan(rowp, fy + fh * 1.15, fy + fh * 3.2, nearest=True)
    # side edges: averaged over the whole cam height once top/bottom are known, so a real window edge
    # (full height) beats objects in the room behind the streamer (only part of the height)
    y0 = int(T) if T is not None else int(max(0, fy - fh * 0.5))
    y1 = int(B) if B is not None else int(min(H, fy + fh * 1.5))
    colp = gx[y0:max(y1, y0 + 1)].mean(axis=0)
    L = scan(colp, fx - fw * 0.15, fx - fw * 4.0)
    R = scan(colp, fx + fw * 1.15, fx + fw * 4.0)
    # an overlay in a corner shows 2 edges (the other two are the frame border); none means a camera shot
    if sum(e is not None for e in (L, R, T, B)) < 2:
        return shot
    # fallbacks for missing edges: typical facecam framing around the face; a guess that lands near the
    # frame border means the cam sits flush in that corner, so use the border itself
    cw_guess = fw * 3.4
    ch_guess = cw_guess * 0.75
    if L is None:
        L = fx + fw / 2 - cw_guess / 2
        L = 0 if L < fw * 0.8 else L
    if R is None:
        R = fx + fw / 2 + cw_guess / 2
        R = W if W - R < fw * 0.8 else R
    if T is None:
        T = fy + fh * 0.45 - ch_guess * 0.45
        T = 0 if T < fh * 0.8 else T
    if B is None:
        B = fy + fh * 0.45 + ch_guess * 0.55
        B = H if H - B < fh * 0.8 else B
    L, R = max(0, L + 2), min(W, R - 2)
    T, B = max(0, T + 2), min(H, B - 2)
    if R - L < fw * 1.4 or B - T < fh * 1.4 or (R - L) * (B - T) > W * H * 0.35:
        return shot
    # an overlay sits on top of moving content; a static background around the face means a real room
    mask = np.ones((90, 160), bool)
    mask[int(T * 90 / H):int(B * 90 / H) + 1, int(L * 160 / W):int(R * 160 / W) + 1] = False
    motion = [float(np.abs(p - q)[mask].mean()) for p, q in zip(smalls, smalls[1:])]
    if not motion or statistics.median(motion) < 2.0:
        return shot
    return {"mode": "facecam", "box": [int(L), int(T), int(R - L), int(B - T)], "face": face}


def choose(fc: dict, forced: str | None, n: int) -> dict:
    """Apply a forced layout (per pick or --layout) to what detect() found. "gameplay" = old name for "full"."""
    forced = {"gameplay": "full"}.get(forced, forced)
    if forced == "full" or (forced == "cam" and "face" not in fc):
        return {"mode": "full"}
    if forced == "cam":
        return {"mode": "cam", "face": fc["face"]}
    if forced == "facecam" and fc["mode"] != "facecam":
        log(f"  clip {n}: no facecam box found, using {fc['mode']}")
    return fc


def plan(fc: dict, W: int, H: int, q: Quality) -> Plan:
    """The ffmpeg framing for a detected (or forced) layout."""
    sf = ":flags=lanczos"  # sharper than the default bicubic when enlarging a small facecam
    sharp = ",unsharp=5:5:0.6:5:5:0" if q.sharpen else ""
    if fc["mode"] == "facecam":
        L, T, cw, ch = fc["box"]
        top_h = int(min(960, max(560, 1080 * ch / cw)))
        top_h -= top_h % 2
        bot_h = 1920 - top_h
        gw, gh = H * 1080 / bot_h, H
        if gw > W:
            gw, gh = W, W * bot_h / 1080
        gx, gy = (W - gw) / 2, (H - gh) / 2
        # keep the cam window itself out of the gameplay panel when there's room to slide the crop
        if L < gx < L + cw and L + cw + gw <= W:
            gx = L + cw
        elif L < gx + gw < L + cw and L - gw >= 0:
            gx = L - gw
        vf = (f"[0:v]fps=30,split[a][b];"
              f"[a]crop={cw}:{ch}:{L}:{T},scale=1080:{top_h}:force_original_aspect_ratio=increase{sf},"
              f"crop=1080:{top_h}{sharp}[top];"
              f"[b]crop={int(gw)}:{int(gh)}:{int(gx)}:{int(gy)},scale=1080:{bot_h}{sf}[bot];[top][bot]vstack[base]")
        return Plan(vf, top_h, top_h + int(bot_h * 0.58))
    if fc["mode"] == "cam":  # 9:16 crop centred on the main face
        fx, fy, fw, fh = fc["face"]
        cw = min(W, H * 9 / 16)
        cx = min(max(0, fx + fw / 2 - cw / 2), W - cw)
        return Plan(f"[0:v]fps=30,crop={int(cw)}:{H}:{int(cx)}:0,scale=1080:1920{sf}{sharp}[base]", 300, 1380)
    # full frame in the middle over a blurred fill
    return Plan("[0:v]fps=30,split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                f"boxblur=30:3,eq=brightness=-0.15[bg];[b]scale=1080:-2{sf}[fg];[bg][fg]overlay=0:(H-h)/2[base]",
                560, 1420)
