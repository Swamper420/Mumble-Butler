# ts-voice-bridge — TeamSpeak 6 voice sidecar

Python keeps all AI logic (Brain/Ear/Voice/AudioManager/Wakeword/handlers).
This Node process is only the TeamSpeak voice client: it pipes
`PCM <-> Opus` over localhost UDP so Python sees the identical
48 kHz mono s16le contract as Mumble.

```
TS voice --Opus--> bridge --PCM UDP :5001--> Python AudioManager.add_audio()
Python TTS --PCM UDP :5002--> bridge --Opus sendVoice()--> TS voice
```

Framing must match `backends/teamspeak_backend.py`:

- RX (bridge → Python, UDP `:5001`):
  `[TOKEN + "|" if TS6_BRIDGE_TOKEN] + [name_len:1][name utf8][pcm48k]`
- TX (Python → bridge, UDP `:5002`):
  raw 48k s16le PCM chunks (~60 ms / 5760 B), each individually
  `TOKEN`-prefixed when set. The bridge re-frames to 20 ms (960-sample)
  Opus frames before `sendVoice()`.

## Install

```bash
cd bridge/ts-voice-bridge
npm install
```

Needs `teamspeak-js` plus an Opus lib (`@discordjs/opus` preferred,
`opusscript` fallback). Opus codec 4 (Music) vs 5 (Voice) is auto-selected;
voice (5) is preferred.

## Configure

Env mirrors `config.py` `TS6_*` (see `.env.example`):

```ini
USE_TEAMSPEAK=True
TS6_VOICE_HOST=127.0.0.1
TS6_VOICE_PORT=9987
TS6_NICKNAME=Obama
TS6_SERVER_PASSWORD=
TS6_CHANNEL=General
TS6_CHANNEL_PASSWORD=
TS6_IDENTITY=          # empty = generate once, then persist the printed value
TS6_BRIDGE_RX_PORT=5001
TS6_BRIDGE_TX_PORT=5002
TS6_BRIDGE_TOKEN=
```

Notes:

- Fresh identities may be blocked by the server security level — connect once
  with a real client to upgrade, or persist a pre-upgraded `TS6_IDENTITY`.
- Duplicate `TS6_CHANNEL` names: Python query side uses exact match, first hit
  + warning. Keep channel names unique.
- `MUMBLE_BANDWIDTH` is Mumble-only (no-op on TS).
- Music (`!yplay` via botamusique) is Mumble-only; on TS6 the bot replies
  `🎵 Music via botamusique is not supported on TeamSpeak yet.` and sends
  nothing to TS chat.

## Run

The Python `BridgeSupervisor` spawns this automatically (`node index.js`).
Manual run for debugging:

```bash
node index.js
```

Kill the bridge to verify degradation: `?status` must show
`VoiceBridge: Down` while text commands keep working.
