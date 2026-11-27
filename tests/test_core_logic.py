"""Core logic that had no tests: pick snapping, shot-edge trimming, chat spikes, Whisper word timings."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import context  # noqa: F401
from test_run_files import SEGS, make_run
from videoclipper import render
from videoclipper.picks import select
from videoclipper.signals import chat_spikes
from videoclipper.transcribe import _dtw_words, dtw_preset


def moment(start, end, score, title="m"):
    return {"start": start, "end": end, "score": score, "title": title}


class SelectSnapping(unittest.TestCase):
    def test_a_moment_snaps_to_the_lines_around_it(self):
        # lines start every 5 s and last 4.5 s: 00:01:03 snaps back to the line at 60, 00:01:40 forward to the end of the line at 95
        rd = make_run(SEGS, {"chunk_01.json": [moment("00:01:03", "00:01:40", 9)]})
        (c,), _ = select(rd, top=1, min_score=7, max_len=75)
        self.assertAlmostEqual(c["_s"], 59.75)
        self.assertAlmostEqual(c["_e"], 99.9)

    def test_a_moment_shorter_than_12_seconds_is_dropped(self):
        rd = make_run(SEGS, {"chunk_01.json": [moment("00:01:00", "00:01:05", 9, "short"),
                                               moment("00:03:00", "00:03:30", 9, "ok")]})
        chosen, total = select(rd, top=5, min_score=7, max_len=75)
        self.assertEqual(total, 2)
        self.assertEqual([c["title"] for c in chosen], ["ok"])

    def test_the_score_bar_is_inclusive_and_top_limits_the_count(self):
        rd = make_run(SEGS, {"chunk_01.json": [moment("00:01:00", "00:01:40", 7, "on the bar"),
                                               moment("00:03:00", "00:03:40", 6.9, "just under"),
                                               moment("00:05:00", "00:05:40", 8, "better"),
                                               moment("00:07:00", "00:07:40", 9, "best")]})
        chosen, _ = select(rd, top=5, min_score=7, max_len=75)
        self.assertEqual([c["title"] for c in chosen], ["best", "better", "on the bar"])  # ranked by score
        chosen, _ = select(rd, top=2, min_score=7, max_len=75)
        self.assertEqual([c["title"] for c in chosen], ["best", "better"])


class ShotEdges(unittest.TestCase):
    def avoid(self, cuts, ss=10.0, dur=60.0, sdur=200.0):
        with mock.patch.object(render, "shot_cuts", side_effect=cuts):  # [cuts near the start, cuts near the end]
            return render._avoid_shot_edges(Path("src.mp4"), ss, dur, sdur)

    def test_no_cuts_changes_nothing(self):
        self.assertEqual(self.avoid([[], []]), (10.0, 60.0))

    def test_a_cut_just_after_the_start_moves_the_start_onto_it(self):
        ss, dur = self.avoid([[10.1], []])
        self.assertAlmostEqual(ss, 10.1)
        self.assertAlmostEqual(ss + dur, 70.0)  # the end stays where it was

    def test_a_cut_far_from_the_start_is_ignored(self):
        self.assertEqual(self.avoid([[11.0], []]), (10.0, 60.0))

    def test_a_cut_just_after_the_end_pulls_the_end_back_before_it(self):
        ss, dur = self.avoid([[], [70.1]])
        self.assertEqual(ss, 10.0)
        self.assertAlmostEqual(ss + dur, 70.06)

    def test_the_end_is_not_trimmed_when_the_clip_would_get_too_short(self):
        ss, dur = self.avoid([[], [14.1]], ss=10.0, dur=4.0)
        self.assertEqual((ss, dur), (10.0, 4.0))


class ChatSpikes(unittest.TestCase):
    def write(self, offsets_sec):
        f = Path(tempfile.mkdtemp()) / "chat.jsonl"
        f.write_text("\n".join(json.dumps({"replayChatItemAction": {"videoOffsetTimeMsec": str(int(t * 1000))}})
                               for t in offsets_sec) + "\nnot json\n")
        return f

    def test_a_burst_of_messages_over_a_quiet_baseline_is_a_spike(self):
        times = [t for t in range(0, 600, 10)] + [300 + i * 0.4 for i in range(20)]  # 1 msg / 10 s, 20 in one bin
        spikes = chat_spikes(self.write(times))
        self.assertEqual(len(spikes), 1)
        self.assertEqual((spikes[0]["start"], spikes[0]["end"], spikes[0]["msgs"]), (300, 310, 21))
        self.assertGreaterEqual(spikes[0]["x"], 2.5)

    def test_steady_chat_has_no_spikes(self):
        self.assertEqual(chat_spikes(self.write(range(0, 600, 5))), [])

    def test_too_little_chat_or_no_file_gives_nothing(self):
        self.assertEqual(chat_spikes(self.write(range(0, 40))), [])
        self.assertEqual(chat_spikes(None), [])
        self.assertEqual(chat_spikes(Path("/nonexistent/chat.jsonl")), [])


class WordTimings(unittest.TestCase):
    def tok(self, text, dtw):
        return {"text": text, "t_dtw": dtw}

    def test_dtw_words_join_pieces_and_end_at_the_next_word_or_the_cap(self):
        data = {"transcription": [{"tokens": [self.tok("[_BEG_]", 0), self.tok(" Hello", 100), self.tok(",", 110),
                                              self.tok(" play", 150), self.tok("ing", 160), self.tok(" now", 400)]}]}
        words = _dtw_words(data)
        self.assertEqual([w["t"] for w in words], ["Hello,", "playing", "now"])
        self.assertAlmostEqual(words[0]["s"], 0.85)   # 1.00 s minus the DTW lead
        self.assertAlmostEqual(words[0]["e"], 1.35)   # the next word starts before the 0.5 s cap
        self.assertAlmostEqual(words[1]["e"], 1.85)   # starts at 1.35, capped at WORD_MAX (0.5 s): "now" is far later
        self.assertAlmostEqual(words[2]["e"], 3.85 + 0.5)

    def test_dtw_words_are_none_when_whisper_gave_no_dtw_times(self):
        self.assertIsNone(_dtw_words({"transcription": [{"tokens": [self.tok(" Hello", -1)]}]}))

    def test_word_start_times_never_go_backwards(self):
        words = _dtw_words({"transcription": [{"tokens": [self.tok(" a", 200), self.tok(" b", 100)]}]})
        self.assertLessEqual(words[0]["s"], words[1]["s"])

    def test_dtw_preset_comes_from_the_model_file_name(self):
        self.assertEqual(dtw_preset("/m/ggml-medium.en.bin"), "medium.en")
        self.assertEqual(dtw_preset("/m/ggml-small.bin"), "small")
        self.assertEqual(dtw_preset("/m/ggml-large-v3-turbo.bin"), "large.v3.turbo")
        self.assertIsNone(dtw_preset("/m/my-finetune.bin"))


if __name__ == "__main__":
    unittest.main()
