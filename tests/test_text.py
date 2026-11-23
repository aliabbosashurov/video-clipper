"""Pure text helpers: time formats, names, hashtags, quality names, error hints, transcript cleanup."""
import unittest

import context  # noqa: F401
from videoclipper.config import resolve_quality
from videoclipper.post import hashtags
from videoclipper.sources import explain
from videoclipper.transcribe import clean_segments
from videoclipper.util import hms, parse_ts, slug


class Util(unittest.TestCase):
    def test_hms_and_parse_ts_round_trip(self):
        self.assertEqual(hms(3723.4), "01:02:03")
        self.assertEqual(parse_ts("01:02:03"), 3723)
        self.assertEqual(parse_ts("02:03"), 123)
        self.assertEqual(parse_ts(12.5), 12.5)

    def test_slug_cuts_file_names_at_a_whole_word(self):
        t = "Speed finds the hidden alien in GTA 6 and says it's KSI"
        self.assertEqual(slug(t, 40, whole_words=True), "speed-finds-the-hidden-alien-in-gta-6")
        self.assertEqual(slug(t, 40), "speed-finds-the-hidden-alien-in-gta-6-an")
        self.assertEqual(slug(None), "video")


class Post(unittest.TestCase):
    def test_hashtags_are_normalised_and_deduplicated(self):
        self.assertEqual(hashtags(["#GTA6", "gta6", "GTA 6", "#start up", "#Startup!", "", None, 5, "#Россия"]),
                         "#GTA6 #startup #Россия")
        self.assertEqual(hashtags("#a #b a"), "#a #b")
        self.assertEqual(hashtags(None), "")


class Quality(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual([resolve_quality(x) for x in ("4K", "1440p", "best", "720", "standard")],
                         ["max", "high", "max", "fast", "standard"])

    def test_unknown_quality_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_quality("ultra")


class ErrorHints(unittest.TestCase):
    def hint(self, msg):
        out = explain(msg)
        return out.split("Hint: ", 1)[1] if "Hint: " in out else None

    def test_common_errors_get_a_hint(self):
        self.assertIn("--cookies", self.hint("Sign in to confirm you're not a bot"))
        self.assertIn("private", self.hint("ERROR: [youtube] x: Private video. Sign in if you've been granted access"))
        self.assertIn("region", self.hint("The uploader has not made this video available in your country"))
        self.assertIn("members-only", self.hint("Join this channel to get access to members-only content"))
        self.assertIn("removed", self.hint("ERROR: [youtube] x: This video is unavailable"))
        self.assertIn("removed", self.hint("ERROR: [youtube] x: Video unavailable"))

    def test_unknown_errors_pass_through_unchanged(self):
        self.assertEqual(explain("something new"), "something new")


class TranscriptCleanup(unittest.TestCase):
    def seg(self, t, s=0.0):
        return {"start": s, "end": s + 1, "text": t}

    def test_silence_and_music_markers_are_dropped(self):
        segs = [self.seg("[BLANK_AUDIO]"), self.seg("[MUSIC]"), self.seg("♪♪"), self.seg("(engine revving)"),
                self.seg("Hello there")]
        self.assertEqual([s["text"] for s in clean_segments(segs)], ["Hello there"])

    def test_reaction_tags_are_kept(self):
        segs = [self.seg("[Screams]"), self.seg("(laughing)"), self.seg("(applause)")]
        self.assertEqual(len(clean_segments(segs)), 3)

    def test_a_repeated_line_is_merged_into_the_previous_one(self):
        out = clean_segments([self.seg("What?", 1), self.seg("what", 2), self.seg("Okay", 3)])
        self.assertEqual([s["text"] for s in out], ["What?", "Okay"])
        self.assertEqual(out[0]["end"], 3)  # the merged line now covers both


if __name__ == "__main__":
    unittest.main()
