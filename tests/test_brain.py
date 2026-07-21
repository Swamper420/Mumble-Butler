"""Tests for Brain.generate_response behaviour."""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

import config


def _make_brain_with_mock_llm(llm_mock):
    """Return a Brain instance whose internal llm is replaced by *llm_mock*."""
    from modules import brain as brain_mod
    with patch.object(brain_mod, "LLM_AVAILABLE", True):
        with patch.object(brain_mod.Brain, "check_connection", return_value=True):
            b = brain_mod.Brain()
            b.llm = llm_mock
    return b


class TestGenerateResponseStopTokens(unittest.TestCase):
    """Ensure generate_response does not include '\\n' in stop tokens."""

    def _captured_stop_tokens(self):
        """Run generate_response and return the stop list passed to self.llm."""
        llm_mock = MagicMock()
        llm_mock.create_chat_completion.return_value = {
            "choices": [{"message": {"content": "Line one.\nLine two.\nLine three."}}]
        }

        brain = _make_brain_with_mock_llm(llm_mock)
        brain.generate_response("Hello")

        _args, kwargs = llm_mock.create_chat_completion.call_args
        return kwargs.get("stop", [])

    def test_newline_not_in_stop_tokens(self):
        stop = self._captured_stop_tokens()
        self.assertIsNone(stop, "stop should be None by default so Ollama uses native model stop tokens")


class TestSystemPromptNotBrief(unittest.TestCase):
    """Ensure the bot system prompt instructs concise answers."""

    def test_system_prompt_does_not_say_brief(self):
        self.assertNotIn(
            "brief",
            config.SYSTEM_PROMPT.lower(),
            "SYSTEM_PROMPT should not tell the model to keep answers brief"
        )

    def test_system_prompt_contains_english_instruction(self):
        self.assertIn(
            "ENGLISH",
            config.SYSTEM_PROMPT,
            "SYSTEM_PROMPT should still instruct the model to respond in ENGLISH"
        )

    def test_system_prompt_instructs_short_responses(self):
        prompt_lower = config.SYSTEM_PROMPT.lower()
        self.assertTrue(
            "short" in prompt_lower or "concise" in prompt_lower,
            "SYSTEM_PROMPT should instruct the bot to keep responses short/concise"
        )



class TestShutupKeywords(unittest.TestCase):
    """Ensure SHUTUP_KEYWORDS is defined in config."""

    def test_shutup_keywords_exist(self):
        self.assertTrue(
            hasattr(config, 'SHUTUP_KEYWORDS'),
            "config must define SHUTUP_KEYWORDS"
        )
        self.assertIsInstance(config.SHUTUP_KEYWORDS, list)
        self.assertGreater(len(config.SHUTUP_KEYWORDS), 0)

    def test_shutup_keywords_contains_shut_up(self):
        self.assertIn("shut up", config.SHUTUP_KEYWORDS)


if __name__ == "__main__":
    unittest.main()
