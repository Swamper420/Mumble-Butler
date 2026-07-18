import unittest
from unittest.mock import MagicMock
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from handlers.text import TextHandler
from utils import get_resample_indices
from modules.audio_buffer import UserVoiceStream

class TestNewFixes(unittest.TestCase):
    def test_say_command_character_limit(self):
        bot = MagicMock()
        bot.mumble = MagicMock()
        bot.mumble.users = {2: {"name": "Tester"}}
        bot.mumble.users.myself_session = 1
        
        handler = TextHandler(bot)
        
        # Test text under 1000 characters
        message_ok = MagicMock()
        message_ok.actor = 2
        message_ok.message = "?say hello"
        handler.handle(message_ok)
        bot.say_async.assert_called_once_with("hello", user="Tester")
        bot.send_chat.assert_not_called()
        
        # Test text over 1000 characters
        bot.say_async.reset_mock()
        bot.send_chat.reset_mock()
        
        message_long = MagicMock()
        message_long.actor = 2
        message_long.message = "?say " + ("a" * 1001)
        handler.handle(message_long)
        bot.say_async.assert_not_called()
        bot.send_chat.assert_called_once()
        self.assertIn("limited to 1000 characters", bot.send_chat.call_args[0][0])

    def test_remind_text_command(self):
        bot = MagicMock()
        bot.mumble = MagicMock()
        bot.mumble.users = {2: {"name": "Tester"}}
        bot.mumble.users.myself_session = 1
        
        handler = TextHandler(bot)
        
        # Test valid ?remind in 10 minutes about standup
        message = MagicMock()
        message.actor = 2
        message.message = "?remind in 10 minutes about standup"
        handler.handle(message)
        bot.schedule_reminder.assert_called_once_with(10 * 60, "standup")
        bot.send_chat.assert_called_once()
        self.assertIn("I will remind you in 10 minutes about standup", bot.send_chat.call_args[0][0])
        
        # Test valid ?remind 5 seconds break
        bot.schedule_reminder.reset_mock()
        bot.send_chat.reset_mock()
        message2 = MagicMock()
        message2.actor = 2
        message2.message = "?remind 5 seconds break"
        handler.handle(message2)
        bot.schedule_reminder.assert_called_once_with(5, "break")
        
        # Test invalid syntax
        bot.schedule_reminder.reset_mock()
        bot.send_chat.reset_mock()
        message_invalid = MagicMock()
        message_invalid.actor = 2
        message_invalid.message = "?remind tomorrow"
        handler.handle(message_invalid)
        bot.schedule_reminder.assert_not_called()
        self.assertIn("Usage", bot.send_chat.call_args[0][0])

    def test_audio_buffer_cutoff(self):
        stream = UserVoiceStream("Tester", bot=None)
        # 1 second of audio is 96000 bytes. 11 seconds is 1056000 bytes.
        dummy_audio = bytes([0] * 1056000)
        stream.add_data(dummy_audio)
        
        # Should be truncated to 10 seconds (960000 bytes)
        self.assertEqual(len(stream.buffer), 960000)

    def test_resample_cache_lru(self):
        # Clear cache info first
        get_resample_indices.cache_clear()
        
        # Call it with various parameters
        indices1 = get_resample_indices(1000, 48000, 16000)
        indices2 = get_resample_indices(1000, 48000, 16000)
        self.assertIs(indices1, indices2)  # Should be cached same object
        
        info = get_resample_indices.cache_info()
        self.assertEqual(info.hits, 1)
        self.assertEqual(info.misses, 1)

if __name__ == "__main__":
    unittest.main()
