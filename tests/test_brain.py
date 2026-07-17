"""Tests for Brain.generate_response behaviour (no llama_cpp required)."""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

import config


def _make_brain_with_mock_llm(llm_mock):
    """Return a Brain instance whose internal llm is replaced by *llm_mock*."""
    # Stub out llama_cpp so the module loads without the native library.
    fake_llama_cpp = types.ModuleType("llama_cpp")
    fake_llama_cpp.Llama = MagicMock(return_value=llm_mock)
    with patch.dict(sys.modules, {"llama_cpp": fake_llama_cpp}):
        from modules import brain as brain_mod
        # Patch LLM_AVAILABLE so __init__ actually creates self.llm
        with patch.object(brain_mod, "LLM_AVAILABLE", True):
            b = brain_mod.Brain()
            # Directly set the llm to our mock to bypass model loading
            b.llm = llm_mock
    return b


class TestGenerateResponseStopTokens(unittest.TestCase):
    """Ensure generate_response does not include '\\n' in stop tokens."""

    def _captured_stop_tokens(self):
        """Run generate_response and return the stop list passed to self.llm."""
        llm_mock = MagicMock(return_value={
            "choices": [{"text": "Line one.\nLine two.\nLine three."}]
        })

        brain = _make_brain_with_mock_llm(llm_mock)
        brain.generate_response("Hello")

        _args, kwargs = llm_mock.call_args
        return kwargs.get("stop", [])

    def test_newline_not_in_stop_tokens(self):
        stop = self._captured_stop_tokens()
        self.assertNotIn("\n", stop, "\\n must not be a stop token — it truncates multi-line answers")

    def test_im_end_still_in_stop_tokens(self):
        stop = self._captured_stop_tokens()
        self.assertIn("<|im_end|>", stop, "<|im_end|> should remain a stop token to delimit ChatML turns")


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
