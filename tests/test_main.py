from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import patch

import config


MAIN_PATH = Path(__file__).resolve().parents[1] / "main.py"


def _build_fake_bot_module(run_calls):
    class _FakeBot:
        def run(self):
            run_calls.append(1)

    module = types.ModuleType("bot")
    module.MadnessBot = _FakeBot
    return module


def _run_main_with_args(args):
    run_calls = []
    fake_bot_module = _build_fake_bot_module(run_calls)
    with patch.object(sys, "argv", ["main.py", *args]):
        with patch.dict(sys.modules, {"bot": fake_bot_module}):
            runpy.run_path(str(MAIN_PATH), run_name="__main__")
    return len(run_calls)


class MainStartupTests(unittest.TestCase):
    def test_default_startup_does_not_force_api_flags(self):
        with patch.object(config, "START_LLM_API_WITH_BOT", False), patch.object(config, "START_VOICE_API_WITH_BOT", False):
            run_calls = _run_main_with_args([])
            self.assertFalse(config.START_LLM_API_WITH_BOT)
            self.assertFalse(config.START_VOICE_API_WITH_BOT)
            self.assertEqual(run_calls, 1)

    def test_api_flag_forces_api_flags_on(self):
        with patch.object(config, "START_LLM_API_WITH_BOT", False), patch.object(config, "START_VOICE_API_WITH_BOT", False):
            run_calls = _run_main_with_args(["--api"])
            self.assertTrue(config.START_LLM_API_WITH_BOT)
            self.assertTrue(config.START_VOICE_API_WITH_BOT)
            self.assertEqual(run_calls, 1)


if __name__ == "__main__":
    unittest.main()
