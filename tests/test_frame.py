"""What goes on screen: layout choice + framing, caption timeline, and the platform safe zone."""
import re
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
FACECAM = {"mode": "facecam", "box": [0, 386, 430, 294], "face": FACE}


class Layout(unittest.TestCase):
    def test_forced_layouts_override_detection(self):
        self.assertEqual(layout.choose(FACECAM, "full", 1), {"mode": "full"})
        self.assertEqual(layout.choose(FACECAM, "gameplay", 1), {"mode": "full"})  # old name
        self.assertEqual(layout.choose(FACECAM, "cam", 1), {"mode": "cam", "face": FACE})
        self.assertEqual(layout.choose({"mode": "full"}, "cam", 1), {"mode": "full"})  # no face to centre on
        self.assertEqual(layout.choose(FACECAM, "auto", 1), FACECAM)
        with redirect_stdout(StringIO()) as out:
            self.assertEqual(layout.choose({"mode": "cam", "face": FACE}, "facecam", 2)["mode"], "cam")
        self.assertIn("no facecam box found", out.getvalue())

    def test_every_mode_plans_a_1080x1920_frame(self):
        for fc in (FACECAM, {"mode": "cam", "face": FACE}, {"mode": "full"}):
            p = layout.plan(fc, 1920, 1080, QUALITY["standard"])
            self.assertTrue(p.filter.startswith("[0:v]") and p.filter.endswith("[base]"), fc["mode"])
            self.assertTrue(0 < p.seam < 1920 and 0 < p.cap_y < 1920)

    def test_gameplay_crop_slides_off_the_cam_window(self):
        p = layout.plan(FACECAM, 1920, 1080, QUALITY["standard"])
        bottom = re.search(r"\[b\]crop=(\d+):(\d+):(\d+):(\d+)", p.filter).groups()
        self.assertGreaterEqual(int(bottom[2]), 430)  # starts right of the cam window (x 0..430)

    def test_sharpening_only_on_high_quality(self):
        cam = {"mode": "cam", "face": FACE}
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
