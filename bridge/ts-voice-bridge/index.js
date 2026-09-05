/**
 * ts-voice-bridge — TeamSpeak 6 voice sidecar for Mumble-Butler.
 *
 * Python keeps ALL AI logic. This process is only the TS voice client:
 * it pipes PCM <-> Opus over localhost UDP so the Python side sees the
 * identical 48 kHz mono s16le contract as Mumble.
 *
 * Directions:
 *   RX: TS on("voice") Opus -> decode -> 48k s16le PCM -> UDP 127.0.0.1:5001
 *       datagram = [TOKEN + "|" if set] + [name_len:1][name utf8][pcm]
 *   TX: UDP 127.0.0.1:5002 datagrams (raw PCM, optionally TOKEN-prefixed)
 *       -> Opus encode (codec 4/5 per server) -> sendVoice()
 *
 * Env (mirrors config.py TS6_*):
 *   TS6_VOICE_HOST (default 127.0.0.1), TS6_VOICE_PORT (9987),
 *   TS6_NICKNAME, TS6_SERVER_PASSWORD, TS6_CHANNEL, TS6_CHANNEL_PASSWORD,
 *   TS6_IDENTITY (empty = generate + print for reuse),
 *   TS6_BRIDGE_RX_PORT (5001), TS6_BRIDGE_TX_PORT (5002), TS6_BRIDGE_TOKEN
 *
 * Requires: npm install (teamspeak-js + @discordjs/opus, opusscript fallback).
 */
'use strict';

const dgram = require('dgram');

const HOST = process.env.TS6_VOICE_HOST || '127.0.0.1';
const PORT = parseInt(process.env.TS6_VOICE_PORT || '9987', 10);
const NICK = process.env.TS6_NICKNAME || process.env.MUMBLE_BOT_USERNAME || 'Obama';
const SERVER_PASSWORD = process.env.TS6_SERVER_PASSWORD || '';
const CHANNEL = process.env.TS6_CHANNEL || process.env.MUMBLE_TARGET_CHANNEL || 'General';
const CHANNEL_PASSWORD = process.env.TS6_CHANNEL_PASSWORD || '';
let IDENTITY = process.env.TS6_IDENTITY || '';
const RX_PORT = parseInt(process.env.TS6_BRIDGE_RX_PORT || '5001', 10);
const TX_PORT = parseInt(process.env.TS6_BRIDGE_TX_PORT || '5002', 10);
const TOKEN = process.env.TS6_BRIDGE_TOKEN || '';

function log(...args) {
  console.log(new Date().toISOString(), '[bridge]', ...args);
}
function warn(...args) {
  console.warn(new Date().toISOString(), '[bridge]', ...args);
}

// --- Opus (native preferred, JS fallback) -----------------------------------
let OpusEncoder = null;
let opusKind = 'none';
try {
  // eslint-disable-next-line global-require
  const { OpusEncoder: DiscordOpus } = require('@discordjs/opus');
  OpusEncoder = DiscordOpus;
  opusKind = '@discordjs/opus';
} catch (e) {
  try {
    // eslint-disable-next-line global-require
    const OpusScript = require('opusscript');
    OpusEncoder = OpusScript;
    opusKind = 'opusscript';
  } catch (e2) {
    warn('No Opus library found. Run `npm install`. Voice will not work.');
  }
}

const SAMPLE_RATE = 48000;
const CHANNELS = 1;
// 20 ms frames: 960 samples * 2 bytes = 1920 bytes PCM per frame.
const FRAME_SAMPLES = 960;
const FRAME_BYTES = FRAME_SAMPLES * 2;

let encoder = null;
let decoder = null;
if (OpusEncoder) {
  try {
    // @discordjs/opus: new OpusEncoder(rate, channels)
    // opusscript: new OpusEncoder(rate, channels, app) — try both.
    try {
      encoder = new OpusEncoder(SAMPLE_RATE, CHANNELS);
      decoder = new OpusEncoder(SAMPLE_RATE, CHANNELS);
    } catch (e) {
      encoder = new OpusEncoder(SAMPLE_RATE, CHANNELS, 2048);
      decoder = new OpusEncoder(SAMPLE_RATE, CHANNELS, 2048);
    }
    log(`Opus ready via ${opusKind}.`);
  } catch (e) {
    warn('Opus init failed:', e.message);
  }
}

function decodeOpus(packet) {
  if (!decoder) return null;
  try {
    if (opusKind === '@discordjs/opus') return decoder.decode(packet);
    return decoder.decode(packet, FRAME_SAMPLES);
  } catch (e) {
    return null;
  }
}

function encodePcm(frame) {
  if (!encoder) return null;
  try {
    if (opusKind === '@discordjs/opus') return encoder.encode(frame);
    return encoder.encode(frame, FRAME_SAMPLES);
  } catch (e) {
    return null;
  }
}

// --- UDP framing (must match backends/teamspeak_backend.py) -----------------
function frameRx(username, pcm) {
  const nameBuf = Buffer.from(username || 'unknown', 'utf8').slice(0, 255);
  const header = Buffer.alloc(1);
  header.writeUInt8(nameBuf.length, 0);
  const payload = Buffer.concat([header, nameBuf, Buffer.from(pcm)]);
  if (TOKEN) return Buffer.concat([Buffer.from(`${TOKEN}|`, 'utf8'), payload]);
  return payload;
}

function parseTx(msg) {
  let data = msg;
  if (TOKEN) {
    const prefix = Buffer.from(`${TOKEN}|`, 'utf8');
    if (!data.slice(0, prefix.length).equals(prefix)) return null;
    data = data.slice(prefix.length);
  }
  if (!data || data.length === 0 || data.length % 2 !== 0) return null;
  return data;
}

// --- Sockets -----------------------------------------------------------------
const rxSocket = dgram.createSocket('udp4'); // we only SEND on this (to Python :5001)
const txSocket = dgram.createSocket('udp4'); // we RECEIVE on this (from Python :5002)

let txBuffer = Buffer.alloc(0);

txSocket.on('message', async (msg) => {
  const pcm = parseTx(msg);
  if (!pcm) return;
  txBuffer = Buffer.concat([txBuffer, pcm]);
  // Emit full 20 ms frames in order.
  while (txBuffer.length >= FRAME_BYTES) {
    const frame = txBuffer.slice(0, FRAME_BYTES);
    txBuffer = txBuffer.slice(FRAME_BYTES);
    const opus = encodePcm(frame);
    if (opus && client) {
      try {
        // Codec 4 (music) vs 5 (voice) is negotiated per server; prefer voice.
        if (typeof client.sendVoice === 'function') {
          await client.sendVoice(opus, currentCodec());
        }
      } catch (e) {
        warn('sendVoice failed:', e.message);
      }
    }
  }
});

txSocket.on('error', (err) => warn('TX socket error:', err.message));

// --- TeamSpeak client -----------------------------------------------------------
let TeamSpeakClient = null;
try {
  // eslint-disable-next-line global-require, import/no-unresolved
  const tsjs = require('teamspeak-js');
  TeamSpeakClient = tsjs.TeamSpeak || tsjs.Client || tsjs.default || tsjs;
} catch (e) {
  warn('teamspeak-js not installed. Run `npm install` in bridge/ts-voice-bridge.');
}

let client = null;
let negotiatedCodec = 5; // Opus Voice; falls back to 4 (Opus Music) when needed.
function currentCodec() {
  return negotiatedCodec;
}

async function connectVoice() {
  if (!TeamSpeakClient) {
    warn('Cannot connect: teamspeak-js missing. Retrying in 10s (text-only mode continues).');
    setTimeout(connectVoice, 10000);
    return;
  }
  if (!IDENTITY) {
    log('TS6_IDENTITY empty — generating ephemeral identity. Set TS6_IDENTITY to reuse it.');
  }
  const opts = {
    host: HOST,
    port: PORT,
    nickname: NICK,
    identity: IDENTITY || undefined,
    serverPassword: SERVER_PASSWORD || undefined,
    defaultChannel: CHANNEL || undefined,
    defaultChannelPassword: CHANNEL_PASSWORD || undefined,
  };
  log(`Connecting voice as ${NICK} to ${HOST}:${PORT} channel=${CHANNEL || '(default)'} ...`);
  try {
    client = new TeamSpeakClient(opts);
    if (typeof client.connect === 'function') await client.connect();
    else if (typeof client.start === 'function') await client.start();

    // Persist generated identity for reuse (avoids security-level blocks).
    try {
      const id = client.identity || client.getIdentity?.();
      if (id && !IDENTITY) {
        IDENTITY = typeof id === 'string' ? id : JSON.stringify(id);
        log('Generated TS identity (save as TS6_IDENTITY to reuse):', IDENTITY.slice(0, 32) + '...');
      }
    } catch (e) { /* non-fatal */ }

    // Negotiate Opus codec: prefer voice (5), accept music (4).
    try {
      const codec = client.codec ?? client.voiceCodec ?? 5;
      if (codec === 4 || codec === 5) negotiatedCodec = codec;
      log(`Voice codec: Opus ${negotiatedCodec === 4 ? 'Music (4)' : 'Voice (5)'}.`);
    } catch (e) { /* keep default */ }

    // Join target channel when the API exposes moves.
    try {
      if (CHANNEL && typeof client.moveToChannel === 'function') await client.moveToChannel(CHANNEL);
      else if (CHANNEL && typeof client.clientMove === 'function') await client.clientMove({ channel: CHANNEL });
    } catch (e) {
      warn('Channel move failed (will retry on reconnect):', e.message);
    }

    client.on?.('voice', (event) => {
      try {
        // teamspeak-js voice event shapes vary: {client, opus, codec} or raw buffer.
        const opus = event?.opus ?? event?.data ?? event?.packet ?? event;
        const name = event?.client?.nickname ?? event?.invokername ?? event?.nickname ?? 'unknown';
        if (!Buffer.isBuffer(opus)) return;
        const pcm = decodeOpus(opus);
        if (!pcm) return;
        const datagram = frameRx(String(name), pcm);
        rxSocket.send(datagram, RX_PORT, '127.0.0.1', (err) => {
          if (err) warn('RX send failed:', err.message);
        });
      } catch (e) {
        warn('voice handler error:', e.message);
      }
    });

    client.on?.('close', () => {
      warn('Voice connection closed. Reconnecting in 5s...');
      client = null;
      setTimeout(connectVoice, 5000);
    });
    client.on?.('error', (err) => warn('Voice client error:', err?.message ?? err));

    log('Voice connected.');
  } catch (e) {
    warn('Voice connect failed:', e.message, '— retrying in 5s.');
    client = null;
    setTimeout(connectVoice, 5000);
  }
}

txSocket.bind(TX_PORT, '127.0.0.1', () => {
  log(`TX listening on 127.0.0.1:${TX_PORT} (PCM from Python). RX target 127.0.0.1:${RX_PORT}.`);
  connectVoice();
});

process.on('SIGINT', () => process.exit(0));
process.on('SIGTERM', () => process.exit(0));
