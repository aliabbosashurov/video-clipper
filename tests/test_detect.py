"""layout.detect() on small synthetic videos: which layout is found for a webcam box over gameplay, a talking
head, a streamer cutout, a game portrait and a screen with no face.

The face detector is replaced by one that reports faces at known places (a drawn rectangle isn't a face); everything
after that, i.e. tracking, picking the person, the edge scan, the motion check and the scaling, is the real code.
"""
import math
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import context  # noqa: F401
import cv2
import numpy as np
from videoclipper import layout

W, H, FPS, SECS = 1280, 720, 8, 6


def background(i: int) -> np.ndarray:
    """Smooth moving bands: lots of change between frames, no sharp edges (like busy gameplay, but tame)."""
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    ph = 1.1 * i
    ch = [128 + 100 * np.sin(2 * math.pi * (x / 400 + y / 300) + ph + k) for k in range(3)]
    return np.stack(ch, axis=-1).astype(np.uint8)


def write_video(path: Path, paint=None, still=False) -> None:
    """SECS seconds at FPS; `paint(frame)` draws on every frame. still=True keeps the background constant."""
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    if not out.isOpened():
        raise unittest.SkipTest("this OpenCV can't write mp4 files")
    for i in range(SECS * FPS):
        fr = background(0 if still else i)
        if paint:
            paint(fr)
        out.write(fr)
    out.release()


def fake_cv2(faces_at):
    """cv2, but FaceDetectorYN reports faces_at(call number) = [(x, y, w, h), ...] for every frame it is shown."""
    calls = {"n": 0}

    class Detector:
        def detect(self, frame):
            faces = faces_at(calls["n"])
            calls["n"] += 1
            if not faces:
                return 1, None
            return 1, np.array([[*f, *([0.0] * 11)] for f in faces], dtype=np.float32)

    class Fake:
        FaceDetectorYN = SimpleNamespace(create=lambda *a, **k: Detector())

        def __getattr__(self, name):
            return getattr(cv2, name)

    return Fake()


def jitter(n: int, amp: float = 5.0) -> float:
    """A real face is never perfectly still."""
    return amp * math.sin(n * 1.3)


class Detect(unittest.TestCase):
    def detect(self, faces_at, paint=None, still=False):
        d = Path(tempfile.mkdtemp())
        write_video(d / "v.mp4", paint, still)
        model = d / "yunet.onnx"
        model.write_bytes(b"x")  # only has to exist: the detector is replaced
        with mock.patch.dict(layout.CFG, {"yunet_model": str(model)}), \
                mock.patch.dict(sys.modules, {"cv2": fake_cv2(faces_at)}):
            return layout.detect(d / "v.mp4", W, H, 0.0, SECS)

    def test_no_faces_means_full(self):
        self.assertEqual(self.detect(lambda n: [])["mode"], "full")

    def test_a_big_face_on_a_calm_background_is_a_camera_shot(self):
        res = self.detect(lambda n: [(480 + jitter(n), 160, 300, 380)], still=True)
        self.assertEqual(res["mode"], "cam")
        fx, fy, fw, fh = res["face"]
        self.assertAlmostEqual(fx + fw / 2, 630, delta=15)
        self.assertEqual(len(res["track"]), len({round(t[0], 3) for t in res["track"]}))  # one point per sample time
        self.assertNotIn("box", res)

    def test_a_small_pixel_still_face_is_a_game_portrait_not_a_person(self):
        res = self.detect(lambda n: [(100, 100, 60, 70)])  # exactly the same place in every frame
        self.assertEqual(res["mode"], "full")

    def test_a_webcam_box_over_moving_gameplay_is_a_facecam(self):
        L, T, bw, bh = 40, 380, 360, 240

        def paint(fr):
            fr[T:T + bh, L:L + bw] = 215  # the webcam picture: flat and still
            cv2.rectangle(fr, (L, T), (L + bw - 1, T + bh - 1), (0, 0, 0), 4)

        res = self.detect(lambda n: [(L + 135 + jitter(n), T + 60 + jitter(n + 3), 90, 110)], paint)
        self.assertEqual(res["mode"], "facecam")
        self.assertIn("box", res)
        x, y, w, h = res["box"]
        for got, want in zip((x, y, w, h), (L, T, bw, bh)):
            self.assertAlmostEqual(got, want, delta=12)

    def test_a_streamer_cutout_with_no_box_is_followed_not_boxed(self):
        res = self.detect(lambda n: [(560 + jitter(n), 480 + jitter(n + 2), 80, 100)])
        self.assertEqual(res["mode"], "facecam")
        self.assertNotIn("box", res)
        self.assertIn("face", res)

    def test_a_small_face_high_in_a_still_picture_is_a_camera_shot(self):
        res = self.detect(lambda n: [(560 + jitter(n), 120 + jitter(n + 2), 80, 100)], still=True)
        self.assertEqual(res["mode"], "cam")

    def test_the_streamer_is_chosen_over_a_still_game_portrait(self):
        res = self.detect(lambda n: [(100, 100, 60, 70), (480 + jitter(n), 160, 300, 380)], still=True)
        self.assertEqual(res["mode"], "cam")
        self.assertGreater(res["face"][2], 200)  # the big moving face, not the 60 px portrait

    def test_faces_seen_in_too_few_frames_are_ignored(self):
        res = self.detect(lambda n: [(480, 160, 300, 380)] if n < 3 else [], still=True)  # 3 of ~12 frames
        self.assertEqual(res["mode"], "full")


class Scaling(unittest.TestCase):
    def test_detection_on_a_4k_source_runs_at_1920_wide_and_results_come_back_in_source_pixels(self):
        found = {"mode": "facecam", "face": [100.0, 200.0, 40.0, 50.0], "track": [[0.5, 120.0, 225.0, 40.0, 50.0]],
                 "box": [10, 20, 300, 200]}
        with mock.patch.object(layout, "_detect", return_value=found) as det:
            res = layout.detect(Path("x.mp4"), 3840, 2160, 5.0, 30.0)
        args = det.call_args.args
        self.assertEqual((args[1], args[2], args[3]), (1920, 1080, 0.5))  # detection size and scale
        self.assertEqual(res["face"], [200.0, 400.0, 80.0, 100.0])
        self.assertEqual(res["track"], [[0.5, 240.0, 450.0, 80.0, 100.0]])  # time stays in seconds
        self.assertEqual(res["box"], [20, 40, 600, 400])

    def test_a_1080p_source_is_not_scaled(self):
        found = {"mode": "full"}
        with mock.patch.object(layout, "_detect", return_value=found) as det:
            self.assertEqual(layout.detect(Path("x.mp4"), 1920, 1080), {"mode": "full"})
        self.assertEqual(det.call_args.args[3], 1.0)

    def test_a_box_is_kept_inside_the_frame_after_scaling(self):
        found = {"mode": "facecam", "face": [1.0, 1.0, 1.0, 1.0], "track": [], "box": [900, 500, 100, 100]}
        with mock.patch.object(layout, "_detect", return_value=found):
            L, T, cw, ch = layout.detect(Path("x.mp4"), 2000, 1000)["box"]  # scale 0.96: box edges land past the frame
        self.assertLessEqual(L + cw, 2000)
        self.assertLessEqual(T + ch, 1000)


if __name__ == "__main__":
    unittest.main()
