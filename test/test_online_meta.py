"""
test_online_meta.py - Tests for the GUI-independent online-metadata helpers.

Runs locally (no Kivy/PyQt needed); online_meta imports only stdlib.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from online_meta import (  # noqa: E402
    SOURCE_BOTH,
    SOURCE_ITUNES,
    SOURCE_MB,
    TagFetchQueue,
    build_song_query,
    clean_query_field,
    fetch_candidates,
    merge_candidates,
)


def _fake_fetcher(results):
    """
    Build a fake search callable that records its calls and returns *results*.

    The returned function mimics mb_fetcher/itunes_fetcher.search(artist,
    title); each invocation appends (artist, title) to its ``.calls`` list so
    tests can assert which source was queried.
    """
    def fetch(artist, title):
        fetch.calls.append((artist, title))
        return [dict(r) for r in results]
    fetch.calls = []
    return fetch


class TestCleanQueryField(unittest.TestCase):
    """Tests for clean_query_field()."""

    def test_none_returns_none(self):
        """Verify None passes through as None."""
        self.assertIsNone(clean_query_field(None))

    def test_empty_returns_none(self):
        """Verify an empty string returns None."""
        self.assertIsNone(clean_query_field(""))

    def test_whitespace_returns_none(self):
        """Verify a whitespace-only string returns None."""
        self.assertIsNone(clean_query_field("   "))

    def test_dash_placeholder_returns_none(self):
        """Verify the '-' missing-tag placeholder returns None."""
        self.assertIsNone(clean_query_field("-"))

    def test_value_is_trimmed(self):
        """Verify a real value is trimmed of surrounding whitespace."""
        self.assertEqual(clean_query_field("  Queen  "), "Queen")


class TestBuildSongQuery(unittest.TestCase):
    """Tests for build_song_query()."""

    def test_both_fields_present(self):
        """Verify both artist and title are returned when present."""
        self.assertEqual(
            build_song_query({"artist": "Queen", "title": "Bohemian Rhapsody"}),
            ("Queen", "Bohemian Rhapsody"),
        )

    def test_placeholder_artist_becomes_none(self):
        """Verify a '-' artist placeholder is dropped while title is kept."""
        self.assertEqual(
            build_song_query({"artist": "-", "title": "Song"}),
            (None, "Song"),
        )

    def test_missing_keys_become_none(self):
        """Verify absent artist/title keys yield (None, None)."""
        self.assertEqual(build_song_query({}), (None, None))


class TestMergeCandidates(unittest.TestCase):
    """Tests for merge_candidates()."""

    def test_tags_each_source_label(self):
        """Verify MusicBrainz rows get 'MusicBrainz' and iTunes rows 'iTunes'."""
        merged = merge_candidates(
            [{"title": "A", "score": 50}],
            [{"title": "B", "score": 40}],
        )
        by_title = {c["title"]: c["source"] for c in merged}
        self.assertEqual(by_title, {"A": "MusicBrainz", "B": "iTunes"})

    def test_sorted_by_score_descending(self):
        """Verify the merged list is ordered by score, highest first."""
        merged = merge_candidates(
            [{"title": "low", "score": 30}],
            [{"title": "high", "score": 90}, {"title": "mid", "score": 60}],
        )
        self.assertEqual([c["title"] for c in merged], ["high", "mid", "low"])

    def test_does_not_mutate_inputs(self):
        """Verify the inputs are copied, never tagged with 'source' in place."""
        mb = [{"title": "A", "score": 50}]
        merge_candidates(mb, [])
        self.assertNotIn("source", mb[0])

    def test_preserves_existing_source(self):
        """Verify a candidate that already has a source keeps it."""
        merged = merge_candidates([{"title": "A", "score": 1, "source": "X"}], [])
        self.assertEqual(merged[0]["source"], "X")

    def test_empty_inputs_return_empty(self):
        """Verify two empty lists merge to an empty list."""
        self.assertEqual(merge_candidates([], []), [])


class TestFetchCandidates(unittest.TestCase):
    """Tests for fetch_candidates() with injected fake fetchers."""

    def test_musicbrainz_only_skips_itunes(self):
        """Verify SOURCE_MB queries MusicBrainz only and tags the result."""
        mb = _fake_fetcher([{"title": "A", "score": 80}])
        itunes = _fake_fetcher([{"title": "B", "score": 70}])
        results = fetch_candidates("Q", "S", SOURCE_MB, mb=mb, itunes=itunes)
        self.assertEqual([c["title"] for c in results], ["A"])
        self.assertEqual(mb.calls, [("Q", "S")])
        self.assertEqual(itunes.calls, [])

    def test_itunes_only_skips_musicbrainz(self):
        """Verify SOURCE_ITUNES queries iTunes only."""
        mb = _fake_fetcher([{"title": "A", "score": 80}])
        itunes = _fake_fetcher([{"title": "B", "score": 70}])
        results = fetch_candidates("Q", "S", SOURCE_ITUNES, mb=mb, itunes=itunes)
        self.assertEqual([c["title"] for c in results], ["B"])
        self.assertEqual(mb.calls, [])
        self.assertEqual(itunes.calls, [("Q", "S")])

    def test_both_merges_and_sorts(self):
        """Verify SOURCE_BOTH queries both and returns a score-sorted union."""
        mb = _fake_fetcher([{"title": "A", "score": 50}])
        itunes = _fake_fetcher([{"title": "B", "score": 90}])
        results = fetch_candidates("Q", "S", SOURCE_BOTH, mb=mb, itunes=itunes)
        self.assertEqual([c["title"] for c in results], ["B", "A"])
        self.assertEqual(len(mb.calls), 1)
        self.assertEqual(len(itunes.calls), 1)

    def test_default_source_is_itunes(self):
        """Verify the default source queries iTunes, not MusicBrainz."""
        mb = _fake_fetcher([{"title": "A", "score": 80}])
        itunes = _fake_fetcher([{"title": "B", "score": 70}])
        fetch_candidates("Q", "S", mb=mb, itunes=itunes)
        self.assertEqual(mb.calls, [])
        self.assertEqual(itunes.calls, [("Q", "S")])

    def test_empty_results_return_empty(self):
        """Verify a source that returns nothing yields an empty list."""
        mb = _fake_fetcher([])
        itunes = _fake_fetcher([])
        self.assertEqual(
            fetch_candidates("Q", "S", SOURCE_BOTH, mb=mb, itunes=itunes), []
        )


class TestTagFetchQueue(unittest.TestCase):
    """Tests for the batch TagFetchQueue helper."""

    def _files(self):
        """Return a sample file list with a mix of complete and missing tags."""
        return [
            {"filename": "a.mp3", "path": "/m/a.mp3", "title": "T1", "artist": "A1"},
            {"filename": "b.mp3", "path": "/m/b.mp3", "title": "",   "artist": "A2"},
            {"filename": "c.mp3", "path": "/m/c.mp3", "title": "T3", "artist": "-"},
            {"filename": "d.mp3", "path": "/m/d.mp3", "title": None, "artist": None},
        ]

    def test_filters_to_files_missing_a_core_tag(self):
        """Verify only files missing title or artist are queued by default."""
        q = TagFetchQueue(self._files())
        self.assertEqual(q.total(), 3)
        self.assertEqual(q.current()["filename"], "b.mp3")

    def test_force_keeps_every_file(self):
        """Verify force=True keeps fully-tagged files in the queue too."""
        q = TagFetchQueue(self._files(), force=True)
        self.assertEqual(q.total(), 4)
        self.assertEqual(q.current()["filename"], "a.mp3")

    def test_counter_text_and_position(self):
        """Verify the (current / total) counter tracks the position."""
        q = TagFetchQueue(self._files())
        self.assertEqual(q.counter_text(), "(1 / 3)")
        q.advance()
        self.assertEqual(q.counter_text(), "(2 / 3)")

    def test_advance_and_mark_applied(self):
        """Verify advance() skips and mark_applied() counts and advances."""
        q = TagFetchQueue(self._files())
        q.mark_applied()
        q.advance()
        self.assertEqual(q.applied_count(), 1)
        self.assertEqual(q.current()["filename"], "d.mp3")

    def test_is_done_after_exhausting_queue(self):
        """Verify is_done() flips to True and current() returns None at the end."""
        q = TagFetchQueue(self._files())
        for _ in range(q.total()):
            q.advance()
        self.assertTrue(q.is_done())
        self.assertIsNone(q.current())

    def test_auto_retry_keyword_is_filename_stem(self):
        """Verify the fallback keyword is the current filename without extension."""
        q = TagFetchQueue(self._files())
        self.assertEqual(q.auto_retry_keyword(), "b")

    def test_query_terms_use_present_tags(self):
        """Verify query_terms() returns the file's real artist/title when set."""
        q = TagFetchQueue(self._files())  # current is b.mp3: title "", artist "A2"
        self.assertEqual(q.query_terms(), ("A2", None))

    def test_query_terms_fall_back_to_filename_stem(self):
        """Verify query_terms() uses the filename stem when both tags are missing."""
        q = TagFetchQueue(self._files())
        q.advance()  # b.mp3 -> c.mp3 (title T3, artist "-")
        q.advance()  # c.mp3 -> d.mp3 (both missing)
        self.assertEqual(q.query_terms(), (None, "d"))

    def test_empty_file_list_is_immediately_done(self):
        """Verify an empty queue reports done with a zero counter."""
        q = TagFetchQueue([])
        self.assertTrue(q.is_done())
        self.assertEqual(q.total(), 0)


if __name__ == "__main__":
    unittest.main()
