# TeamSpeak 6 Support Plan — `USE_TEAMSPEAK` flag

> Status: PLAN ONLY. Mumble remains default. `USE_TEAMSPEAK=true` selects TeamSpeak 6 backend.
> Intended as iteration file for following agents to finish the implementation.

## 0. Locked decisions

- Selector: `USE_TEAMSPEAK=true/false` (default `false`).
- Voice scope: **full voice via bridge sidecar** (not text-only).
- Music: **disabled with message on TS6** (botamusique is Mumble-only).
- Python AI stack unchanged: Brain/Ear/Voice/AudioManager/Wakeword/handlers.

## 1. Why a bridge is required

- TS6 removed raw ServerQuery `:10011`. Only SSH query `:10022` + HTTP WebQuery remain.
- ServerQuery is text/control only (chat, move, presence). It cannot send/receive voice audio.
- No mature Python TS6-voice lib exists. Options: `honeybbq/teamspeak-js` (TS, `sendVoice(data,codec)`, `on("voice")`, Opus codecs 4/5) or `honeybbq/teamspeak-go`.
- Design: Python keeps all logic, speaks 48k mono s16le PCM. Node/Go sidecar is the TS voice client, piping PCM <-> Opus over localhost IPC.

Background research:

- `atsq` (PyPI): asyncio TeamSpeak ServerQuery client for TS3+TS6 over SSH. Only dep `asyncssh`, requires Python >=3.12. Tested against `teamspeak:3.13` and `teamspeaksystems/teamspeak6-server` containers. API: `await atsq.connect(host, 10022, password=..., server_id=1)`, `client_list`, `channel_create`, `@client.on("cliententerview")`, `run_forever()` with backoff + keepalive. Handles `QueryError`, `FloodError id 524` (needs `query_ip_allowlist.txt`).
- `tsbot` (PyPI, `jykob/TSBot`): async framework for TS ServerQuery bots, SSH default (`protocol='ssh'`), `TSBot(username, password, address)`, `@bot.command`, `@bot.on("cliententerview")`, auto-reconnect, rate-limiter.
- `joshii-h/ts3-query-proxy`: raw `:10011` -> SSH `:10022` translation layer for legacy tools (e.g. TS3MusicBot). Useful reference, not used directly.
- `honeybbq/teamspeak-js` + `teamspeak-go`: clean-room client-protocol libs (ECDH+RSA+EAX handshake). Support `sendVoice`, `on("voice")`, text messages, moves, file transfer. Only path to full voice without a real client binary + virtual cable.
- `E2cD3s/Teamspeak-AI-Assistant`: reference for virtual-cable approach (TS client + VB-CABLE + local Whisper/TTS). Rejected here in favor of bridge sidecar for headless Linux.

## 2. New env vars (`config.py` + `.env.example`)

```ini
USE_TEAMSPEAK=False
TS6_HOST=127.0.0.1
TS6_QUERY_PORT=10022
TS6_QUERY_USER=serveradmin
TS6_QUERY_PASSWORD=
TS6_SERVER_ID=1
TS6_NICKNAME=${MUMBLE_BOT_USERNAME}
TS6_CHANNEL=${MUMBLE_TARGET_CHANNEL}
TS6_CHANNEL_PASSWORD=
TS6_VOICE_HOST=${TS6_HOST}
TS6_VOICE_PORT=9987
TS6_SERVER_PASSWORD=
TS6_IDENTITY=
TS6_BRIDGE_RX_PORT=5001
TS6_BRIDGE_TX_PORT=5002
TS6_BRIDGE_TOKEN=
```

`config.py`: add `USE_TEAMSPEAK = os.getenv(...).lower()=="true"` + all `TS6_*` with fallbacks above.

## 3. Target architecture

```text
main.py -> MadnessBot (bot.py) -> self.backend: VoiceBackend
├── MumbleBackend (backends/mumble_backend.py) — extract current pymumble code
└── TeamspeakBackend (backends/teamspeak_backend.py)
    ├── QueryClient (atsq + asyncssh, SSH :10022) — text/presence/move
    └── BridgeSupervisor -> bridge/ts-voice-bridge/ (Node + teamspeak-js)
        RX: TS Opus -> decode -> 48k PCM -> UDP/TCP :5001 -> AudioManager.add_audio()
        TX: AudioManager/TTS 48k PCM -> :5002 -> encode Opus -> sendVoice()
```

`VoiceBackend` ABC (`backends/base.py`):

- `connect()/disconnect()/is_alive()`
- `move_to_channel(name)`
- `send_chat(text, target)`
- `play_pcm(bytes)`
- `clear_audio_buffer()`
- `list_users() -> [{name, id, channel}]`
- `my_channel_id`
- callbacks `on_text(sender,text)`, `on_audio(user,pcm48k)`, `on_join(user,channel)`

Current Mumble coupling to abstract (see `bot.py`):

- `pymumble_py3.Mumble(...)`, `set_bandwidth`, `sound_output.add_sound`
- `channels.find_by_name().move_in()`, `channels[id].send_text_message`
- callbacks `user_updated` / `text_received` / `sound_received`
- `users.myself`, `users.myself_session`, `users` dict
- music via `send_chat("!yplay ...")` to botamusique

## 4. Task checklist for implementing agents

### Phase 0 — Abstraction (no behavior change)

- [ ] Create `backends/base.py` ABC as above.
- [ ] Create `backends/mumble_backend.py` by moving `setup_mumble()`, bandwidth, `sound_output.add_sound`, `channels.find_by_name().move_in()`, `user_updated/text_received/sound_received` callbacks out of `bot.py`.
- [ ] Create `backends/__init__.py:create_backend(bot)` factory reading `config.USE_TEAMSPEAK`.
- [ ] Refactor `bot.py` to use only `self.backend` for: `play_ack_sound`, `play_action_confirmation`, `tts_worker`, `_generate_and_play_tts`, `send_chat`, `get_status`, `on_sound_received`, `on_user_updated`, `stop_speaking` (via `clear_audio_buffer()`).
- [ ] Keep `self.mumble` alias for Mumble backend only (test compat).
- [ ] Verify: `python -m pytest tests/` passes with `USE_TEAMSPEAK=False`.

### Phase 1 — TS6 query / text path

- [ ] Add `atsq` + `asyncssh` to `requirements.txt` (preferred over `tsbot`; asyncio-native, tested vs `teamspeaksystems/teamspeak6-server`). Pin versions, check py3.14 (repo runs 3.14.7; `atsq` claims 3.12–3.14+, `tsbot` 3.10+).
- [ ] Implement `backends/teamspeak_backend.py:QueryClient`: SSH login, `use <server_id>`, `servernotifyregister`, set nick, channel name → cid lookup + move, `sendtextmessage targetmode 2/1`, presence list for hourly reports/welcome, reconnect backoff, `quit` on close.
- [ ] Add `normalize_text_event()` adapter: map both pymumble `message.actor` and TS `notifytextmessage(invokername/msg/targetmode)` to `handle(sender_name, text)` core in `handlers/text.py`.
- [ ] `get_status()`: `"Backend": "mumble|teamspeak6"` + `"VoiceBridge": Connected/Down`.
- [ ] Music guard in `bot.py`: if `USE_TEAMSPEAK`, all `play/play_file/skip/stop_music/pause_music/resume_music/set_volume/repeat_music/set_mode/request_now_playing/request_queue/clear_queue` do `send_chat("🎵 Music via botamusique is not supported on TeamSpeak yet.")` and return `None`. No `!yplay` leaks to TS chat.
- [ ] Docs: query setup (`TSSERVER_QUERY_SSH_ENABLED=1`, `TSSERVER_QUERY_ADMIN_PASSWORD`, `query_ip_allowlist.txt`, flood 524 handling).

### Phase 2 — Voice bridge

- [ ] Scaffold `bridge/ts-voice-bridge/package.json` (`teamspeak-js`, opus lib e.g. `@discordjs/opus` or `opusscript`), `index.js`, `README`.
- [ ] Implement: connect as voice client (`identity, host:9987, nick, serverPassword, defaultChannel`), `clientMove`, `on("voice")` → Opus decode → 48k s16le → send to `TS6_BRIDGE_RX_PORT` (with `TS6_BRIDGE_TOKEN`); read `TS6_BRIDGE_TX_PORT` → Opus encode (codec 4/5 per server) → `sendVoice()`.
- [ ] Python `BridgeSupervisor`: spawn/supervise Node proc, health-check IPC sockets, restart on fail, expose `play_pcm()` / `on_audio()` with identical 48k PCM contract so `AudioManager`, `UserVoiceStream`, `Ear.transcribe`, `Voice.generate_pcm` need zero changes.
- [ ] Handle: server/channel passwords, `TS6_IDENTITY` generate/store/upgrade, reconnect + re-join, `MUMBLE_BANDWIDTH` is Mumble-only (no-op on TS).

### Phase 3 — Docs / examples / tests

- [ ] `.env.example` + `README.md`: `USE_TEAMSPEAK` section, ports (`9987/udp` voice, `10022/tcp` query), identity, music-unsupported note, arch diagram.
- [ ] Tests: new `tests/test_teamspeak_backend.py` (factory selection, text normalization, music guard, `stop_speaking` clears backend buffer, bridge PCM shape with fake sockets). Extend `tests/test_music_commands.py`. All old tests pass with flag off.
- [ ] Manual E2E vs docker `teamspeaksystems/teamspeak6-server`: `?ping/?status/?say`, wake → STT → LLM → TTS audible in TS, hourly report, reminders, music cmd shows unsupported, kill bridge → `VoiceBridge: Down` but text works, TS restart → auto-reconnect.

## 5. Acceptance criteria

- [ ] `USE_TEAMSPEAK=False` → byte-identical Mumble behavior, all existing tests pass.
- [ ] `USE_TEAMSPEAK=True` → join TS channel, text commands work, voice RX → LLM → TX works via bridge, music replies unsupported, status shows backend+bridge, reconnects survive bridge/TS restarts.

## 6. Risks

- Opus codec 4 vs 5 negotiation — bridge must auto-select.
- TS channel name → cid duplicates — define policy (exact match, first hit + warning).
- Query flood / allowlist — document `query_ip_allowlist.txt`.
- Fresh identity security level blocked — document upgrade.
- `set_bandwidth` Mumble-only.

## 7. Suggested agent order

1. Phase 0 refactor → run `pytest`.
2. Phase 1 query + music guard + tests.
3. Phase 2 bridge + supervisor + E2E.
4. Phase 3 docs + full verification.
