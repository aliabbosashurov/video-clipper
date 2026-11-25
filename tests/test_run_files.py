"""Files in a run folder: chunks for the picker, the manifest, reading / checking / ranking picks, status."""
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import context  # noqa: F401
from videoclipper import manifest, transcribe
from videoclipper.chunks import LOOKAHEAD_SEC, LOW_CONF, sha, write_chunks
from videoclipper.picks import problems, select
from videoclipper.post import post_text
from videoclipper.status import run_status

# one line every 5 s for 30 minutes
SEGS = [{"start": t, "end": t + 4.5, "text": f"line at {t}"} for t in range(0, 1800, 5)]
INFO = {"streamer": "Tester", "title": "A long video", "duration": 1800}


def make_run(segs, picks=None, info=INFO) -> Path:
    """A prepped run folder: transcript, chunks (12 min each), manifest with the chunk index, and the given picks."""
    rd = Path(tempfile.mkdtemp())
    (rd / "chunks").mkdir()
    (rd / "picks").mkdir()
    (rd / "transcript.json").write_text(json.dumps(segs))
    index = write_chunks(rd, info, segs, [], [], 720)
    manifest.update(rd, source=info, prep={"whisper_model": "medium.en"}, chunks=index)
    for name, body in (picks or {}).items():
        (rd / "picks" / name).write_text(body if isinstance(body, str) else json.dumps(body))
    return rd


class Chunks(unittest.TestCase):
    def test_every_line_is_owned_by_one_chunk_and_each_chunk_ends_with_a_lookahead(self):
        rd = make_run(SEGS)
        loud = [{"start": 100, "end": 101, "db": 12.0}]
        index = write_chunks(rd, INFO, SEGS, loud, [], 720, context="test video")
        self.assertEqual([c["lines"] for c in index], [144, 144, 72])  # 720 s of lines at 5 s each; 360 s in the last
        self.assertEqual(sum(c["lines"] for c in index), len(SEGS))
        first, second, last = [(rd / "chunks" / f"chunk_0{n}.md").read_text() for n in (1, 2, 3)]
        self.assertIn("Context: test video", first)
        self.assertIn("[00:01:40] line at 100   <<LOUD(+12dB)>>", first)
        self.assertIn("(end of this chunk.", first)
        above, below = first.split("(end of this chunk.")
        self.assertIn("line at 715", above)
        self.assertNotIn("line at 720", above)   # chunk 2's first line is only context here
        self.assertIn("line at 720", below)
        self.assertIn(f"line at {720 + LOOKAHEAD_SEC - 5}", below)
        self.assertNotIn(f"line at {720 + LOOKAHEAD_SEC}\n", below)  # the lookahead stops at LOOKAHEAD_SEC
        self.assertIn("[00:12:00] line at 720\n", second.split("(end of this chunk.")[0])
        self.assertNotIn("(end of this chunk.", last)  # nothing follows the last chunk

    def test_a_line_that_runs_over_a_boundary_belongs_to_the_chunk_where_it_starts(self):
        segs = [{"start": 715, "end": 725, "text": "crosses the boundary"}, {"start": 730, "end": 735, "text": "later"}]
        rd = make_run(segs)
        own1 = (rd / "chunks" / "chunk_01.md").read_text().split("(end of this chunk.")[0]
        own2 = (rd / "chunks" / "chunk_02.md").read_text().split("(end of this chunk.")[0]
        self.assertIn("crosses the boundary", own1)
        self.assertNotIn("crosses the boundary", own2)
        self.assertIn("later", own2)

    def test_the_index_describes_each_chunk_and_fingerprints_its_text(self):
        rd = make_run(SEGS)
        loud = [{"start": 100, "end": 101, "db": 12.0}, {"start": 800, "end": 801, "db": 9.0}]
        low = [{**s, "conf": 0.2} if s["start"] == 10 else s for s in SEGS]
        index = write_chunks(rd, INFO, low, loud, [{"start": 50, "end": 52, "x": 3}], 720)
        a, b, c = index
        self.assertEqual((a["n"], a["start"], a["end"], a["loud"], a["chat"], a["low_conf_lines"]), (1, 0, 720, 1, 1, 1))
        self.assertEqual((b["start"], b["end"], b["loud"], c["start"], c["end"]), (720, 1440, 1, 1440, 1800))
        self.assertEqual(a["words"], 144 * 3)  # "line at N" is 3 words
        self.assertEqual(a["sha"], sha((rd / "chunks" / "chunk_01.md").read_bytes()))


class Confidence(unittest.TestCase):
    def test_unsure_lines_are_marked_and_sure_ones_are_not(self):
        segs = [{"start": 0, "end": 4, "text": "clear speech", "conf": 0.9},
                {"start": 5, "end": 9, "text": "sung words maybe", "conf": LOW_CONF - 0.1},
                {"start": 10, "end": 14, "text": "an old transcript line without conf"}]
        rd = make_run(segs)
        write_chunks(rd, INFO, segs, [{"start": 6, "end": 7, "db": 11.0}], [], 720)
        text = (rd / "chunks" / "chunk_01.md").read_text()
        self.assertIn("[00:00:00] clear speech\n", text)
        self.assertIn("[00:00:05] sung words maybe   <<LOW-CONF LOUD(+11dB)>>", text)
        self.assertIn("[00:00:10] an old transcript line without conf\n", text)
        self.assertIn("LOW-CONF = ", text)  # the legend tells the picker what the marker means

    def test_transcribe_averages_token_confidence_and_skips_special_tokens(self):
        data = {"transcription": [{"offsets": {"from": 0, "to": 2000}, "text": " hello there",
                                   "tokens": [{"text": "[_BEG_]", "p": 0.99}, {"text": " hello", "p": 0.9},
                                              {"text": " there", "p": 0.5}, {"text": "[_TT_100]", "p": 0.01}]},
                                  {"offsets": {"from": 2000, "to": 3000}, "text": " ", "tokens": []}]}
        real = transcribe._whisper_json
        transcribe._whisper_json = lambda *a, **k: data
        try:
            segs = transcribe.transcribe(Path("x.wav"), Path("x"), "en")
        finally:
            transcribe._whisper_json = real
        self.assertEqual(segs, [{"start": 0.0, "end": 2.0, "text": "hello there", "conf": 0.7}])

    def test_a_repeated_line_keeps_the_lower_confidence(self):
        out = transcribe.clean_segments([{"start": 0, "end": 2, "text": "Thank you.", "conf": 0.8},
                                         {"start": 2, "end": 4, "text": "Thank you.", "conf": 0.3}])
        self.assertEqual(out, [{"start": 0, "end": 4, "text": "Thank you.", "conf": 0.3}])


def select_all(rd):
    return select(rd, top=1, min_score=0, max_len=75)


class Manifest(unittest.TestCase):
    def test_update_keeps_the_other_sections(self):
        rd = Path(tempfile.mkdtemp())
        manifest.update(rd, source=INFO, timing={"prep_started": 5})
        manifest.update(rd, prep={"whisper_model": "medium.en"})
        m = manifest.update(rd, render={"top": 3})
        self.assertEqual((m["schema"], m["source"], m["timing"]), (manifest.SCHEMA, INFO, {"prep_started": 5}))
        self.assertEqual((m["prep"], m["render"]), ({"whisper_model": "medium.en"}, {"top": 3}))
        self.assertEqual(manifest.read(rd), m)

    def test_only_a_prepped_folder_passes_require(self):
        bare = Path(tempfile.mkdtemp())
        self.assertEqual(manifest.read(bare), {})
        self.assertFalse((bare / "manifest.json").exists())  # reading never writes
        for call in (manifest.require, run_status, select_all):
            with self.assertRaises(SystemExit) as ctx:
                call(bare)
            self.assertIn("run prep first", str(ctx.exception))
        manifest.update(bare, source=INFO, prep={})  # prep started but never finished
        with self.assertRaises(SystemExit):
            manifest.require(bare)
        self.assertEqual(manifest.require(make_run(SEGS))["prep"], {"whisper_model": "medium.en"})

    def test_stale_reason_names_what_changed(self):
        m = {"prep": {"whisper_model": "small.en", "lang": "en", "chunk_min": 12}}
        self.assertIsNone(manifest.stale_reason(m, {"whisper_model": "small.en", "lang": "en", "chunk_min": 12}))
        self.assertEqual(manifest.stale_reason(m, {"whisper_model": "medium.en", "lang": "en", "chunk_min": 8}),
                         "whisper_model: small.en -> medium.en, chunk_min: 12 -> 8")
        self.assertIsNone(manifest.stale_reason({}, {"whisper_model": "medium.en"}))  # nothing recorded to compare


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

    def test_every_pick_knows_its_chunk_and_position(self):
        rd = make_run(SEGS, {"chunk_01.json": [self.moment("00:01:00", "00:01:40", 9, "a")],
                             "chunk_02.json": [self.moment("00:13:00", "00:13:40", 8, "b"),
                                               self.moment("00:20:00", "00:20:40", 8, "c")]})
        chosen, _ = select(rd, top=5, min_score=7, max_len=75)
        self.assertEqual([(c["_id"], c["_chunk"]) for c in chosen], [("c01-1", 1), ("c02-1", 2), ("c02-2", 2)])

    def test_a_moment_must_start_in_its_own_chunk(self):
        rd = make_run(SEGS, {"chunk_01.json": [self.moment("00:13:00", "00:13:40", 9, "wrong chunk"),
                                               self.moment("00:05:00", "00:05:40", 8, "fine")],
                             "chunk_02.json": [self.moment("00:11:59", "00:12:40", 8, "2 s early is rounding"),
                                               self.moment("00:11:00", "00:11:40", 8, "belongs to chunk 1")],
                             "chunk_09.json": [self.moment("00:01:00", "00:01:40", 8, "no such chunk")]})
        cands, bad = problems(rd)
        self.assertEqual(cands, 4)  # entries of files that belong to a chunk of this run
        self.assertEqual([(b["file"], b.get("entry")) for b in bad],
                         [("chunk_01.json", 0), ("chunk_02.json", 1), ("chunk_09.json", None)])
        self.assertIn("starts at 00:13:00, outside chunk 1 (00:00:00 to 00:12:00)", bad[0]["error"])
        self.assertEqual(bad[2]["error"], "there is no chunk 9 (this run has 3)")
        with redirect_stdout(StringIO()) as out:
            chosen, total = select(rd, top=5, min_score=7, max_len=75)
        self.assertEqual(sorted(c["title"] for c in chosen), ["2 s early is rounding", "fine"])
        self.assertEqual(total, 2)
        self.assertIn("skipped chunk_01.json entry 1: starts at 00:13:00, outside chunk 1", out.getvalue())
        self.assertIn("bad pick file chunk_09.json: there is no chunk 9", out.getvalue())

    def test_post_text_records_where_the_clip_came_from(self):
        c = {"_id": "c07-2", "_s": 100, "title": "t", "category": "fail", "score": 8}
        info = {"streamer": "Tester", "platform": "local", "path": "/x/video.mp4", "webpage_url": ""}
        txt = post_text(c, info, "cam", "standard", 1920, 1080, "medium.en")
        self.assertIn("Pick: c07-2  Whisper: medium.en  video-clipper ", txt)

    def test_clips_are_capped_at_max_len(self):
        rd = make_run(SEGS, {"chunk_01.json": [self.moment("00:01:00", "00:04:00", 9, "long")]})
        (c,), _ = select(rd, top=1, min_score=7, max_len=60)
        self.assertLessEqual(c["_e"] - c["_s"], 61)


class Status(unittest.TestCase):
    def test_status_reports_progress_and_broken_picks(self):
        rd = make_run(SEGS, {"chunk_01.json": [{"start": "00:00:10", "score": 8}],
                             "chunk_02.json": '{"start": 1}',
                             "chunk_03.json": "[oops"},
                      info={**INFO, "duration": 3600})  # 5 chunks
        st = run_status(rd)
        self.assertEqual((st["prepped_with"], st["chunks"], st["picked_chunks"]), ("medium.en", 5, 3))
        self.assertEqual(st["chunks_left"], ["chunk_04.md", "chunk_05.md"])
        self.assertEqual([b["file"] for b in st["bad_picks"]], ["chunk_01.json", "chunk_02.json", "chunk_03.json"])
        self.assertEqual(st["bad_picks"][0]["error"], "missing end")
        self.assertEqual(problems(rd)[0], 1)  # entries in readable files

    def test_status_flags_picks_older_than_their_chunk_and_chunks_edited_after_prep(self):
        rd = make_run(SEGS, {"chunk_01.json": [], "chunk_02.json": [], "chunk_03.json": []})
        self.assertEqual((run_status(rd)["stale_picks"], run_status(rd)["changed_chunks"]), ([], []))
        md1 = rd / "chunks" / "chunk_01.md"
        old = md1.stat().st_mtime - 100
        os.utime(rd / "picks" / "chunk_01.json", (old, old))          # picked before the chunk was written
        (rd / "chunks" / "chunk_02.md").write_text("edited by hand\n")  # no longer what prep wrote
        (rd / "chunks" / "chunk_03.md").unlink()
        st = run_status(rd)
        self.assertEqual(st["stale_picks"], ["chunk_01.json"])
        self.assertEqual(st["changed_chunks"], ["chunk_02.md", "chunk_03.md"])


if __name__ == "__main__":
    unittest.main()
