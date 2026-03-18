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


class TestApiSystemPrompt(unittest.TestCase):
    """Ensure API_SYSTEM_PROMPT exists and differs from SYSTEM_PROMPT."""

    def test_api_system_prompt_exists(self):
        self.assertTrue(
            hasattr(config, 'API_SYSTEM_PROMPT'),
            "config must define API_SYSTEM_PROMPT"
        )

    def test_api_system_prompt_contains_english_instruction(self):
        self.assertIn(
            "ENGLISH",
            config.API_SYSTEM_PROMPT,
            "API_SYSTEM_PROMPT should instruct the model to respond in ENGLISH"
        )

    def test_api_system_prompt_encourages_detailed_answers(self):
        prompt_lower = config.API_SYSTEM_PROMPT.lower()
        self.assertTrue(
            "detailed" in prompt_lower or "thorough" in prompt_lower,
            "API_SYSTEM_PROMPT should encourage detailed/thorough answers"
        )

    def test_api_prompt_does_not_say_short(self):
        prompt_lower = config.API_SYSTEM_PROMPT.lower()
        self.assertNotIn(
            "short",
            prompt_lower,
            "API_SYSTEM_PROMPT should not tell the model to keep answers short"
        )


class TestGenerateApiResponse(unittest.TestCase):
    """Ensure generate_api_response uses API_SYSTEM_PROMPT."""

    def test_api_response_uses_api_system_prompt(self):
        llm_mock = MagicMock(return_value={
            "choices": [{"text": "A detailed answer about the topic."}]
        })

        brain = _make_brain_with_mock_llm(llm_mock)
        brain.generate_api_response("Tell me about Python")

        _args, _kwargs = llm_mock.call_args
        prompt_str = _args[0]
        self.assertIn(
            "detailed",
            prompt_str.lower(),
            "generate_api_response should include API_SYSTEM_PROMPT (with 'detailed')"
        )

    def test_api_response_returns_text(self):
        llm_mock = MagicMock(return_value={
            "choices": [{"text": "A thorough answer."}]
        })

        brain = _make_brain_with_mock_llm(llm_mock)
        result = brain.generate_api_response("Question")
        self.assertEqual(result, "A thorough answer.")

    def test_api_response_offline(self):
        llm_mock = MagicMock()
        brain = _make_brain_with_mock_llm(llm_mock)
        brain.llm = None
        result = brain.generate_api_response("Question")
        self.assertEqual(result, "My brain is offline.")

    def test_api_response_error_handling(self):
        llm_mock = MagicMock(side_effect=RuntimeError("LLM crashed"))
        brain = _make_brain_with_mock_llm(llm_mock)
        result = brain.generate_api_response("Question")
        self.assertIn("Thinking error", result)
        self.assertIn("LLM crashed", result)


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
