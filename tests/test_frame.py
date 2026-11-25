"""What goes on screen: layout choice + framing, caption timeline, and the platform safe zone."""
import re
import statistics
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import context  # noqa: F401
from videoclipper import layout
from videoclipper.captions import SAFE_MAX_Y, caption_frames
from videoclipper.config import QUALITY

FACE = [100.0, 500.0, 80.0, 110.0]
TRACK = [[0.0, 140.0, 555.0, 80.0, 110.0], [10.0, 300.0, 560.0, 80.0, 110.0]]
FACECAM = {"mode": "facecam", "box": [0, 386, 430, 294], "face": FACE, "track": TRACK}
CUTOUT = {"mode": "facecam", "face": FACE, "track": TRACK}


class Layout(unittest.TestCase):
    def test_forced_layouts_override_detection(self):
        self.assertEqual(layout.choose(FACECAM, "full", 1), {"mode": "full"})
        self.assertEqual(layout.choose(FACECAM, "cam", 1), {"mode": "cam", "face": FACE, "track": TRACK})
        self.assertEqual(layout.choose({"mode": "full"}, "cam", 1), {"mode": "full"})  # no face to centre on
        self.assertEqual(layout.choose({"mode": "full"}, "facecam", 1), {"mode": "full"})
        self.assertEqual(layout.choose(FACECAM, "auto", 1), FACECAM)
        with redirect_stdout(StringIO()) as out:
            cam = {"mode": "cam", "face": FACE, "track": TRACK}
            self.assertEqual(layout.choose(cam, "facecam", 2), CUTOUT)  # no box: follow the face
        self.assertIn("no webcam box found", out.getvalue())

    def test_the_streamer_beats_game_portraits(self):
        # frames: two pixel-still card portraits (one only in half the frames) and a big moving face
        portrait = (198.0, 539.0, 58.0, 77.0)
        frames = [[portrait, (344.0, 549.0, 52.0, 66.0), (300.0 + 25 * (i % 3), 650.0 - 8 * (i % 2), 150.0 + 6 * i, 190.0)]
                  for i in range(6)] + [[(290.0, 478.0, 78.0, 99.0), (290.0, 640.0 + 5 * i, 190.0, 250.0)] for i in range(6)]
        person = layout._person(layout._link(frames), len(frames), 1920)
        self.assertGreater(statistics.median(o[3] for o in person), 140)
        self.assertEqual(len(person), 12)
        self.assertIsNone(layout._person(layout._link([[portrait]] * 12), 12, 1920))  # only a frozen portrait: nobody

    def test_a_still_big_face_is_still_a_person(self):
        frames = [[(600.0, 200.0, 400.0, 500.0)] for _ in range(8)]  # locked-off podcast camera
        self.assertIsNotNone(layout._person(layout._link(frames), 8, 1920))

    def test_follow_glides_between_keypoints_and_holds_still_when_the_face_barely_moves(self):
        self.assertEqual(layout._follow([(0.0, 100.0), (3.0, 101.0)]), "100")
        e = layout._follow([(1.0, 100.0), (4.0, 400.0)])
        self.assertIn("lt(t,4.00)", e)
        self.assertTrue(e.startswith("if(lt(t,1.00),100.0,"))

    def test_every_mode_plans_a_1080x1920_frame(self):
        for fc in (FACECAM, CUTOUT, {"mode": "cam", "face": FACE, "track": TRACK}, {"mode": "full"}):
            p = layout.plan(fc, 1920, 1080, QUALITY["standard"])
            self.assertTrue(p.filter.startswith("[0:v]") and p.filter.endswith("[base]"), fc["mode"])
            self.assertTrue(0 < p.seam < 1920 and 0 < p.cap_y < 1920)

    def test_gameplay_crop_slides_off_the_cam_window(self):
        p = layout.plan(FACECAM, 1920, 1080, QUALITY["standard"])
        bottom = re.search(r"\[b\]crop=(\d+):(\d+):(\d+):(\d+)", p.filter).groups()
        self.assertGreaterEqual(int(bottom[2]), 430)  # starts right of the cam window (x 0..430)

    def test_sharpening_only_on_high_quality(self):
        cam = {"mode": "cam", "face": FACE, "track": TRACK}
        self.assertNotIn("unsharp", layout.plan(cam, 1920, 1080, QUALITY["standard"]).filter)
        self.assertIn("unsharp", layout.plan(cam, 1920, 1080, QUALITY["high"]).filter)


class Captions(unittest.TestCase):
    def test_timeline_covers_the_clip_and_stays_in_the_safe_zone(self):
        words = [{"t": w, "s": i * 0.4, "e": i * 0.4 + 0.35} for i, w in enumerate("so i got fired today wow".split())]
        out = Path(tempfile.mkdtemp())
        lst = caption_frames(words, "HE GOT FIRED", 960, 1600, 6.0, out)
        durations = [float(x) for x in re.findall(r"duration ([\d.]+)", lst.read_text())]
        self.assertAlmostEqual(sum(durations), 6.0, places=1)
        self.assertGreater(len(list(out.glob("c*.png"))), 3)  # one image per highlighted word
        self.assertLess(SAFE_MAX_Y, 1600)  # a caption asked for at y=1600 is pulled up into the safe zone


if __name__ == "__main__":
    unittest.main()
