import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.recommender import MusicRecommender
import config

class TestEnhancedRecommender(unittest.TestCase):
    def test_normalize_track_strips_noise(self):
        recommender = MusicRecommender()
        self.assertEqual(recommender._normalize_track("Queen - Bohemian Rhapsody [Official Video]"), "queen bohemian rhapsody")
        self.assertEqual(recommender._normalize_track("Daft Punk - One More Time (Remastered 2021)"), "daft punk one more time")
        self.assertEqual(recommender._normalize_track("Kavinsky - Nightcall (feat. Lovefoxxx)"), "kavinsky nightcall")

    @patch('requests.get')
    def test_verify_track_on_itunes(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"artistName": "Queen", "trackName": "Bohemian Rhapsody"}
            ]
        }
        mock_get.return_value = mock_response

        recommender = MusicRecommender()
        res = recommender.verify_track_on_itunes("Queen - Bohemian Rhapsody")
        self.assertEqual(res, "Queen - Bohemian Rhapsody")

        # Test failure fallback to None
        mock_response.json.return_value = {"results": []}
        res_fail = recommender.verify_track_on_itunes("Unknown Song")
        self.assertIsNone(res_fail)

    def test_parse_recommendation_output(self):
        from modules.brain import Brain
        with patch('modules.brain.LLM_AVAILABLE', False):
            brain = Brain()
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

    @patch('modules.recommender.MusicRecommender.verify_track_on_itunes')
    def test_recommend_song_fallback_mode(self, mock_verify):
        mock_verify.side_effect = lambda x: x
        from modules.brain import Brain
        with patch('modules.brain.LLM_AVAILABLE', False):
            brain = Brain()
            brain.recommender.get_recommendation = MagicMock(return_value="Daft Punk - One More Time")
            song = brain.recommend_song("chill music")
            self.assertEqual(song, "Daft Punk - One More Time")

    @patch('modules.recommender.MusicRecommender.verify_track_on_itunes')
    def test_recommend_song_return_meta(self, mock_verify):
        mock_verify.side_effect = lambda x: x
        from modules.brain import Brain
        with patch('modules.brain.LLM_AVAILABLE', True):
            with patch('modules.brain.Brain.check_connection', return_value=True):
                brain = Brain()
                brain.llm = MagicMock()
                brain.llm.return_value = {
                    "choices": [{
                        "message": {
                            "content": "[INTENT]\nGENRE_MOOD\n[VIBE]\nChill late night coding vibes\n[RECOMMENDATIONS]\n1. Tycho - A Walk\n2. Bonobo - Kerala"
                        }
                    }]
                }
                song, vibe = brain.recommend_song("chill music", return_meta=True)
                self.assertEqual(song, "Tycho - A Walk")
                self.assertEqual(vibe, "Chill late night coding vibes")

    @patch('modules.recommender.MusicRecommender.verify_track_on_itunes')
    def test_recommend_song_specific_bypass_history(self, mock_verify):
        mock_verify.side_effect = lambda x: x
        from modules.brain import Brain
        with patch('modules.brain.LLM_AVAILABLE', True):
            with patch('modules.brain.Brain.check_connection', return_value=True):
                brain = Brain()
                brain.llm = MagicMock()
                brain.llm.return_value = {
                    "choices": [{
                        "message": {
                            "content": "[INTENT]\nSPECIFIC\n[VIBE]\nQueen Rock\n[RECOMMENDATIONS]\nQueen - Bohemian Rhapsody\nQueen - Under Pressure"
                        }
                    }]
                }
                brain.recommender.history = ["Queen - Bohemian Rhapsody"]
                
                song = brain.recommend_song("play bohemian rhapsody")
                self.assertEqual(song, "Queen - Bohemian Rhapsody")

                brain.llm.return_value = {
                    "choices": [{
                        "message": {
                            "content": "[INTENT]\nGENRE_MOOD\n[VIBE]\nQueen Rock\n[RECOMMENDATIONS]\nQueen - Bohemian Rhapsody\nQueen - Under Pressure"
                        }
                    }]
                }
                song = brain.recommend_song("play some Queen vibe")
                self.assertEqual(song, "Queen - Under Pressure")

if __name__ == '__main__':
    unittest.main()
