/**
 * ts-voice-bridge — TeamSpeak 6 voice sidecar for Mumble-Butler.
 *
 * Python keeps ALL AI logic. This process is only the TS voice client:
 * it pipes PCM <-> Opus over localhost UDP so the Python side sees the
 * identical 48 kHz mono s16le contract as Mumble.
 *
 * Directions:
 *   RX: TS voiceData Opus -> decode -> 48k s16le PCM -> UDP 127.0.0.1:5001
 *       datagram = [TOKEN + "|" if set] + [name_len:1][name utf8][pcm]
 *   TX: UDP 127.0.0.1:5002 datagrams (raw PCM, optionally TOKEN-prefixed)
 *       -> Opus encode (codec 4/5 per server) -> sendVoice(data, codec)
 *
 * Env (mirrors config.py TS6_*):
 *   TS6_VOICE_HOST (default 127.0.0.1), TS6_VOICE_PORT (9987),
 *   TS6_NICKNAME, TS6_SERVER_PASSWORD, TS6_CHANNEL, TS6_CHANNEL_PASSWORD,
 *   TS6_IDENTITY (empty = generate + print for reuse),
 *   TS6_BRIDGE_RX_PORT (5001), TS6_BRIDGE_TX_PORT (5002), TS6_BRIDGE_TOKEN
 *
 * Requires: npm install (@honeybbq/teamspeak-client + @discordjs/opus,
 * opusscript fallback). Needs Node.js >= 20.19.
 */
'use strict';

const dgram = require('dgram');

const HOST = process.env.TS6_VOICE_HOST || '127.0.0.1';
const PORT = parseInt(process.env.TS6_VOICE_PORT || '9987', 10);
const NICK = process.env.TS6_NICKNAME || process.env.MUMBLE_BOT_USERNAME || 'Obama';
const SERVER_PASSWORD = process.env.TS6_SERVER_PASSWORD || '';
const CHANNEL = process.env.TS6_CHANNEL || process.env.MUMBLE_TARGET_CHANNEL || 'General';
const CHANNEL_PASSWORD = process.env.TS6_CHANNEL_PASSWORD || '';
const IDENTITY_STR = process.env.TS6_IDENTITY || '';
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
let client = null;
let negotiatedCodec = 5; // Opus Voice; falls back to 4 (Opus Music) when needed.
function currentCodec() {
  return negotiatedCodec;
}

// clid -> nickname for RX framing (voiceData only carries clientId).
const nickByClid = new Map();
function nameForClid(clid) {
  const nick = nickByClid.get(clid);
  if (nick) return String(nick);
  return `clid_${clid}`;
}

txSocket.on('message', (msg) => {
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
        // NOTE: sendVoice(data, codec) is sync in @honeybbq/teamspeak-client.
        client.sendVoice(opus, currentCodec());
      } catch (e) {
        warn('sendVoice failed:', e.message);
      }
    }
  }
});

txSocket.on('error', (err) => warn('TX socket error:', err.message));

// --- TeamSpeak client (@honeybbq/teamspeak-client) ---------------------------
// Correct npm package for HoneyBBQ/teamspeak-js is the scoped
// `@honeybbq/teamspeak-client` (bare `teamspeak-js` does NOT exist on npm
// and installs fail with E404). API: new Client(identity, addr, nick, opts),
// client.connect() + waitConnected(), client.on("voiceData", ...),
// client.sendVoice(data, codec), generateIdentity(level) /
// identityFromString(str) / identity.toString().
let TSClient = null;
let generateIdentity = null;
let identityFromString = null;
try {
  // eslint-disable-next-line global-require, import/no-unresolved
  const tsmod = require('@honeybbq/teamspeak-client');
  TSClient = tsmod.Client || tsmod.default || tsmod;
  generateIdentity = tsmod.generateIdentity;
  identityFromString = tsmod.identityFromString;
} catch (e) {
  warn('@honeybbq/teamspeak-client not installed. Run `npm install` in bridge/ts-voice-bridge.');
}

function loadIdentity() {
  if (IDENTITY_STR && identityFromString) {
    try {
      const id = identityFromString(IDENTITY_STR.trim());
      log('Loaded TS identity from TS6_IDENTITY.');
      return id;
    } catch (e) {
      warn('TS6_IDENTITY invalid, generating ephemeral identity:', e.message);
    }
  }
  if (!generateIdentity) {
    throw new Error('@honeybbq/teamspeak-client missing (no generateIdentity). Run `npm install`.');
  }
  log('TS6_IDENTITY empty — generating new identity (level 8). Save the printed value as TS6_IDENTITY to reuse it.');
  const id = generateIdentity(8);
  try {
    const exported = typeof id.toString === 'function' ? id.toString() : String(id);
    log('Generated TS identity (save as TS6_IDENTITY to reuse):', exported.slice(0, 32) + '...');
  } catch (e) { /* non-fatal */ }
  return id;
}

async function connectVoice() {
  if (!TSClient) {
    warn('Cannot connect: @honeybbq/teamspeak-client missing. Retrying in 10s (text-only mode continues).');
    setTimeout(connectVoice, 10000);
    return;
  }
  const addr = `${HOST}:${PORT}`;
  log(`Connecting voice as ${NICK} to ${addr} channel=${CHANNEL || '(default)'} ...`);
  try {
    const identity = loadIdentity();
    client = new TSClient(identity, addr, NICK, {
      serverPassword: SERVER_PASSWORD || undefined,
      defaultChannel: CHANNEL || undefined,
      defaultChannelPassword: CHANNEL_PASSWORD || undefined,
    });

    client.on('connected', () => {
      try {
        log(`Voice connected (clid=${client.clientID?.() ?? '?'}).`);
      } catch (e) {
        log('Voice connected.');
      }
    });

    // Keep clid -> nickname map for RX framing.
    client.on('clientEnter', (info) => {
      try {
        if (info && typeof info.id === 'number' && info.nickname) {
          nickByClid.set(info.id, info.nickname);
        }
      } catch (e) { /* non-fatal */ }
    });
    client.on('clientLeave', (evt) => {
      try {
        if (evt && typeof evt.id === 'number') nickByClid.delete(evt.id);
      } catch (e) { /* non-fatal */ }
    });
    client.on('clientMoved', () => { /* channel tracking not needed for voice */ });

    // Incoming voice: { clientId, codec, data } — decode Opus -> PCM -> Python.
    client.on('voiceData', (event) => {
      try {
        const opus = event?.data;
        const clid = event?.clientId;
        if (!Buffer.isBuffer(opus) && !(opus instanceof Uint8Array)) return;
        if (typeof event?.codec === 'number' && (event.codec === 4 || event.codec === 5)) {
          negotiatedCodec = event.codec;
        }
        const pcm = decodeOpus(Buffer.from(opus));
        if (!pcm) return;
        const datagram = frameRx(nameForClid(clid), pcm);
        rxSocket.send(datagram, RX_PORT, '127.0.0.1', (err) => {
          if (err) warn('RX send failed:', err.message);
        });
      } catch (e) {
        warn('voiceData handler error:', e.message);
      }
    });

    client.on('disconnected', (err) => {
      warn('Voice connection closed:', err?.message ?? 'clean', 'Reconnecting in 5s...');
      client = null;
      setTimeout(connectVoice, 5000);
    });

    await client.connect();
    // Wait until handshake completes (15 s timeout).
    if (typeof client.waitConnected === 'function') {
      await client.waitConnected(AbortSignal.timeout(15_000));
    }

    // Seed nickname map so RX frames carry real names from the start.
    try {
      const { listClients } = require('@honeybbq/teamspeak-client');
      if (typeof listClients === 'function') {
        const clients = await listClients(client);
        for (const c of clients || []) {
          if (c && typeof c.id === 'number' && c.nickname) nickByClid.set(c.id, c.nickname);
        }
      }
    } catch (e) { /* optional; nicknames fall back to clid_N */ }

    log(`Voice codec: Opus ${negotiatedCodec === 4 ? 'Music (4)' : 'Voice (5)'}.`);
    log('Voice connected.');
  } catch (e) {
    warn('Voice connect failed:', e.message, '— retrying in 5s.');
    try {
      if (client && typeof client.disconnect === 'function') await client.disconnect();
    } catch (e2) { /* ignore */ }
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
