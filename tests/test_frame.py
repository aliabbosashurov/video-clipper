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
from videoclipper.captions import HOOK_LINES, HOOK_SIZES, SAFE_MAX_Y, SAFE_TEXT_W, caption_frames, fit_hook
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
    def build(self, hook="HE GOT FIRED", seam=960, cap_y=1600, dur=6.0):
        words = [{"t": w, "s": i * 0.4, "e": i * 0.4 + 0.35} for i, w in enumerate("so i got fired today wow".split())]
        out = Path(tempfile.mkdtemp())
        return caption_frames(words, hook, seam, cap_y, dur, out), out

    def test_timeline_covers_the_clip_and_stays_in_the_safe_zone(self):
        ov, out = self.build()
        durations = [float(x) for x in re.findall(r"duration ([\d.]+)", ov.strips.read_text())]
        self.assertAlmostEqual(sum(durations), 6.0, places=1)
        self.assertGreater(len(list(out.glob("c*.png"))), 3)  # one image per highlighted word
        self.assertLess(SAFE_MAX_Y, 1600)  # a caption asked for at y=1600 is pulled up into the safe zone
        from PIL import Image
        with Image.open(out / "c0000.png") as im:
            self.assertTrue(ov.strip_y < SAFE_MAX_Y < ov.strip_y + im.size[1])  # the strip is built around the safe line

    def test_caption_strips_are_small_even_sized_bands_inside_the_frame(self):
        from PIL import Image
        for cap_y in (300, 1090, 1380, 1900):
            ov, out = self.build(cap_y=cap_y)
            with Image.open(out / "c0000.png") as im:
                w, h = im.size
            self.assertEqual(w, 1080)
            self.assertTrue(120 < h < 400 and h % 2 == 0, h)
            self.assertTrue(ov.strip_y % 2 == 0 and 0 <= ov.strip_y and ov.strip_y + h <= 1920)
            with Image.open(out / "blank.png") as im:
                self.assertEqual(im.size, (1080, h))  # same size, so the overlay never jumps

    def test_the_hook_is_one_still_image_and_no_hook_means_none(self):
        from PIL import Image
        ov, out = self.build(seam=672)
        self.assertEqual(ov.hook, out / "hook.png")
        with Image.open(ov.hook) as im:
            w, h = im.size
        self.assertEqual(w, 1080)
        self.assertTrue(ov.hook_y % 2 == 0 and h % 2 == 0 and ov.hook_y <= 672 < ov.hook_y + h)
        self.assertIsNone(self.build(hook=None)[0].hook)


class HookFit(unittest.TestCase):
    def fit(self, text):
        from PIL import Image, ImageDraw
        draw = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
        fnt, lines = fit_hook(draw, text.upper(), SAFE_TEXT_W - 60)
        return draw, fnt, lines

    def test_a_short_hook_keeps_the_full_size(self):
        _, fnt, lines = self.fit("He got fired the same day")
        self.assertEqual(fnt.size, HOOK_SIZES[0])
        self.assertLessEqual(len(lines), HOOK_LINES)

    def test_a_long_hook_shrinks_to_fit_instead_of_losing_words(self):
        text = ("Biggest boss fight ever she beats it after six hours of trying and chat loses it completely "
                "tonight wow no way this really happened here")
        draw, fnt, lines = self.fit(text)
        self.assertLess(fnt.size, HOOK_SIZES[0])
        self.assertEqual(" ".join(lines), text.upper())  # nothing was cut
        self.assertLessEqual(len(lines), HOOK_LINES)
        self.assertTrue(all(draw.textlength(l, font=fnt) <= SAFE_TEXT_W - 60 for l in lines))

    def test_a_hook_too_long_for_any_size_ends_with_an_ellipsis_on_a_whole_word(self):
        text = " ".join(["unbelievable"] * 40)
        draw, fnt, lines = self.fit(text)
        self.assertLessEqual(len(lines), HOOK_LINES)
        self.assertTrue(lines[-1].endswith("…"))
        self.assertTrue(all(draw.textlength(l, font=fnt) <= SAFE_TEXT_W - 60 for l in lines))

    def test_one_word_wider_than_the_box_gets_a_smaller_font(self):
        draw, fnt, lines = self.fit("Supercalifragilisticexpialidocious")
        self.assertTrue(all(draw.textlength(l, font=fnt) <= SAFE_TEXT_W - 60 for l in lines))


if __name__ == "__main__":
    unittest.main()
