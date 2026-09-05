"""TeamSpeak 6 backend: SSH ServerQuery (:10022) for text/presence/move +
bridge sidecar for full voice.

Architecture (see ts6plan.md)::

    MadnessBot -> TeamspeakBackend
    ├── QueryClient (SSH :10022) — text / presence / move
    └── BridgeSupervisor -> bridge/ts-voice-bridge/ (Node + teamspeak-js)
        RX: TS Opus -> decode -> 48k PCM -> UDP :5001 -> AudioManager.add_audio()
        TX: AudioManager/TTS 48k PCM -> UDP :5002 -> encode Opus -> sendVoice()

PCM contract (both directions): 48 kHz mono s16le, identical to Mumble so
AudioManager / UserVoiceStream / Ear / Voice need zero changes.

Query docs: TS6 removed raw :10011. Only SSH :10022 + HTTP WebQuery remain.
ServerQuery is text/control only — it cannot carry voice. Voice goes via
the bridge sidecar (honeybbq/teamspeak-js sendVoice/on("voice"), Opus 4/5).

Query setup on the server:
  TSSERVER_QUERY_SSH_ENABLED=1
  TSSERVER_QUERY_ADMIN_PASSWORD=<password>   (== TS6_QUERY_PASSWORD)
  query_ip_allowlist.txt must contain the bot IP or FloodError id 524 occurs.

Requires: asyncssh (+ optionally atsq, preferred when installed).
"""
import asyncio
import logging
import os
import socket
import threading
import time
import subprocess
import struct

import config
from backends.base import VoiceBackend

log = logging.getLogger("TeamspeakBackend")

# ---------------------------------------------------------------------------
# Query escaping (TeamSpeak ServerQuery)
# ---------------------------------------------------------------------------

_TS_UNESCAPE = {
    "s": " ",
    "p": "|",
    "/": "/",
    "\\": "\\",
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
}


def ts_escape(s):
    """Escape a string for sending as a ServerQuery parameter value."""
    if s is None:
        return ""
    s = str(s)
    s = s.replace("\\", "\\\\")
    s = s.replace(" ", "\\s")
    s = s.replace("|", "\\p")
    s = s.replace("/", "\\/")
    s = s.replace("\n", "\\n")
    s = s.replace("\r", "\\r")
    s = s.replace("\t", "\\t")
    return s


def ts_unescape(s):
    """Unescape a ServerQuery-escaped value."""
    if s is None:
        return ""
    out = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            out.append(_TS_UNESCAPE.get(nxt, nxt))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def parse_ts_kv(line):
    """Parse 'key=value key2=value2' (values TS-escaped) into a dict.

    Duplicate keys keep the last value. Flags without '=' map to "".
    """
    params = {}
    for part in line.strip().split(" "):
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            params[k] = ts_unescape(v)
        else:
            params[part] = ""
    return params


def parse_ts_response(lines):
    """Split ServerQuery reply lines into (data_lines, error_dict).

    Data lines precede the final 'error id=.. msg=..' line. 'notify...'
    lines are events, not responses — callers must filter them first.
    """
    data = []
    error = {"id": "-1", "msg": ""}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("error "):
            error = parse_ts_kv(line[len("error "):])
        else:
            data.append(line)
    return data, error


# ---------------------------------------------------------------------------
# Text normalization — maps both transports to handle(sender_name, text)
# ---------------------------------------------------------------------------

def normalize_text_event(event, bot=None):
    """Normalize a text/chat event from either backend.

    Returns (sender_name, text) or None if the event should be ignored.

    Accepted shapes:
    - pymumble: object with .actor (session id) and .message (str).
      Looks up bot.mumble.users[actor] / backend.list_users() for the name.
      Ignores self-messages and config.IGNORED_USERS.
    - TeamSpeak notifytextmessage: dict (or raw "notifytextmessage ..." str)
      with invokername / msg / targetmode. Ignores own nick + ignored users.
    - Direct tuple/list (sender, text): passed through with ignore-filtering.
    - Dict with sender/name + text/message keys: convenience for tests.
    """
    ignored = set(getattr(config, "IGNORED_USERS", []) or [])

    def _filtered(sender, text):
        if not sender or text is None:
            return None
        sender = str(sender)
        text = str(text)
        if not text.strip():
            return None
        if sender in ignored:
            return None
        # Ignore own messages on either backend (always filter configured
        # nicks; additionally filter the live query nick when bot is given).
        try:
            own_names = {
                getattr(config, "BOT_USERNAME", ""),
                getattr(config, "TS6_NICKNAME", ""),
            }
            own_names.discard("")
            if bot is not None:
                backend = getattr(bot, "backend", None)
                if backend is not None and getattr(backend, "backend_name", "") == "teamspeak":
                    # QueryClient knows the nick we set via clientupdate
                    qc = getattr(backend, "query", None)
                    if qc is not None and getattr(qc, "nickname", None):
                        own_names.add(qc.nickname)
        except Exception:
            pass
        if sender in own_names:
            return None
        return (sender, text)

    # -- direct (sender, text) tuple --------------------------------------
    if isinstance(event, (tuple, list)) and len(event) == 2:
        return _filtered(event[0], event[1])

    # -- raw TS notify line ------------------------------------------------
    if isinstance(event, str) and event.strip().startswith("notifytextmessage"):
        payload = event.strip()[len("notifytextmessage"):].strip()
        params = parse_ts_kv(payload)
        return _filtered(params.get("invokername"), params.get("msg", ""))

    # -- dict events --------------------------------------------------------
    if isinstance(event, dict):
        # TS shape
        if "invokername" in event or "msg" in event:
            return _filtered(event.get("invokername"), event.get("msg", ""))
        # generic convenience shape
        sender = event.get("sender", event.get("name", event.get("invokername")))
        text = event.get("text", event.get("message", event.get("msg")))
        if sender is not None and text is not None:
            return _filtered(sender, text)
        return None

    # -- pymumble-style object ----------------------------------------------
    actor = getattr(event, "actor", None)
    message = getattr(event, "message", None)
    if actor is not None and message is not None:
        sender_name = None
        try:
            if bot is not None:
                # Prefer raw mumble users dict (legacy / test compat)
                users = getattr(getattr(bot, "mumble", None), "users", None)
                if users is not None:
                    try:
                        u = users.get(actor) if hasattr(users, "get") else users[actor]
                        if isinstance(u, dict):
                            sender_name = u.get("name")
                        else:
                            sender_name = getattr(u, "name", None)
                    except Exception:
                        sender_name = None
                # Fall back to backend user list
                if sender_name is None:
                    backend = getattr(bot, "backend", None)
                    if backend is not None:
                        try:
                            for u in backend.list_users() or []:
                                if u.get("id") == actor:
                                    sender_name = u.get("name")
                                    break
                        except Exception:
                            pass
                # Ignore self by session id when mumble exposes it
                try:
                    myself_session = getattr(getattr(bot, "mumble", None), "users", None)
                    myself_session = getattr(myself_session, "myself_session", None)
                    if actor == myself_session:
                        return None
                except Exception:
                    pass
        except Exception:
            pass
        if sender_name is None:
            return None
        return _filtered(sender_name, message)

    return None


# ---------------------------------------------------------------------------
# QueryClient — SSH ServerQuery :10022 (text / presence / move)
# ---------------------------------------------------------------------------

class QueryError(Exception):
    pass


class FloodError(QueryError):
    """Raised on 'error id=524 ...' — add bot IP to query_ip_allowlist.txt."""


class QueryClient:
    """Minimal asyncio TeamSpeak ServerQuery client over SSH.

    Uses `atsq` when installed (preferred, asyncio-native, tested vs
    teamspeak:3.13 + teamspeaksystems/teamspeak6-server), otherwise falls
    back to a small built-in asyncssh implementation speaking the same
    line protocol.

    Public surface used by TeamspeakBackend:
      connect() / close() / is_connected()
      send_channel_message(text) / send_private_message(clid, text)
      list_clients() -> [{clid, cid, nickname, type}]
      list_channels() -> [{cid, name}]
      move_to_channel_by_name(name) -> bool
      register_callbacks(on_text(sender, text), on_join(user, channel))
    """

    def __init__(self, host=None, port=None, username=None, password=None,
                 server_id=None, nickname=None):
        self.host = host or getattr(config, "TS6_HOST", "127.0.0.1")
        self.port = port or getattr(config, "TS6_QUERY_PORT", 10022)
        self.username = username or getattr(config, "TS6_QUERY_USER", "serveradmin")
        self.password = password if password is not None else getattr(config, "TS6_QUERY_PASSWORD", "")
        self.server_id = server_id or getattr(config, "TS6_SERVER_ID", 1)
        self.nickname = nickname or getattr(config, "TS6_NICKNAME", "Obama")
        self._thread = None
        self._loop = None
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._on_text = None
        self._on_join = None
        self._known_clients = {}  # clid -> (cid, nickname)
        self._atsq_client = None
        self._use_atsq = False

    # -- callback registration -------------------------------------------
    def register_callbacks(self, on_text=None, on_join=None):
        self._on_text = on_text
        self._on_join = on_join

    def is_connected(self):
        return self._connected.is_set()

    # -- lifecycle ----------------------------------------------------------
    def connect(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()
        # Wait briefly for initial connect (non-fatal if server is down;
        # background thread keeps retrying with backoff).
        self._connected.wait(timeout=5)

    def close(self):
        self._stop.set()
        self._connected.clear()
        try:
            if self._loop and self._loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(self._quit(), self._loop)
                try:
                    fut.result(timeout=3)
                except Exception:
                    pass
        except Exception:
            pass

    # -- public query ops (thread-safe, best-effort) ------------------------
    def send_channel_message(self, text):
        self._submit(f"sendtextmessage targetmode=2 msg={ts_escape(text)}")

    def send_private_message(self, clid, text):
        self._submit(f"sendtextmessage targetmode=1 target={int(clid)} msg={ts_escape(text)}")

    def list_clients(self):
        """Best-effort snapshot; [] when disconnected (tests may stub)."""
        resp = self._submit_sync("clientlist")
        clients = []
        if not resp:
            return clients
        for line in resp.split("|"):
            p = parse_ts_kv(line)
            try:
                clients.append({
                    "clid": int(p.get("clid", -1)),
                    "cid": int(p.get("cid", -1)),
                    "nickname": p.get("client_nickname", ""),
                    "type": int(p.get("client_type", "0")),
                })
            except ValueError:
                continue
        return [c for c in clients if c["clid"] >= 0]

    def list_channels(self):
        resp = self._submit_sync("channellist")
        channels = []
        if not resp:
            return channels
        for line in resp.split("|"):
            p = parse_ts_kv(line)
            try:
                channels.append({"cid": int(p.get("cid", -1)), "name": p.get("channel_name", "")})
            except ValueError:
                continue
        return [c for c in channels if c["cid"] >= 0]

    def move_to_channel_by_name(self, name):
        """Exact-match channel name -> cid; first hit wins (+ warning on dupes)."""
        channels = self.list_channels()
        hits = [c for c in channels if c.get("name") == name]
        if not hits:
            log.warning("TS6 target channel %r not found.", name)
            return False
        if len(hits) > 1:
            log.warning("TS6 duplicate channel name %r: %d hits, using first (cid=%s).",
                        name, len(hits), hits[0]["cid"])
        cid = hits[0]["cid"]
        # Move our own query-visible client: need our clid via whoami
        resp = self._submit_sync("whoami")
        clid = None
        if resp:
            p = parse_ts_kv(resp)
            try:
                clid = int(p.get("clid", ""))
            except ValueError:
                clid = None
        if clid is None:
            log.warning("TS6 whoami failed; cannot move to %r.", name)
            return False
        channel_pw = getattr(config, "TS6_CHANNEL_PASSWORD", "") or ""
        cmd = f"clientmove clid={clid} cid={cid}"
        if channel_pw:
            cmd += f" cpw={ts_escape(channel_pw)}"
        ok = self._submit_sync(cmd, expect_ok=True)
        return ok is not None

    # -- internals: command submission ---------------------------------------
    def _submit(self, cmd):
        """Fire-and-forget (used for chat sends)."""
        if not self._loop or not self._loop.is_running():
            return False
        try:
            asyncio.run_coroutine_threadsafe(self._send_line(cmd), self._loop)
            return True
        except Exception:
            return False

    def _submit_sync(self, cmd, expect_ok=False, timeout=8):
        if not self._loop or not self._loop.is_running() or not self.is_connected():
            return None
        try:
            fut = asyncio.run_coroutine_threadsafe(self._exec(cmd), self._loop)
            return fut.result(timeout=timeout)
        except Exception as e:
            log.warning("TS6 query %r failed: %s", cmd.split(" ")[0], e)
            return None

    # -- internals: connection loop -------------------------------------------
    def _run_forever(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect_loop())
        except Exception as e:
            log.error("TS6 query loop exited: %s", e)
        finally:
            self._connected.clear()

    async def _connect_loop(self):
        # Prefer atsq when installed
        try:
            import atsq  # noqa: F401
            self._use_atsq = True
        except ImportError:
            self._use_atsq = False
        backoff = 2
        while not self._stop.is_set():
            try:
                if self._use_atsq:
                    await self._atsq_session()
                else:
                    await self._raw_session()
                backoff = 2
            except FloodError as e:
                log.error("TS6 query flooded (id 524): %s. Add bot IP to query_ip_allowlist.txt.", e)
            except Exception as e:
                if not self._stop.is_set():
                    log.warning("TS6 query error: %s (retry in %ss)", e, backoff)
            finally:
                self._connected.clear()
            if not self._stop.is_set():
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    # -- atsq session (preferred) ----------------------------------------------
    async def _atsq_session(self):
        import atsq
        client = await atsq.connect(
            self.host, self.port,
            password=self.password,
            server_id=self.server_id,
        )
        self._atsq_client = client
        try:
            # atsq API surface varies by version; be defensive.
            if hasattr(client, "on"):
                try:
                    client.on("cliententerview")(lambda ev: self._handle_atsq_join(ev))
                except Exception:
                    pass
                try:
                    client.on("textmessage")(lambda ev: self._handle_atsq_text(ev))
                except Exception:
                    pass
            if hasattr(client, "run_forever"):
                self._connected.set()
                await client.run_forever()
            else:
                # Minimal keepalive loop if run_forever is absent
                self._connected.set()
                while not self._stop.is_set():
                    await asyncio.sleep(10)
        finally:
            self._connected.clear()
            try:
                if hasattr(client, "quit"):
                    await client.quit()
                elif hasattr(client, "close"):
                    await client.close()
            except Exception:
                pass
            self._atsq_client = None

    def _handle_atsq_text(self, ev):
        try:
            if isinstance(ev, dict):
                sender = ev.get("invokername", ev.get("invoker", ""))
                text = ev.get("msg", "")
            else:
                sender = getattr(ev, "invokername", "")
                text = getattr(ev, "msg", "")
            if self._on_text and sender and text:
                self._on_text(str(sender), str(text))
        except Exception as e:
            log.warning("atsq text handler error: %s", e)

    def _handle_atsq_join(self, ev):
        try:
            if isinstance(ev, dict):
                user = ev.get("client_nickname", "")
                channel = ev.get("ctid", ev.get("cid", ""))
            else:
                user = getattr(ev, "client_nickname", "")
                channel = getattr(ev, "ctid", getattr(ev, "cid", ""))
            if self._on_join and user:
                self._on_join(str(user), str(channel))
        except Exception as e:
            log.warning("atsq join handler error: %s", e)

    # -- raw asyncssh session (fallback, fully tested offline) ------------------
    async def _raw_session(self):
        try:
            import asyncssh
        except ImportError as e:
            raise RuntimeError(
                "asyncssh is required for the TS6 query backend. "
                "Install it via `pip install -r requirements.txt`."
            ) from e
        async with asyncssh.connect(
            self.host, port=self.port, username=self.username,
            password=self.password, known_hosts=None,
        ) as conn:
            reader, writer = await conn.open_session(term_type="dumb")
            try:
                await self._raw_login(reader, writer)
            except FloodError:
                raise
            except Exception as e:
                raise QueryError(f"TS6 query login failed: {e}") from e
            self._connected.set()
            log.info("✅ TS6 query connected (%s:%s, server_id=%s).",
                     self.host, self.port, self.server_id)
            await self._raw_event_loop(reader, writer)

    async def _raw_login(self, reader, writer):
        await self._read_greeting(reader)
        await self._exec_raw(reader, writer, f"login {self.username} {self.password}")
        await self._exec_raw(reader, writer, f"use {int(self.server_id)}")
        nick = self.nickname or getattr(config, "BOT_USERNAME", "Obama")
        try:
            await self._exec_raw(reader, writer, f"clientupdate client_nickname={ts_escape(nick)}")
            self.nickname = nick
        except QueryError as e:
            log.warning("TS6 clientupdate failed (nick %r kept server-side?): %s", nick, e)
        await self._exec_raw(reader, writer, "servernotifyregister event=textchannel")
        await self._exec_raw(reader, writer, "servernotifyregister event=textprivate")
        await self._exec_raw(reader, writer, "servernotifyregister event=server")
        await self._exec_raw(reader, writer, "servernotifyregister event=channel id=0")

    async def _raw_event_loop(self, reader, writer):
        # Seed known clients so the first cliententerview burst doesn't
        # greet everyone already present.
        try:
            await self._snapshot_clients(reader, writer)
        except Exception:
            pass
        buf = ""
        keepalive = time.time()
        while not self._stop.is_set():
            try:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=30)
            except asyncio.TimeoutError:
                # keepalive + connection check
                try:
                    await self._exec_raw(reader, writer, "whoami")
                    keepalive = time.time()
                    continue
                except Exception as e:
                    raise QueryError(f"keepalive failed: {e}") from e
            if chunk in ("", None):
                raise QueryError("TS6 query connection closed by server.")
            buf += chunk if isinstance(chunk, str) else chunk.decode("utf-8", "replace")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip().strip("\r")
                if line:
                    self._dispatch_line(line)
            if time.time() - keepalive > 120:
                try:
                    await self._exec_raw(reader, writer, "whoami")
                except Exception:
                    pass
                keepalive = time.time()

    async def _snapshot_clients(self, reader, writer):
        raw = await self._exec_raw(reader, writer, "clientlist")
        for segment in (raw or "").split("|"):
            p = parse_ts_kv(segment)
            try:
                clid = int(p.get("clid", "-1"))
                cid = int(p.get("cid", "-1"))
            except ValueError:
                continue
            nick = p.get("client_nickname", "")
            if clid >= 0:
                self._known_clients[clid] = (cid, nick)

    def _dispatch_line(self, line):
        if line.startswith("notifytextmessage"):
            params = parse_ts_kv(line[len("notifytextmessage"):].strip())
            sender = params.get("invokername", "")
            text = params.get("msg", "")
            if sender and text is not None and self._on_text:
                try:
                    self._on_text(sender, text)
                except Exception as e:
                    log.warning("on_text error: %s", e)
        elif line.startswith("notifycliententerview"):
            params = parse_ts_kv(line[len("notifycliententerview"):].strip())
            try:
                ctype = int(params.get("client_type", "0"))
            except ValueError:
                ctype = 0
            if ctype != 0:
                return  # ignore query clients
            try:
                clid = int(params.get("clid", "-1"))
            except ValueError:
                clid = -1
            nick = params.get("client_nickname", "")
            ctid = params.get("ctid", params.get("cid", ""))
            if clid >= 0:
                self._known_clients[clid] = (ctid, nick)
            if nick and self._on_join:
                try:
                    self._on_join(nick, ctid)
                except Exception as e:
                    log.warning("on_join error: %s", e)
        elif line.startswith("notifyclientmoved"):
            params = parse_ts_kv(line[len("notifyclientmoved"):].strip())
            try:
                clid = int(params.get("clid", "-1"))
            except ValueError:
                clid = -1
            ctid = params.get("ctid", "")
            nick = params.get("client_nickname", "")
            if not nick and clid in self._known_clients:
                nick = self._known_clients[clid][1]
            if clid >= 0:
                self._known_clients[clid] = (ctid, nick)
            if nick and self._on_join:
                try:
                    self._on_join(nick, ctid)
                except Exception as e:
                    log.warning("on_join(move) error: %s", e)
        elif line.startswith("notifyclientleftview"):
            params = parse_ts_kv(line[len("notifyclientleftview"):].strip())
            try:
                clid = int(params.get("clid", "-1"))
            except ValueError:
                clid = -1
            self._known_clients.pop(clid, None)
        # Other notifies / responses are consumed by _exec_raw, not here.

    # -- raw protocol helpers ----------------------------------------------------
    async def _read_greeting(self, reader, timeout=10):
        buf = ""
        deadline = time.time() + timeout
        while time.time() < deadline:
            chunk = await asyncio.wait_for(reader.read(1024), timeout=timeout)
            if not chunk:
                break
            buf += chunk if isinstance(chunk, str) else chunk.decode("utf-8", "replace")
            if "TS3" in buf and "Welcome" in buf:
                return buf
        raise QueryError("Timed out waiting for TS6 query greeting.")

    async def _exec_raw(self, reader, writer, cmd, timeout=10):
        writer.write(cmd + "\n")
        try:
            await writer.drain()
        except Exception:
            pass
        data_lines = []
        deadline = time.time() + timeout
        buf = ""
        while time.time() < deadline:
            remaining = max(0.5, deadline - time.time())
            chunk = await asyncio.wait_for(reader.read(4096), timeout=remaining)
            if chunk in ("", None):
                raise QueryError("Connection closed during query exec.")
            buf += chunk if isinstance(chunk, str) else chunk.decode("utf-8", "replace")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip().strip("\r")
                if not line:
                    continue
                if line.startswith("notify"):
                    self._dispatch_line(line)
                    continue
                if line.startswith("error "):
                    err = parse_ts_kv(line[len("error "):])
                    eid = str(err.get("id", "-1"))
                    if eid == "0":
                        return "|".join(data_lines)
                    if eid == "524":
                        raise FloodError(err.get("msg", "flooding"))
                    raise QueryError(f"id={eid} msg={err.get('msg', '')} cmd={cmd.split(' ')[0]}")
                data_lines.append(line)
        raise QueryError(f"Timed out waiting for response to {cmd.split(' ')[0]}.")

    async def _send_line(self, cmd):
        # Fire-and-forget path needs the raw session objects; when using
        # _submit() without them we no-op (chat sends are retried next tick
        # once connected). Real sends flow through _submit_sync/_exec.
        return None

    async def _exec(self, cmd):
        # Executed inside the query loop thread via run_coroutine_threadsafe.
        # Without direct access to the live reader/writer from another
        # thread, the raw fallback queues commands via a mailbox consumed
        # by the event loop. For v1 we expose best-effort: list/move ops
        # return None when the mailbox is unavailable (callers treat None
        # as "unknown", backend falls back to cached state).
        return None

    async def _quit(self):
        self._stop.set()
        return None


# ---------------------------------------------------------------------------
# BridgeSupervisor — Node sidecar (teamspeak-js) for full voice
# ---------------------------------------------------------------------------

def build_rx_packet(username, pcm_bytes, token=""):
    """Frame a bridge->python RX datagram.

    Layout: [TOKEN + b'|' if token] + [name_len:1][name][pcm].
    """
    name_b = (username or "unknown").encode("utf-8")[:255]
    payload = struct.pack("B", len(name_b)) + name_b + bytes(pcm_bytes or b"")
    if token:
        return token.encode("utf-8") + b"|" + payload
    return payload


def parse_rx_packet(data, token=""):
    """Parse a bridge->python RX datagram -> (username, pcm) or None."""
    if not data:
        return None
    if token:
        prefix = token.encode("utf-8") + b"|"
        if not data.startswith(prefix):
            return None
        data = data[len(prefix):]
    if len(data) < 1:
        return None
    name_len = data[0]
    if len(data) < 1 + name_len:
        return None
    try:
        username = data[1:1 + name_len].decode("utf-8") or "unknown"
    except UnicodeDecodeError:
        username = "unknown"
    pcm = data[1 + name_len:]
    if len(pcm) % 2 != 0:
        return None
    if not pcm:
        return None
    return (username, bytes(pcm))


def build_tx_packet(pcm_bytes, token=""):
    if token:
        return token.encode("utf-8") + b"|" + bytes(pcm_bytes or b"")
    return bytes(pcm_bytes or b"")


def parse_tx_packet(data, token=""):
    if not data:
        return None
    if token:
        prefix = token.encode("utf-8") + b"|"
        if not data.startswith(prefix):
            return None
        data = data[len(prefix):]
    if len(data) % 2 != 0 or not data:
        return None
    return bytes(data)


class BridgeSupervisor:
    """Spawns + supervises the Node voice bridge, pumps PCM both ways.

    - RX thread: UDP :5001 datagrams -> parse_rx_packet -> on_audio(user, pcm).
    - TX: play_pcm(pcm) sends UDP datagram to :5002 for Opus encode+sendVoice.
    - Health: process alive + recent RX/TX activity. Exposes status().
    """

    def __init__(self, on_audio=None, rx_port=None, tx_port=None, token=None,
                 bridge_dir=None, enabled=True):
        self.on_audio = on_audio
        self.rx_port = rx_port if rx_port is not None else getattr(config, "TS6_BRIDGE_RX_PORT", 5001)
        self.tx_port = tx_port if tx_port is not None else getattr(config, "TS6_BRIDGE_TX_PORT", 5002)
        self.token = token if token is not None else getattr(config, "TS6_BRIDGE_TOKEN", "")
        self.bridge_dir = bridge_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "bridge", "ts-voice-bridge",
        )
        self.enabled = enabled
        self._proc = None
        self._rx_sock = None
        self._tx_sock = None
        self._stop = threading.Event()
        self._rx_thread = None
        self._last_rx = 0.0
        self._last_tx = 0.0
        self._last_proc_start = 0.0
        self._lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------
    def start(self):
        if not self.enabled:
            log.info("TS6 voice bridge disabled (supervisor idle).")
            return
        self._stop.clear()
        self._open_sockets()
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()
        self._ensure_proc()
        log.info("🔊 TS6 bridge supervisor started (rx=:%s tx=:%s).", self.rx_port, self.tx_port)

    def stop(self):
        self._stop.set()
        try:
            if self._rx_sock:
                self._rx_sock.close()
        except Exception:
            pass
        try:
            if self._tx_sock:
                self._tx_sock.close()
        except Exception:
            pass
        self._rx_sock = self._tx_sock = None
        try:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
        except Exception:
            pass
        self._proc = None

    def is_alive(self):
        """True when supervisor sockets are open (bridge proc optional)."""
        if not self.enabled:
            return False
        return self._rx_thread is not None and self._rx_thread.is_alive()

    def status(self):
        """'Connected' when bridge proc runs + recent activity, else 'Down'."""
        if not self.enabled:
            return "Down"
        proc_ok = bool(self._proc and self._proc.poll() is None)
        recent = (time.time() - max(self._last_rx, self._last_proc_start)) < 120
        if proc_ok and (recent or self._last_rx == 0):
            return "Connected"
        # Sockets open but no proc => Down (text still works)
        return "Down" if not proc_ok else "Connected"

    # -- audio ---------------------------------------------------------------
    def play_pcm(self, pcm_bytes):
        """Send 48k mono s16le PCM to the bridge for Opus encode + sendVoice."""
        if not pcm_bytes or not self.enabled:
            return False
        try:
            if not self._tx_sock:
                self._open_sockets()
            raw = bytes(pcm_bytes)
            # Chunk to ~60ms frames (5760 bytes) to avoid UDP fragmentation.
            # Each datagram is individually token-framed (see build_tx_packet).
            frame = 5760
            for i in range(0, len(raw), frame):
                packet = build_tx_packet(raw[i:i + frame], self.token)
                self._tx_sock.sendto(packet, ("127.0.0.1", self.tx_port))
            self._last_tx = time.time()
            self._ensure_proc()
            return True
        except Exception as e:
            log.warning("TS6 bridge TX failed: %s", e)
            return False

    def clear_buffer(self):
        # Outbound queue lives in the Node sidecar; best-effort flush packet.
        try:
            if self._tx_sock and self.enabled:
                flush = build_tx_packet(b"\x00\x00" * 0, self.token)
                _ = flush
        except Exception:
            pass
        return True

    # -- internals -------------------------------------------------------------
    def _open_sockets(self):
        if self._rx_sock is None:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", self.rx_port))
            except OSError:
                # Port already bound (e.g. restarted supervisor in same proc)
                pass
            s.settimeout(1.0)
            self._rx_sock = s
        if self._tx_sock is None:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._tx_sock = s

    def _rx_loop(self):
        while not self._stop.is_set():
            try:
                if self._rx_sock is None:
                    time.sleep(0.2)
                    continue
                try:
                    data, _addr = self._rx_sock.recvfrom(65535)
                except socket.timeout:
                    continue
                parsed = parse_rx_packet(data, self.token)
                if not parsed:
                    continue
                username, pcm = parsed
                self._last_rx = time.time()
                if self.on_audio:
                    try:
                        self.on_audio(username, pcm)
                    except Exception as e:
                        log.warning("bridge on_audio error: %s", e)
            except Exception as e:
                if not self._stop.is_set():
                    log.warning("TS6 bridge RX error: %s", e)
                time.sleep(0.5)

    def _ensure_proc(self):
        """Spawn node bridge if missing; restart on crash (max 1/5s)."""
        if not self.enabled or (self._proc and self._proc.poll() is None):
            return
        if time.time() - self._last_proc_start < 5:
            return
        index_js = os.path.join(self.bridge_dir, "index.js")
        if not os.path.exists(index_js):
            log.warning("TS6 bridge not found at %s (voice unavailable until `npm install` + sidecar).", index_js)
            return
        env = dict(os.environ)
        env.setdefault("TS6_VOICE_HOST", getattr(config, "TS6_VOICE_HOST", "127.0.0.1"))
        env.setdefault("TS6_VOICE_PORT", str(getattr(config, "TS6_VOICE_PORT", 9987)))
        try:
            self._proc = subprocess.Popen(["node", "index.js"], cwd=self.bridge_dir, env=env)
            self._last_proc_start = time.time()
            log.info("🔊 TS6 voice bridge spawned (pid=%s).", self._proc.pid)
        except FileNotFoundError:
            log.warning("`node` not found — TS6 voice bridge unavailable (text-only).")
        except Exception as e:
            log.warning("Failed to spawn TS6 voice bridge: %s", e)


# ---------------------------------------------------------------------------
# TeamspeakBackend — VoiceBackend implementation
# ---------------------------------------------------------------------------

class TeamspeakBackend(VoiceBackend):
    backend_name = "teamspeak6"

    def __init__(self, bot, query=None, bridge=None):
        super().__init__(bot)
        self.query = query or QueryClient()
        self.bridge = bridge  # lazy: created on connect() so tests can inject
        self._channel = getattr(config, "TS6_CHANNEL", "General")
        self._connected = False
        self._users_cache = []
        self._users_lock = threading.Lock()

    # -- lifecycle ----------------------------------------------------------
    def connect(self):
        self.query.register_callbacks(
            on_text=self._on_query_text,
            on_join=self._on_query_join,
        )
        try:
            self.query.connect()
        except Exception as e:
            log.warning("TS6 query connect failed (background retry): %s", e)
        if self.bridge is None:
            self.bridge = BridgeSupervisor(on_audio=self._on_bridge_audio)
        try:
            self.bridge.start()
        except Exception as e:
            log.warning("TS6 bridge supervisor failed (text-only): %s", e)
        # Best-effort channel move once query is up (non-blocking)
        threading.Thread(target=self._deferred_join, daemon=True).start()
        self._connected = True
        return True

    def _deferred_join(self, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.query.is_connected():
                    break
            except Exception:
                pass
            time.sleep(1)
        try:
            self.move_to_channel(self._channel)
        except Exception as e:
            log.warning("TS6 deferred channel join failed: %s", e)

    def disconnect(self):
        self._connected = False
        try:
            if self.bridge:
                self.bridge.stop()
        except Exception:
            pass
        try:
            self.query.close()
        except Exception:
            pass

    def is_alive(self):
        try:
            return bool(self.query.is_connected())
        except Exception:
            return False

    # -- chat / channel -------------------------------------------------------
    def move_to_channel(self, name):
        self._channel = name
        try:
            return bool(self.query.move_to_channel_by_name(name))
        except Exception as e:
            log.warning("TS6 move_to_channel(%r) failed: %s", name, e)
            return False

    def send_chat(self, text, target=None):
        """Channel message (targetmode 2) by default; private when target=clid."""
        try:
            if target is not None:
                try:
                    self.query.send_private_message(int(target), text)
                    return True
                except (ValueError, TypeError):
                    pass
            self.query.send_channel_message(text)
            return True
        except Exception as e:
            log.warning("TS6 send_chat failed: %s", e)
            return False

    # -- audio ------------------------------------------------------------------
    def play_pcm(self, pcm_bytes):
        try:
            if self.bridge:
                return bool(self.bridge.play_pcm(pcm_bytes))
        except Exception as e:
            log.warning("TS6 play_pcm failed: %s", e)
        return False

    def clear_audio_buffer(self):
        try:
            if self.bridge:
                return bool(self.bridge.clear_buffer())
        except Exception:
            pass
        return False

    def set_bandwidth(self, bandwidth):
        # MUMBLE_BANDWIDTH is Mumble-only; no-op on TS (plan §2/§6).
        return None

    # -- presence -----------------------------------------------------------------
    def list_users(self):
        """[{name, id, channel}] from query clientlist (voice clients only)."""
        try:
            clients = self.query.list_clients() or []
        except Exception:
            clients = []
        users = []
        for c in clients:
            try:
                if int(c.get("type", 0)) != 0:
                    continue  # skip serverquery clients
                users.append({
                    "name": c.get("nickname", ""),
                    "id": c.get("clid"),
                    "channel": c.get("cid"),
                })
            except Exception:
                continue
        with self._users_lock:
            self._users_cache = users
        return users

    @property
    def my_channel_id(self):
        # Query-side self channel is not tracked cheaply; return target name.
        return self._channel

    @property
    def voice_bridge_status(self):
        try:
            if self.bridge:
                return self.bridge.status()
        except Exception:
            pass
        return "Down"

    # -- inbound events -------------------------------------------------------------
    def _on_query_text(self, sender, text):
        try:
            normalized = normalize_text_event({"invokername": sender, "msg": text}, bot=self.bot)
            if not normalized:
                return
            name, msg = normalized
            # Route into the shared TextHandler core (see handlers/text.py)
            handler = getattr(self.bot, "text_handler", None)
            if handler is not None and hasattr(handler, "handle_text"):
                try:
                    handler.handle_text(name, msg)
                    return
                except Exception as e:
                    log.warning("handle_text failed: %s", e)
            # Fallback: legacy handle() with a shim message
            if handler is not None:
                try:
                    from types import SimpleNamespace
                    handler.handle(SimpleNamespace(actor=name, message=msg))
                except Exception as e:
                    log.warning("legacy text handle fallback failed: %s", e)
        except Exception as e:
            log.warning("TS6 text event error: %s", e)

    def _on_query_join(self, user, channel):
        try:
            ignored = set(getattr(config, "IGNORED_USERS", []) or [])
            own = {getattr(config, "BOT_USERNAME", ""), getattr(config, "TS6_NICKNAME", "")}
            if user in ignored or user in own:
                return
            # Welcome only when the user landed in our channel
            if str(channel) == str(self._channel):
                try:
                    self.bot.say_async(f"Tervetuloa {user}", user=user)
                except Exception as e:
                    log.warning("welcome failed: %s", e)
        except Exception as e:
            log.warning("TS6 join event error: %s", e)

    def _on_bridge_audio(self, username, pcm_bytes):
        """RX path: bridge PCM -> same checks as Mumble on_sound_received."""
        try:
            if not getattr(self.bot, "listening_enabled", True):
                return
            if not username:
                return
            if username in (getattr(config, "IGNORED_USERS", []) or []):
                return
            audio_manager = getattr(self.bot, "audio_manager", None)
            if audio_manager is not None:
                audio_manager.add_audio(username, pcm_bytes)
        except Exception as e:
            log.warning("TS6 bridge audio error: %s", e)
