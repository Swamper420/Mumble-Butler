"""Tests for the rewritten music recommendation pipeline."""
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from modules.recommender import MusicRecommender


def _isolated_recommender(**kwargs):
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)  # history file must not exist yet -> clean []
    kwargs.setdefault("history_file", path)
    kwargs.setdefault("max_history", 10)
    rec = MusicRecommender(**kwargs)
    rec.history = []
    return rec


def _itunes_payload(*tracks):
    return {"results": [
        {"artistName": a, "trackName": t} for a, t in tracks
    ]}


def _mock_session_get(recommender, payload=None, exc=None):
    mock_response = MagicMock()
    mock_response.json.return_value = payload if payload is not None else {"results": []}
    if exc is not None:
        recommender.session.get = MagicMock(side_effect=exc)
    else:
        recommender.session.get = MagicMock(return_value=mock_response)
    return recommender.session.get


def _make_brain(llm_mock=None, offline=False):
    from modules import brain as brain_mod
    with patch.object(brain_mod, "LLM_AVAILABLE", not offline):
        with patch.object(brain_mod.Brain, "check_connection", return_value=True):
            brain = brain_mod.Brain()
    brain.recommender = _isolated_recommender()
    if llm_mock is not None:
        brain.llm = llm_mock
    elif offline:
        brain.llm = None
    return brain


class TestNormalizeTrack(unittest.TestCase):
    def test_normalize_track_strips_noise(self):
        recommender = _isolated_recommender()
        self.assertEqual(recommender._normalize_track("Queen - Bohemian Rhapsody [Official Video]"), "queen bohemian rhapsody")
        self.assertEqual(recommender._normalize_track("Daft Punk - One More Time (Remastered 2021)"), "daft punk one more time")
        self.assertEqual(recommender._normalize_track("Kavinsky - Nightcall (feat. Lovefoxxx)"), "kavinsky nightcall")

    def test_normalize_handles_dashes_and_quotes(self):
        recommender = _isolated_recommender()
        self.assertEqual(
            recommender._normalize_track("Queen – Bohemian Rhapsody"),
            recommender._normalize_track("Queen - Bohemian Rhapsody"))
        self.assertEqual(recommender._normalize_track(""), "")


class TestVerifyTrackOnItunes(unittest.TestCase):
    def test_verify_returns_canonical_form(self):
        recommender = _isolated_recommender()
        _mock_session_get(recommender, _itunes_payload(("Queen", "Bohemian Rhapsody")))
        res = recommender.verify_track_on_itunes("Queen - Bohemian Rhapsody")
        self.assertEqual(res, "Queen - Bohemian Rhapsody")

    def test_verify_empty_results_returns_none(self):
        recommender = _isolated_recommender()
        _mock_session_get(recommender, {"results": []})
        self.assertIsNone(recommender.verify_track_on_itunes("Unknown Song"))

    def test_verify_generic_query_short_circuits_without_http(self):
        recommender = _isolated_recommender()
        mock_get = _mock_session_get(recommender, _itunes_payload(("X", "Y")))
        self.assertIsNone(recommender.verify_track_on_itunes("random music"))
        self.assertIsNone(recommender.verify_track_on_itunes("musiikkia"))
        mock_get.assert_not_called()

    def test_verify_picks_best_match_not_first(self):
        recommender = _isolated_recommender()
        _mock_session_get(recommender, _itunes_payload(
            ("Some Random Band", "Nightcall Cover"),
            ("Kavinsky", "Nightcall"),
        ))
        res = recommender.verify_track_on_itunes("Kavinsky - Nightcall")
        self.assertEqual(res, "Kavinsky - Nightcall")

    def test_verify_caches_repeat_queries(self):
        recommender = _isolated_recommender()
        mock_get = _mock_session_get(recommender, _itunes_payload(("Queen", "Bohemian Rhapsody")))
        first = recommender.verify_track_on_itunes("Queen - Bohemian Rhapsody")
        second = recommender.verify_track_on_itunes("Queen - Bohemian Rhapsody")
        self.assertEqual(first, second)
        mock_get.assert_called_once()

    def test_verify_network_error_returns_none(self):
        recommender = _isolated_recommender()
        _mock_session_get(recommender, exc=ConnectionError("down"))
        self.assertIsNone(recommender.verify_track_on_itunes("Queen - Bohemian Rhapsody"))


class TestHistory(unittest.TestCase):
    def test_history_assignment_keeps_dedup_index_in_sync(self):
        recommender = _isolated_recommender()
        recommender.history = ["Queen - Bohemian Rhapsody"]
        self.assertTrue(recommender.is_in_history("Queen - Bohemian Rhapsody [Official Video]"))
        self.assertFalse(recommender.is_in_history("ABBA - Dancing Queen"))

    def test_add_to_history_dedups_noisy_variants(self):
        recommender = _isolated_recommender()
        recommender.add_to_history("Queen - Bohemian Rhapsody")
        recommender.add_to_history("Queen - Bohemian Rhapsody [Official Video]")
        self.assertEqual(len(recommender.history), 1)

    def test_remove_from_history(self):
        recommender = _isolated_recommender()
        recommender.add_to_history("Queen - Bohemian Rhapsody")
        self.assertTrue(recommender.remove_from_history("queen - bohemian rhapsody"))
        self.assertFalse(recommender.is_in_history("Queen - Bohemian Rhapsody"))
        self.assertFalse(recommender.remove_from_history("Queen - Bohemian Rhapsody"))

    def test_resolve_track(self):
        recommender = _isolated_recommender()
        _mock_session_get(recommender, _itunes_payload(("Eagles", "Hotel California")))
        self.assertEqual(recommender.resolve_track("Eagles - Hotel California"),
                         "Eagles - Hotel California")
        self.assertIsNone(recommender.resolve_track("musiikkia"))
        self.assertIsNone(recommender.resolve_track(""))


class TestGetRecommendation(unittest.TestCase):
    def test_skips_history_and_returns_fresh(self):
        recommender = _isolated_recommender()
        _mock_session_get(recommender, {"results": []})
        with patch.object(config, "RECOMMENDER_SHUFFLE", False):
            recommender.history = ["Queen - Bohemian Rhapsody"]
            song = recommender.get_recommendation(
                ["Queen - Bohemian Rhapsody", "ABBA - Dancing Queen"])
        self.assertEqual(song, "ABBA - Dancing Queen")

    def test_recycles_when_everything_is_stale(self):
        recommender = _isolated_recommender()
        _mock_session_get(recommender, {"results": []})
        with patch.object(config, "RECOMMENDER_SHUFFLE", False):
            recommender.history = ["Queen - Bohemian Rhapsody"]
            song = recommender.get_recommendation(["Queen - Bohemian Rhapsody"])
        self.assertEqual(song, "Queen - Bohemian Rhapsody")

    def test_empty_candidates_use_curated_fallback(self):
        recommender = _isolated_recommender()
        _mock_session_get(recommender, {"results": []})
        song = recommender.get_recommendation([])
        self.assertIsNotNone(song)
        self.assertIn(" - ", song)

    def test_multi_recommendations(self):
        recommender = _isolated_recommender()
        _mock_session_get(recommender, {"results": []})
        with patch.object(config, "RECOMMENDER_SHUFFLE", False):
            tracks = recommender.get_recommendations(
                ["Queen - Bohemian Rhapsody", "ABBA - Dancing Queen"], count=2)
        self.assertEqual(tracks, ["Queen - Bohemian Rhapsody", "ABBA - Dancing Queen"])


class TestParseRecommendationOutput(unittest.TestCase):
    def test_parse_recommendation_output(self):
        brain = _make_brain(offline=True)
        llm_output = """
        [INTENT]
        GENRE_MOOD
        [VIBE]
        Upbeat 80s Synthwave
        [RECOMMENDATIONS]
        1. Kavinsky - Nightcall
        - College - A Real Hero
        * Com Truise - Brokendate
        """
        intent, vibe, recommendations = brain.parse_recommendation_output(llm_output)
        self.assertEqual(intent, "GENRE_MOOD")
        self.assertEqual(vibe, "Upbeat 80s Synthwave")
        self.assertEqual(recommendations, ["Kavinsky - Nightcall", "College - A Real Hero", "Com Truise - Brokendate"])

    def test_parse_tolerates_markdown_and_by_format(self):
        brain = _make_brain(offline=True)
        llm_output = """
        [intent]
        specific
        [vibe]
        \"Chill coding music\"
        [recommendations]
        1. **Tycho – A Walk**
        2. A Walk by Tycho
        """
        intent, vibe, recommendations = brain.parse_recommendation_output(llm_output)
        self.assertEqual(intent, "SPECIFIC")
        self.assertEqual(vibe, "Chill coding music")
        self.assertIn("Tycho - A Walk", recommendations)

    def test_parse_freeform_without_headers(self):
        brain = _make_brain(offline=True)
        llm_output = "Here are my picks:\nKavinsky - Nightcall\nBonobo - Kerala\nHave fun!"
        intent, vibe, recommendations = brain.parse_recommendation_output(llm_output)
        self.assertEqual(recommendations, ["Kavinsky - Nightcall", "Bonobo - Kerala"])


class TestRecommendSong(unittest.TestCase):
    def test_recommend_song_fallback_mode(self):
        brain = _make_brain(offline=True)
        brain.recommender.get_recommendation = MagicMock(return_value="Daft Punk - One More Time")
        song = brain.recommend_song("chill music")
        self.assertEqual(song, "Daft Punk - One More Time")

    def test_recommend_song_return_meta(self):
        llm_mock = MagicMock()
        llm_mock.create_chat_completion.return_value = {
            "choices": [{
                "message": {
                    "content": "[INTENT]\nGENRE_MOOD\n[VIBE]\nChill late night coding vibes\n[RECOMMENDATIONS]\n1. Tycho - A Walk\n2. Bonobo - Kerala"
                }
            }]
        }
        brain = _make_brain(llm_mock=llm_mock)
        with patch.object(config, "RECOMMENDER_SHUFFLE", False):
            with patch.object(brain.recommender, "verify_track_on_itunes", side_effect=lambda x: x):
                song, vibe = brain.recommend_song("chill music", return_meta=True)
        self.assertEqual(song, "Tycho - A Walk")
        self.assertEqual(vibe, "Chill late night coding vibes")

    def test_recommend_song_specific_bypass_history(self):
        llm_mock = MagicMock()
        llm_mock.create_chat_completion.return_value = {
            "choices": [{
                "message": {
                    "content": "[INTENT]\nSPECIFIC\n[VIBE]\nQueen Rock\n[RECOMMENDATIONS]\nQueen - Bohemian Rhapsody\nQueen - Under Pressure"
                }
            }]
        }
        brain = _make_brain(llm_mock=llm_mock)
        with patch.object(config, "RECOMMENDER_SHUFFLE", False):
            with patch.object(brain.recommender, "verify_track_on_itunes", side_effect=lambda x: x):
                brain.recommender.history = ["Queen - Bohemian Rhapsody"]

                song = brain.recommend_song("play bohemian rhapsody")
                self.assertEqual(song, "Queen - Bohemian Rhapsody")

                llm_mock.create_chat_completion.return_value = {
                    "choices": [{
                        "message": {
                            "content": "[INTENT]\nGENRE_MOOD\n[VIBE]\nQueen Rock\n[RECOMMENDATIONS]\nQueen - Bohemian Rhapsody\nQueen - Under Pressure"
                        }
                    }]
                }
                song = brain.recommend_song("play some Queen vibe")
                self.assertEqual(song, "Queen - Under Pressure")

    def test_explicit_track_fast_path_skips_llm(self):
        llm_mock = MagicMock()
        brain = _make_brain(llm_mock=llm_mock)
        with patch.object(brain.recommender, "verify_track_on_itunes",
                          return_value="Queen - Bohemian Rhapsody"):
            song, vibe = brain.recommend_song("Queen - Bohemian Rhapsody", return_meta=True)
        llm_mock.create_chat_completion.assert_not_called()
        llm_mock.assert_not_called()
        self.assertEqual(song, "Queen - Bohemian Rhapsody")
        self.assertIn("Queen - Bohemian Rhapsody", vibe)

    def test_offline_generic_returns_curated(self):
        brain = _make_brain(offline=True)
        with patch.object(brain.recommender, "verify_track_on_itunes", side_effect=lambda x: x):
            song, vibe = brain.recommend_song("random music", return_meta=True)
        self.assertIsNotNone(song)
        self.assertIn(" - ", song)
        self.assertTrue(vibe)


class TestVoiceMusicRouting(unittest.TestCase):
    def _make_handler(self):
        from handlers.voice import VoiceHandler
        bot = MagicMock()
        bot.chime_pcm = None
        bot.mumble = None
        bot.listening_enabled = True
        return VoiceHandler(bot), bot

    def test_specific_play_stays_direct(self):
        handler, bot = self._make_handler()
        result = handler.handle("Tester", "obama play hotel california")
        self.assertTrue(result)
        bot.play.assert_called_once_with("hotel california")
        bot.say_stream.assert_not_called()

    def test_vague_play_routes_to_recommendation(self):
        handler, bot = self._make_handler()
        bot.brain.recommend_song.return_value = ("Tycho - A Walk", "Chill vibes")
        result = handler.handle("Tester", "obama play something chill for coding")
        self.assertTrue(result)
        bot.brain.recommend_song.assert_called_once()
        bot.play.assert_called_once_with("Tycho - A Walk")

    def test_generic_soita_musiikkia_recommends(self):
        handler, bot = self._make_handler()
        bot.brain.recommend_song.return_value = ("ABBA - Dancing Queen", "Poppia")
        result = handler.handle("Tester", "obama soita musiikkia")
        self.assertTrue(result)
        bot.brain.recommend_song.assert_called_once()
        bot.play.assert_called_once_with("ABBA - Dancing Queen")

    def test_surprise_me_recommends(self):
        handler, bot = self._make_handler()
        bot.brain.recommend_song.return_value = ("Toto - Africa", "Yllätys")
        result = handler.handle("Tester", "obama surprise me")
        self.assertTrue(result)
        bot.brain.recommend_song.assert_called_once()
        bot.play.assert_called_once_with("Toto - Africa")


if __name__ == '__main__':
    unittest.main()
