"""Files in a run folder: chunks for the picker, reading / checking / ranking picks, status."""
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import context  # noqa: F401
from videoclipper.chunks import OVERLAP_SEC, write_chunks
from videoclipper.picks import problems, select
from videoclipper.status import run_status


def make_run(segs, picks=None) -> Path:
    rd = Path(tempfile.mkdtemp())
    (rd / "chunks").mkdir()
    (rd / "picks").mkdir()
    (rd / "transcript.json").write_text(json.dumps(segs))
    for name, body in (picks or {}).items():
        (rd / "picks" / name).write_text(body if isinstance(body, str) else json.dumps(body))
    return rd


# one line every 5 s for 30 minutes
SEGS = [{"start": t, "end": t + 4.5, "text": f"line at {t}"} for t in range(0, 1800, 5)]
INFO = {"streamer": "Tester", "title": "A long video", "duration": 1800}


class Chunks(unittest.TestCase):
    def test_chunks_overlap_by_a_minute_with_markers(self):
        rd = make_run(SEGS)
        loud = [{"start": 100, "end": 101, "db": 12.0}]
        n = write_chunks(rd, INFO, SEGS, loud, [], 720, context="test video")
        self.assertEqual(n, 3)
        first = (rd / "chunks" / "chunk_01.md").read_text()
        second = (rd / "chunks" / "chunk_02.md").read_text()
        self.assertIn("Context: test video", first)
        self.assertIn("[00:01:40] line at 100   <<LOUD(+12dB)>>", first)
        self.assertNotIn("previous chunk", first)
        self.assertIn("(end of the previous chunk", second)
        self.assertIn(f"line at {720 - OVERLAP_SEC}", second)  # the last minute of chunk 1 again
        self.assertIn("(this chunk starts here)", second)


class Picks(unittest.TestCase):
    def moment(self, start, end, score, title):
        return {"start": start, "end": end, "score": score, "title": title}

    def test_best_moments_win_and_overlaps_are_dropped(self):
        rd = make_run(SEGS, {"chunk_01.json": [self.moment("00:01:00", "00:01:40", 9, "best"),
                                               self.moment("00:01:10", "00:01:30", 8, "overlaps best"),
                                               self.moment("00:05:00", "00:05:40", 7.5, "second"),
                                               self.moment("00:08:00", "00:08:40", 5, "too low")]})
        chosen, total = select(rd, top=5, min_score=7, max_len=75)
        self.assertEqual(total, 4)
        self.assertEqual([c["title"] for c in chosen], ["best", "second"])

    def test_one_broken_entry_does_not_drop_the_rest_of_the_file(self):
        rd = make_run(SEGS, {"chunk_01.json": [{"start": "00:00:10", "score": 9.9, "title": "no end"},
                                               self.moment("00:02:00", "00:02:40", 8, "good")],
                             "chunk_02.json": "[not json"})
        with redirect_stdout(StringIO()) as out:
            chosen, total = select(rd, top=3, min_score=7, max_len=75)
        self.assertEqual([c["title"] for c in chosen], ["good"])
        self.assertIn("skipped chunk_01.json entry 1: missing 'end'", out.getvalue())
        self.assertIn("bad pick file chunk_02.json", out.getvalue())

    def test_clips_are_capped_at_max_len(self):
        rd = make_run(SEGS, {"chunk_01.json": [self.moment("00:01:00", "00:04:00", 9, "long")]})
        (c,), _ = select(rd, top=1, min_score=7, max_len=60)
        self.assertLessEqual(c["_e"] - c["_s"], 61)


class Status(unittest.TestCase):
    def test_status_reports_progress_and_broken_picks(self):
        rd = make_run(SEGS, {"chunk_01.json": [{"start": "00:00:10", "score": 8}],
                             "chunk_02.json": '{"start": 1}',
                             "chunk_03.json": "[oops"})
        write_chunks(rd, {**INFO, "duration": 3600}, SEGS, [], [], 720)  # 5 chunks
        st = run_status(rd)
        self.assertEqual((st["chunks"], st["picked_chunks"]), (5, 3))
        self.assertEqual(st["chunks_left"], ["chunk_04.md", "chunk_05.md"])
        self.assertEqual([b["file"] for b in st["bad_picks"]], ["chunk_01.json", "chunk_02.json", "chunk_03.json"])
        self.assertEqual(st["bad_picks"][0]["error"], "missing end")
        self.assertEqual(problems(rd)[0], 1)  # entries in readable files


if __name__ == "__main__":
    unittest.main()
