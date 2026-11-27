"""Vertical framing: find where the person is (facecam overlay, camera shot, or nobody) and build the
ffmpeg filter that turns the wide frame into 1080x1920.

To add a layout: return a new "mode" from detect(), handle it in plan(), and add it to config.LAYOUTS.
"""
from __future__ import annotations

import math
import os
import statistics
from dataclasses import dataclass
from pathlib import Path

from .config import CFG, Quality
from .util import log

TOP_H = 672  # facecam panel without a box: the face panel's height (the game gets the rest)
SAMPLE_EVERY = 1.5  # seconds between the frames detect() looks at


@dataclass
class Plan:
    """What render needs from a layout."""
    filter: str  # ffmpeg filter graph from [0:v] to [base] (1080x1920)
    seam: int    # y of the hook box
    cap_y: int   # y of the caption line (captions.py clamps it into the safe zone)


def detect(video: Path, W: int, H: int, start: float = 0.0, dur: float | None = None) -> dict:
    """What is on screen during video[start : start+dur], in source pixels:
    {"mode": "facecam" | "cam" | "full", "face": [x, y, w, h], "track": [[t, cx, cy, w, h], ...], "box": [x, y, w, h]}.
    face is the person's median face and track follows it over the clip (t counts from `start`); box only
    comes with a facecam that has a rectangular webcam box. No "face" when nobody steady is on screen.
    Detection runs on frames scaled to at most 1920 wide (fast, same thresholds for 1440p/4K sources)."""
    s = min(1.0, 1920 / W)
    res = _detect(video, int(W * s), int(H * s), s, start, dur)
    if "face" in res:
        res["face"] = [v / s for v in res["face"]]
        res["track"] = [[t, *(v / s for v in rest)] for t, *rest in res["track"]]
    if "box" in res:
        L, T, cw, ch = (int(v / s) for v in res["box"])
        res["box"] = [L, T, min(cw, W - L), min(ch, H - T)]
    return res


def _link(frames: list[list[tuple]]) -> list[list[tuple]]:
    """Faces found per frame -> tracks of (frame, cx, cy, w, h): the same face in neighbouring frames."""
    tracks: list[list[tuple]] = []
    for i, faces in enumerate(frames):
        taken = set()
        for x, y, w, h in sorted(faces, key=lambda f: -f[2]):
            cx, cy = x + w / 2, y + h / 2
            best, best_d = None, 1e9
            for k, tr in enumerate(tracks):
                _, px, py, pw, _ = tr[-1]
                d = math.hypot(cx - px, cy - py)
                if k not in taken and d < 1.5 * max(w, pw) and 0.5 <= w / pw <= 2 and d < best_d:
                    best, best_d = k, d
            if best is None:
                tracks.append([(i, cx, cy, w, h)])
                best = len(tracks) - 1
            else:
                tracks[best].append((i, cx, cy, w, h))
            taken.add(best)
    return tracks


def _person(tracks: list[list[tuple]], nframes: int, W: int) -> list[tuple] | None:
    """The track that is the person: seen in most frames and the biggest. A game's player cards and portraits
    are small and pixel-still; a streamer is bigger and always moving a little."""
    best, best_score = None, 0.0
    for tr in tracks:
        w = statistics.median(o[3] for o in tr)
        cover = len(tr) / nframes
        if len(tr) < 3 or cover < 0.4 or w < W * 0.02:
            continue
        if w < W * 0.08 and max(statistics.pstdev(o[k] for o in tr) for k in (1, 2, 3)) < 0.03 * w:
            continue  # frozen
        if cover * w > best_score:
            best, best_score = tr, cover * w
    return best


def _smooth(vals: list[float]) -> list[float]:
    """Median of 3, then mean of 5: a face bobbing at talking speed shouldn't move the crop."""
    n = len(vals)
    med = [statistics.median(vals[max(0, i - 1):i + 2]) for i in range(n)]
    return [statistics.fmean(med[max(0, i - 2):i + 3]) for i in range(n)]


def _track(person: list[tuple], times: list[float]) -> list[list[float]]:
    """[t, cx, cy, w, h] at every sample time, smoothed; frames where the face was lost are filled in."""
    import numpy as np
    idx = [o[0] for o in person]
    cols = [_smooth([float(v) for v in np.interp(range(len(times)), idx, [o[k] for o in person])]) for k in (1, 2, 3, 4)]
    return [[times[i], *(c[i] for c in cols)] for i in range(len(times))]


def _detect(video: Path, W: int, H: int, scale: float, start: float, dur: float | None) -> dict:
    """Sample frames across the clip and find the person. facecam: the face is inside a box with static edges AND
    the rest of the frame moves (gameplay, screen share) -> overlay; or a small face low in the frame with no
    box at all (a green-screen cutout of the streamer) -> followed with a crop. cam: a camera shot of a person
    (podcast, interview, vlog). full: no steady face."""
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = dur if dur else (int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 300) / fps
    det = None
    ym = CFG.get("yunet_model")
    if ym and Path(ym).exists():
        det = cv2.FaceDetectorYN.create(ym, "", (W, H), 0.75, 0.3, 50)
    haar = None
    if det is None and hasattr(cv2, "CascadeClassifier"):
        haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    n = int(min(30, max(12, total / SAMPLE_EVERY)))
    keep_every = math.ceil(n / 12)  # edge and motion maps are big: keep about 12 of them
    frames, times, grads, smalls = [], [], [], []
    for i in range(n):
        t = total * (i + 0.5) / n
        cap.set(cv2.CAP_PROP_POS_MSEC, (start + t) * 1000)
        ok, fr = cap.read()
        if not ok:
            continue
        if scale < 1:
            fr = cv2.resize(fr, (W, H), interpolation=cv2.INTER_AREA)
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        if i % keep_every == 0:
            smalls.append(cv2.resize(g, (160, 90), interpolation=cv2.INTER_AREA).astype(np.float32))
            grads.append((np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0)), np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1))))
        found = []
        if det is not None:
            _, res = det.detect(fr)
            if res is not None:
                found = [tuple(map(float, r[:4])) for r in res]
        elif haar is not None:
            found = [tuple(map(float, f)) for f in haar.detectMultiScale(g, 1.1, 6, minSize=(40, 40))]
        frames.append(found)
        times.append(t)
    cap.release()
    person = _person(_link(frames), len(frames), W) if frames else None
    if person is None:
        return {"mode": "full"}
    fx = statistics.median(o[1] - o[3] / 2 for o in person); fy = statistics.median(o[2] - o[4] / 2 for o in person)
    fw = statistics.median(o[3] for o in person); fh = statistics.median(o[4] for o in person)
    face = [fx, fy, fw, fh]
    track = _track(person, times)
    shot = {"mode": "cam", "face": face, "track": track} if fw > W * 0.05 else {"mode": "full", "face": face, "track": track}
    if fw > W * 0.2:  # face fills the screen: it's a camera view, not an overlay
        return shot
    # a small face low in the frame is a streamer cutout on top of the screen content, box or not
    cutout = {"mode": "facecam", "face": face, "track": track} if fw > W * 0.04 and fy + fh / 2 > H * 0.55 else shot

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
        return cutout
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
    # a webcam box is landscape: a tall one is the scan running past the real edge
    if R - L < fw * 1.4 or B - T < fh * 1.4 or (R - L) * (B - T) > W * H * 0.35 or R - L < B - T:
        return cutout
    # an overlay sits on top of moving content; a static background around the face means a real room
    mask = np.ones((90, 160), bool)
    mask[int(T * 90 / H):int(B * 90 / H) + 1, int(L * 160 / W):int(R * 160 / W) + 1] = False
    motion = [float(np.abs(p - q)[mask].mean()) for p, q in zip(smalls, smalls[1:])]
    if not motion or statistics.median(motion) < 2.0:
        return shot
    return {"mode": "facecam", "box": [int(L), int(T), int(R - L), int(B - T)], "face": face, "track": track}


def choose(fc: dict, forced: str | None, n: int) -> dict:
    """Apply a forced layout (per pick or --layout) to what detect() found."""
    if forced == "full" or (forced in ("cam", "facecam") and "face" not in fc):
        return {"mode": "full"}
    if forced == "cam":
        return {**{k: v for k, v in fc.items() if k != "box"}, "mode": "cam"}
    if forced == "facecam" and fc["mode"] != "facecam":
        log(f"  clip {n}: no webcam box found, following the face instead")
        return {**fc, "mode": "facecam"}
    return fc


def _follow(keys: list[tuple[float, float]]) -> str:
    """ffmpeg expression in t (seconds) that glides through (t, value) keypoints; a constant when it barely moves."""
    vals = [v for _, v in keys]
    if max(vals) - min(vals) < 2:
        return f"{statistics.fmean(vals):.0f}"
    e = f"{vals[-1]:.1f}"
    for (t0, v0), (t1, v1) in reversed(list(zip(keys, keys[1:]))):
        e = f"if(lt(t,{t1:.2f}),{v0:.1f}+({v1 - v0:.1f})*(t-{t0:.2f})/{t1 - t0:.2f},{e})"
    return f"if(lt(t,{keys[0][0]:.2f}),{vals[0]:.1f},{e})"


def _pan(fc: dict, cw: float, ch: float, W: int, H: int, face_at: float) -> tuple[str, str]:
    """x and y expressions of a cw x ch crop that keeps the face centred sideways and face_at (0..1) down the crop."""
    track = fc.get("track") or [[0.0, fc["face"][0] + fc["face"][2] / 2, fc["face"][1] + fc["face"][3] / 2, 0, 0]]
    xs = [(t, min(max(0, cx - cw / 2), W - cw)) for t, cx, *_ in track]
    ys = [(t, min(max(0, cy - ch * face_at), H - ch)) for t, _, cy, *_ in track]
    return f"'{_follow(xs)}'", f"'{_follow(ys)}'"


def plan(fc: dict, W: int, H: int, q: Quality) -> Plan:
    """The ffmpeg framing for a detected (or forced) layout."""
    sf = ":flags=lanczos"  # sharper than the default bicubic when enlarging a small facecam
    sharp = ",unsharp=5:5:0.6:5:5:0" if q.sharpen else ""
    if fc["mode"] == "facecam" and fc.get("box"):
        L, T, cw, ch = fc["box"]
        top_h = int(min(768, max(560, 1080 * ch / cw)))
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
        # box taller than the panel: keep the face, not the middle of the box, in view
        fy = fc["face"][1] + fc["face"][3] / 2 - T
        oy = min(max(0, (fy - ch * 0.45) * 1080 / cw), max(0, 1080 * ch / cw - top_h))
        vf = (f"[0:v]fps=30:start_time=0,split[a][b];"
              f"[a]crop={cw}:{ch}:{L}:{T},scale=1080:{top_h}:force_original_aspect_ratio=increase{sf},"
              f"crop=1080:{top_h}:0:{int(oy)}{sharp}[top];"
              f"[b]crop={int(gw)}:{int(gh)}:{int(gx)}:{int(gy)},scale=1080:{bot_h}{sf}[bot];[top][bot]vstack[base]")
        return Plan(vf, top_h, top_h + int(bot_h * 0.58))
    if fc["mode"] == "facecam":  # no webcam box: a crop that follows the face on top, the screen below
        fx, fy, fw, fh = fc["face"]
        widths = sorted(o[3] for o in fc["track"]) if fc.get("track") else [fw]
        cw = min(W * 0.7, max(360, widths[int(len(widths) * 0.8)] * 4.6))  # sized for when he leans in
        ch = cw * TOP_H / 1080
        if ch > H * 0.7:
            ch, cw = H * 0.7, H * 0.7 * 1080 / TOP_H
        cw, ch = int(cw) // 2 * 2, int(ch) // 2 * 2
        x, y = _pan(fc, cw, ch, W, H, 0.46)
        bot_h = 1920 - TOP_H
        gw, gh = H * 1080 / bot_h, H
        if gw > W:
            gw, gh = W, W * bot_h / 1080
        gx = (W - gw) / 2
        px0, px1 = fx + fw / 2 - fw * 0.8, fx + fw / 2 + fw * 0.8  # the person's body, so the screen crop skips it
        if px0 < gx + gw and px1 > gx:
            if px1 + gw <= W:
                gx = px1
            elif px0 - gw >= 0:
                gx = px0 - gw
        gy = (H - gh) / 2
        vf = (f"[0:v]fps=30:start_time=0,split[a][b];"
              f"[a]crop={cw}:{ch}:{x}:{y},scale=1080:{TOP_H}{sf}{sharp}[top];"
              f"[b]crop={int(gw)}:{int(gh)}:{int(gx)}:{int(gy)},scale=1080:{bot_h}{sf}[bot];[top][bot]vstack[base]")
        return Plan(vf, TOP_H, TOP_H + int(bot_h * 0.58))
    if fc["mode"] == "cam":  # 9:16 crop that follows the main face, zoomed in when it sits too low or high
        fx, fy, fw, fh = fc["face"]
        cy, ch, a = fy + fh / 2, H, 0.42
        if cy - a * ch < 0:
            ch = max(H * 0.62, cy / a)
        if cy + (1 - a) * ch > H:
            ch = max(H * 0.62, (H - cy) / (1 - a))
        ch = int(min(ch, H)) // 2 * 2
        cw = min(W, int(ch * 9 / 16) // 2 * 2)
        x, y = _pan(fc, cw, ch, W, H, a)
        return Plan(f"[0:v]fps=30:start_time=0,crop={cw}:{ch}:{x}:{y},scale=1080:1920{sf}{sharp}[base]", 300, 1380)
    # full frame in the middle over a blurred fill
    return Plan("[0:v]fps=30:start_time=0,split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                f"boxblur=30:3,eq=brightness=-0.15[bg];[b]scale=1080:-2{sf}[fg];[bg][fg]overlay=0:(H-h)/2[base]",
                560, 1420)
