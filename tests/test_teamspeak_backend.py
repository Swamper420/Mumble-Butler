"""Tests for TeamSpeak 6 backend (USE_TEAMSPEAK flag).

Covers (ts6plan.md Phase 3):
- factory selection (mumble vs teamspeak6)
- text normalization (pymumble actor + TS notifytextmessage -> sender/text)
- music guard (no !yplay leaks to TS chat)
- stop_speaking clears backend buffer
- bridge PCM framing with fake sockets (no network needed)
"""
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import config
from backends.teamspeak_backend import (
    normalize_text_event,
    ts_escape,
    ts_unescape,
    parse_ts_kv,
    build_rx_packet,
    parse_rx_packet,
    build_tx_packet,
    parse_tx_packet,
    TeamspeakBackend,
    BridgeSupervisor,
)
from backends.mumble_backend import MumbleBackend


class FactorySelectionTests(unittest.TestCase):
    def test_factory_selects_mumble_by_default(self):
        with patch.object(config, "USE_TEAMSPEAK", False):
            from backends import create_backend
            bot = MagicMock()
            backend = create_backend(bot)
            self.assertIsInstance(backend, MumbleBackend)
            self.assertEqual(backend.backend_name, "mumble")

    def test_factory_selects_teamspeak_when_flag_on(self):
        with patch.object(config, "USE_TEAMSPEAK", True):
            from backends import create_backend
            bot = MagicMock()
            backend = create_backend(bot)
            self.assertIsInstance(backend, TeamspeakBackend)
            self.assertEqual(backend.backend_name, "teamspeak6")


class QueryEscapeTests(unittest.TestCase):
    def test_escape_unescape_roundtrip(self):
        original = "hello world | slash/test"
        self.assertEqual(ts_unescape(ts_escape(original)), original)

    def test_parse_kv(self):
        params = parse_ts_kv(r"clid=1 cid=2 client_nickname=Obama\sBot msg=hello\sworld")
        self.assertEqual(params["clid"], "1")
        self.assertEqual(params["client_nickname"], "Obama Bot")
        self.assertEqual(params["msg"], "hello world")


class NormalizeTextEventTests(unittest.TestCase):
    def test_pymumble_actor_resolution(self):
        bot = MagicMock()
        bot.mumble = SimpleNamespace(
            users={2: {"name": "Tester"}, 1: {"name": "Obama"}},
        )
        bot.mumble.users = {2: {"name": "Tester"}}
        # myself_session lives on the users container in prod; attach manually
        bot.backend = MagicMock()
        bot.backend.list_users.return_value = [{"name": "Tester", "id": 2, "channel": 0}]
        msg = SimpleNamespace(actor=2, message="?ping")
        result = normalize_text_event(msg, bot=bot)
        self.assertEqual(result, ("Tester", "?ping"))

    def test_ts_dict_event(self):
        result = normalize_text_event(
            {"invokername": "Alice", "msg": "?status"}, bot=None
        )
        self.assertEqual(result, ("Alice", "?status"))

    def test_ts_raw_notify_line(self):
        line = r"notifytextmessage targetmode=2 msg=?ping invokername=Bob invokerid=5"
        result = normalize_text_event(line, bot=None)
        self.assertEqual(result, ("Bob", "?ping"))

    def test_tuple_passthrough(self):
        self.assertEqual(
            normalize_text_event(("Alice", "?ping")), ("Alice", "?ping")
        )

    def test_ignored_user_filtered(self):
        with patch.object(config, "IGNORED_USERS", ["YoMusicBot"]):
            self.assertIsNone(normalize_text_event(("YoMusicBot", "?ping")))
            self.assertIsNone(
                normalize_text_event({"invokername": "YoMusicBot", "msg": "?ping"})
            )

    def test_self_message_filtered(self):
        with patch.object(config, "BOT_USERNAME", "Obama"):
            with patch.object(config, "TS6_NICKNAME", "Obama"):
                self.assertIsNone(normalize_text_event(("Obama", "?ping")))

    def test_empty_text_filtered(self):
        self.assertIsNone(normalize_text_event(("Alice", "   ")))
        self.assertIsNone(normalize_text_event(("Alice", "")))


class BridgeFramingTests(unittest.TestCase):
    def test_rx_roundtrip_no_token(self):
        pcm = b"\x01\x02" * 960  # one 20ms frame
        packet = build_rx_packet("Alice", pcm)
        parsed = parse_rx_packet(packet)
        self.assertIsNotNone(parsed)
        user, out = parsed
        self.assertEqual(user, "Alice")
        self.assertEqual(out, pcm)

    def test_rx_token_auth(self):
        pcm = b"\x03\x04" * 100
        packet = build_rx_packet("Bob", pcm, token="secret")
        # Correct token parses
        self.assertEqual(parse_rx_packet(packet, token="secret")[0], "Bob")
        # Wrong / missing token rejected
        self.assertIsNone(parse_rx_packet(packet, token="wrong"))
        self.assertIsNone(parse_rx_packet(packet, token=""))

    def test_rx_rejects_odd_pcm(self):
        packet = build_rx_packet("Alice", b"\x01\x02\x03")
        self.assertIsNone(parse_rx_packet(packet))

    def test_tx_roundtrip(self):
        pcm = b"\x05\x06" * 500
        packet = build_tx_packet(pcm, token="tok")
        self.assertEqual(parse_tx_packet(packet, token="tok"), pcm)
        self.assertIsNone(parse_tx_packet(packet, token="wrong"))

    def test_tx_rejects_empty_and_odd(self):
        self.assertIsNone(parse_tx_packet(b""))
        self.assertIsNone(parse_tx_packet(b"\x01"))

    def test_bridge_play_pcm_uses_fake_socket(self):
        received = []

        class FakeSocket:
            def sendto(self, data, addr):
                received.append((data, addr))

        sup = BridgeSupervisor(on_audio=None, rx_port=5011, tx_port=5012,
                               token="t", enabled=True)
        sup._tx_sock = FakeSocket()
        # Stub proc supervision (no node binary in CI)
        sup._ensure_proc = lambda: None
        pcm = b"\x01\x02" * 3000  # > one 5760B frame -> multiple datagrams
        self.assertTrue(sup.play_pcm(pcm))
        self.assertGreaterEqual(len(received), 2)
        # Each datagram individually token-framed and parseable
        reassembled = b"".join(parse_tx_packet(d, token="t") for d, _ in received)
        self.assertEqual(reassembled, pcm)

    def test_bridge_rx_dispatches_to_on_audio(self):
        got = []
        sup = BridgeSupervisor(on_audio=lambda u, p: got.append((u, p)),
                               rx_port=5013, tx_port=5014, token="", enabled=True)
        pcm = b"\x07\x08" * 960
        packet = build_rx_packet("Carol", pcm)
        # Simulate what _rx_loop does on recv
        parsed = parse_rx_packet(packet, sup.token)
        self.assertIsNotNone(parsed)
        sup.on_audio(*parsed)
        self.assertEqual(got, [("Carol", pcm)])


class MusicGuardTests(unittest.TestCase):
    def _make_bot(self):
        # Import bot lazily with heavy deps stubbed like existing tests do.
        import importlib.util
        from pathlib import Path
        BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
        module_name = "bot_under_test_ts6"
        if module_name in sys.modules:
            del sys.modules[module_name]
        fake_pymumble = types.ModuleType("pymumble_py3")
        fake_pymumble.Mumble = object
        fake_utils = types.ModuleType("utils")
        fake_utils.patch_ssl = lambda: None
        fake_utils.setup_logger = lambda name="x", level=None: MagicMock()
        fake_brain = types.ModuleType("modules.brain")
        fake_brain.Brain = MagicMock
        fake_ears = types.ModuleType("modules.ears")
        fake_ears.Ear = MagicMock
        fake_voice = types.ModuleType("modules.voice")
        fake_voice.Voice = MagicMock
        fake_audio_manager = types.ModuleType("modules.audio_manager")
        fake_audio_manager.AudioManager = MagicMock
        fake_text = types.ModuleType("handlers.text")
        fake_text.TextHandler = MagicMock
        fake_voice_handler = types.ModuleType("handlers.voice")
        fake_voice_handler.VoiceHandler = MagicMock
        # Wakeword stub
        import modules.wakeword as real_wakeword  # noqa: F401 (ensure package importable)
        spec = importlib.util.spec_from_file_location(module_name, BOT_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        patched = {
            "pymumble_py3": fake_pymumble,
            "utils": fake_utils,
            "modules.brain": fake_brain,
            "modules.ears": fake_ears,
            "modules.voice": fake_voice,
            "modules.audio_manager": fake_audio_manager,
            "handlers.text": fake_text,
            "handlers.voice": fake_voice_handler,
        }
        originals = {}
        try:
            for name, fake in patched.items():
                originals[name] = sys.modules.get(name)
                sys.modules[name] = fake
            spec.loader.exec_module(module)
            return module
        finally:
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

    def test_music_commands_blocked_on_teamspeak(self):
        bot_module = self._make_bot()
        bot = bot_module.MadnessBot.__new__(bot_module.MadnessBot)
        sent = []
        bot.send_chat = sent.append
        # Fake TS backend
        bot.backend = SimpleNamespace(backend_name="teamspeak6")
        with patch.object(config, "USE_TEAMSPEAK", True):
            self.assertIsNone(bot.play("some song"))
            self.assertIsNone(bot.play_file("x"))
            self.assertIsNone(bot.skip())
            self.assertIsNone(bot.stop_music())
            self.assertIsNone(bot.pause_music())
            self.assertIsNone(bot.resume_music())
            self.assertIsNone(bot.set_volume(50))
            self.assertIsNone(bot.repeat_music(2))
            self.assertIsNone(bot.set_mode("random"))
            self.assertIsNone(bot.request_now_playing())
            self.assertIsNone(bot.request_queue())
            self.assertIsNone(bot.clear_queue())
        # No botamusique leaks
        for msg in sent:
            self.assertNotIn("!yplay", msg)
            self.assertNotIn("!play", msg)
            self.assertNotIn("!skip", msg)
        # Unsupported notice was sent
        self.assertTrue(any("not supported on TeamSpeak" in m for m in sent))

    def test_music_commands_work_on_mumble(self):
        bot_module = self._make_bot()
        bot = bot_module.MadnessBot.__new__(bot_module.MadnessBot)
        sent = []
        bot.send_chat = sent.append
        bot.backend = SimpleNamespace(backend_name="mumble")
        with patch.object(config, "USE_TEAMSPEAK", False):
            self.assertEqual(bot.play("lofi mix"), "!yplay lofi mix")
            self.assertEqual(bot.skip(), "!skip")
        self.assertIn("!yplay lofi mix", sent)

    def test_stop_speaking_clears_backend_buffer(self):
        bot_module = self._make_bot()
        bot = bot_module.MadnessBot.__new__(bot_module.MadnessBot)
        bot.speech_generation = 0
        bot.loop = SimpleNamespace(call_soon_threadsafe=lambda func, *a: func(*a))

        class FakeQueue:
            def __init__(self):
                self.items = [(0, "x")]
            def get_nowait(self):
                if not self.items:
                    raise bot_module.asyncio.QueueEmpty()
                return self.items.pop(0)
            def task_done(self):
                pass

        bot.queue = FakeQueue()
        backend = SimpleNamespace(clear_audio_buffer=MagicMock(return_value=True))
        bot.backend = backend
        bot.mumble = SimpleNamespace(sound_output=MagicMock())
        bot.stop_speaking()
        self.assertEqual(bot.speech_generation, 1)
        backend.clear_audio_buffer.assert_called_once_with()


class TeamspeakBackendUnitTests(unittest.TestCase):
    def test_list_users_filters_query_clients(self):
        bot = MagicMock()
        query = MagicMock()
        query.list_clients.return_value = [
            {"clid": 1, "cid": 5, "nickname": "Alice", "type": 0},
            {"clid": 2, "cid": 5, "nickname": "serveradmin", "type": 1},
        ]
        backend = TeamspeakBackend(bot, query=query, bridge=MagicMock())
        users = backend.list_users()
        self.assertEqual(users, [{"name": "Alice", "id": 1, "channel": 5}])

    def test_send_chat_defaults_to_channel(self):
        bot = MagicMock()
        query = MagicMock()
        backend = TeamspeakBackend(bot, query=query, bridge=MagicMock())
        backend.send_chat("hello")
        query.send_channel_message.assert_called_once_with("hello")

    def test_status_shows_backend_and_bridge(self):
        from handlers.text import TextHandler  # noqa: F401 (import check)
        bot_module_name = "bot_under_test_ts6_status"
        # Build a minimal bot-like object to test get_status shape
        import importlib.util
        from pathlib import Path
        BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
        if bot_module_name in sys.modules:
            del sys.modules[bot_module_name]
        fake = types.ModuleType("pymumble_py3")
        fake.Mumble = object
        fu = types.ModuleType("utils")
        fu.patch_ssl = lambda: None
        fu.setup_logger = lambda name="x", level=None: MagicMock()
        for mod_name, cls_name in [
            ("modules.brain", "Brain"), ("modules.ears", "Ear"),
            ("modules.voice", "Voice"), ("modules.audio_manager", "AudioManager"),
            ("handlers.text", "TextHandler"), ("handlers.voice", "VoiceHandler"),
        ]:
            m = types.ModuleType(mod_name)
            setattr(m, cls_name, MagicMock)
            sys.modules[mod_name] = m
        sys.modules["pymumble_py3"] = fake
        sys.modules["utils"] = fu
        try:
            spec = importlib.util.spec_from_file_location(bot_module_name, BOT_PATH)
            module = importlib.util.module_from_spec(spec)
            sys.modules[bot_module_name] = module
            spec.loader.exec_module(module)
            bot = module.MadnessBot.__new__(module.MadnessBot)
            bot.start_time = 0
            bot.brain = SimpleNamespace(llm=True, memory_enabled=True)
            bot.ear = object()
            bot.voice = object()
            bot.wakeword_detector = SimpleNamespace(enabled=True)
            bot.listening_enabled = True
            bot.mumble = None
            bot.backend = SimpleNamespace(
                backend_name="teamspeak6",
                is_alive=lambda: True,
                voice_bridge_status="Down",
            )
            with patch.object(config, "USE_TEAMSPEAK", True):
                status = module.MadnessBot.get_status(bot)
            self.assertEqual(status["Backend"], "teamspeak6")
            self.assertEqual(status["VoiceBridge"], "Down")
            self.assertIn("TeamSpeak", status)
        finally:
            for mod_name in ["pymumble_py3", "utils", "modules.brain", "modules.ears",
                             "modules.voice", "modules.audio_manager",
                             "handlers.text", "handlers.voice", bot_module_name]:
                sys.modules.pop(mod_name, None)

    def test_text_handler_ts_ping(self):
        from handlers.text import TextHandler
        bot = MagicMock()
        bot.mumble = None
        bot.backend = MagicMock()
        bot.backend.list_users.return_value = []
        handler = TextHandler(bot)
        handler.handle_text("Tester", "?ping")
        bot.send_chat.assert_called_once_with("Pong!")

    def test_set_bandwidth_noop_on_ts(self):
        bot = MagicMock()
        backend = TeamspeakBackend(bot, query=MagicMock(), bridge=MagicMock())
        self.assertIsNone(backend.set_bandwidth(64000))


if __name__ == "__main__":
    unittest.main()
