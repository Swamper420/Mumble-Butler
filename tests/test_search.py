import unittest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.search import WebSearcher
import config


class TestWebSearcher(unittest.TestCase):
    def test_should_search(self):
        searcher = WebSearcher()
        searcher.enabled = True

        # Explicit triggers
        self.assertTrue(searcher.should_search("search weather in London"))
        self.assertTrue(searcher.should_search("look up latest tech news"))
        self.assertTrue(searcher.should_search("what is the weather today"))

        # Temporal + Topic triggers
        self.assertTrue(searcher.should_search("weather forecast for today"))
        self.assertTrue(searcher.should_search("latest news about election"))

        # Non-search queries
        self.assertFalse(searcher.should_search("tell me a joke"))
        self.assertFalse(searcher.should_search("what is a function in python"))

    @patch('requests.post')
    def test_search_parsing(self, mock_post):
        mock_html = """
        <html>
            <body>
                <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fweather.com%2Fhelsinki">Helsinki Weather - Today</a>
                <a class="result__snippet">Clear sky with a high of 22°C.</a>
            </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.text = mock_html
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        searcher = WebSearcher()
        results = searcher.search("weather in Helsinki")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Helsinki Weather - Today")
        self.assertEqual(results[0]["snippet"], "Clear sky with a high of 22°C.")
        self.assertEqual(results[0]["url"], "https://weather.com/helsinki")

    def test_format_search_context(self):
        searcher = WebSearcher()
        results = [
            {
                "title": "Helsinki Weather",
                "snippet": "22°C Sunny",
                "url": "https://weather.com"
            }
        ]
        context = searcher.format_search_context("weather in Helsinki", results)
        self.assertIn("Helsinki Weather", context)
        self.assertIn("22°C Sunny", context)
        self.assertIn("https://weather.com", context)


class TestBrainSearchIntegration(unittest.TestCase):
    @patch('modules.search.WebSearcher.search')
    def test_brain_search_trigger(self, mock_search):
        mock_search.return_value = [
            {"title": "Test Title", "snippet": "Test Snippet", "url": "http://example.com"}
        ]
        from modules.brain import Brain
        with patch('modules.brain.LLM_AVAILABLE', True):
            with patch('modules.brain.Brain.check_connection', return_value=True):
                brain = Brain()
                brain.llm = MagicMock()
                brain.llm.return_value = {
                    "choices": [{"message": {"content": "The weather is sunny."}}]
                }

                response = brain.generate_response("what is the weather today")
                mock_search.assert_called_once()
                self.assertIn("sunny", response.lower())


if __name__ == '__main__':
    unittest.main()
