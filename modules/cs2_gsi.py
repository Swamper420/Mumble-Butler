"""
CS2 Game State Integration (GSI) Module
========================================
Receives HTTP POST payloads pushed by CS2 and fires commentary events:
  - Kill feed with multi-kill buffering (e.g. double/triple/ace)
  - Round-end economic report
  - Live game state announcements (bomb planted, half-time, etc.)
"""

import json
import threading
import time
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import defaultdict

import config

logger = logging.getLogger("CS2GSI")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _team_label(side: str) -> str:
    return "Counter-Terrorists" if side == "CT" else "Terrorists"


def _money_str(amount: int) -> str:
    return f"${amount:,}"


def _eco_label(money: int, has_armor: bool, has_rifle: bool) -> str:
    """Classify a player's economic state into a human-readable label."""
    if money < 1400:
        return "eco"
    if not has_rifle and money < 3000:
        return "force buy"
    if has_armor and has_rifle:
        return "full buy"
    return "partial buy"


# ---------------------------------------------------------------------------
# Main GSI module
# ---------------------------------------------------------------------------

class CS2GSI:
    """
    Manages CS2 game state and fires callbacks to the bot.

    Callbacks (all optional, set after construction):
        on_kill_commentary(kills: list[dict]) -> None
        on_round_end(report: dict) -> None
        on_bomb_planted(site: str) -> None
        on_game_phase_change(new_phase: str, old_phase: str) -> None
    """

    # ------------------------------------------------------------------
    # Kill event structure: each entry pushed to self._kill_buffer
    # {
    #   "killer": str, "victim": str, "weapon": str, "headshot": bool,
    #   "killer_team": str, "victim_team": str, "timestamp": float
    # }
    # ------------------------------------------------------------------

    def __init__(self):
        self.state = {}          # Full latest GSI payload
        self.prev_state = {}     # Previous payload for delta detection

        # Kill feed
        self._kill_buffer: list[dict] = []
        self._kill_lock = threading.Lock()
        self._kill_flush_timer: threading.Timer | None = None

        # Round tracking
        self._prev_round_phase: str = ""
        self._prev_map_phase: str = ""
        self._prev_bomb_state: str = ""

        # Callbacks (set by bot after construction)
        self.on_kill_commentary = None
        self.on_round_end = None
        self.on_bomb_planted = None
        self.on_game_phase_change = None

        # HTTP server
        self._server: HTTPServer | None = None
        self._server_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    def start(self, host: str = "0.0.0.0", port: int = 9100):
        """Starts the GSI HTTP listener in a background daemon thread."""
        gsi_module = self  # capture for handler closure

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass  # silence default HTTP log noise

            def do_POST(self):
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length)
                    payload = json.loads(body.decode("utf-8"))
                    gsi_module._on_payload(payload)
                except Exception as e:
                    logger.warning(f"GSI parse error: {e}")
                finally:
                    self.send_response(200)
                    self.end_headers()

        self._server = HTTPServer((host, port), _Handler)
        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="CS2-GSI-Server"
        )
        self._server_thread.start()
        logger.info(f"🎮 CS2 GSI listening on {host}:{port}")

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._kill_flush_timer:
            self._kill_flush_timer.cancel()

    # ------------------------------------------------------------------
    # Payload processing
    # ------------------------------------------------------------------

    def _on_payload(self, payload: dict):
        """Entry point for every incoming GSI payload."""
        self.prev_state = self.state
        self.state = payload

        self._process_kill_feed(payload)
        self._process_round_phase(payload)
        self._process_map_phase(payload)
        self._process_bomb(payload)

    # ------------------------------------------------------------------
    # Kill feed with multi-kill buffer
    # ------------------------------------------------------------------

    def _process_kill_feed(self, payload: dict):
        """
        Detects new kills by comparing allplayers match stats against the
        previous payload. Buffers kills for KILL_BUFFER_SECONDS, then
        flushes the whole burst to on_kill_commentary.
        """
        buffer_secs = getattr(config, "CS2_KILL_BUFFER_SECONDS", 3.0)

        cur_players = payload.get("allplayers", {})
        prev_players = self.prev_state.get("allplayers", {})

        if not cur_players or not prev_players:
            return

        # Also grab recently_killed added by GSI (not always present)
        # Fallback: diff kill counts per player
        for steam_id, cur_data in cur_players.items():
            prev_data = prev_players.get(steam_id)
            if not prev_data:
                continue

            cur_kills = (cur_data.get("match_stats") or {}).get("kills", 0)
            prev_kills = (prev_data.get("match_stats") or {}).get("kills", 0)

            if cur_kills <= prev_kills:
                continue

            # Build kill event(s) — typically 1 per update but could be >1
            delta = cur_kills - prev_kills
            for _ in range(delta):
                kill_event = {
                    "killer": (cur_data.get("name") or steam_id),
                    "killer_team": cur_data.get("team", ""),
                    "weapon": self._infer_weapon(cur_data),
                    "headshot": self._check_headshot(cur_data, prev_data),
                    "victim": "",   # GSI doesn't give us victim directly from stats
                    "timestamp": time.time(),
                }
                logger.debug(f"🔫 Kill detected: {kill_event['killer']}")
                with self._kill_lock:
                    self._kill_buffer.append(kill_event)

            # Restart the flush timer every new kill
            self._reset_kill_timer(buffer_secs)

    def _reset_kill_timer(self, buffer_secs: float):
        """Restarts the debounce timer that triggers commentary flush."""
        with self._kill_lock:
            if self._kill_flush_timer:
                self._kill_flush_timer.cancel()
            self._kill_flush_timer = threading.Timer(
                buffer_secs, self._flush_kill_buffer
            )
            self._kill_flush_timer.daemon = True
            self._kill_flush_timer.start()

    def _flush_kill_buffer(self):
        """Called after buffer window expires. Fires commentary callback."""
        with self._kill_lock:
            kills = list(self._kill_buffer)
            self._kill_buffer.clear()
            self._kill_flush_timer = None

        if kills and self.on_kill_commentary:
            try:
                self.on_kill_commentary(kills)
            except Exception as e:
                logger.error(f"Kill commentary callback error: {e}")

    def _infer_weapon(self, player_data: dict) -> str:
        """Best-effort weapon from allplayers_weapons payload."""
        weapons = player_data.get("weapons") or {}
        for slot, w in weapons.items():
            if w.get("state") == "active":
                name = w.get("name", "weapon_unknown")
                # Strip "weapon_" prefix
                return name.replace("weapon_", "").replace("_", " ")
        return "unknown"

    def _check_headshot(self, cur: dict, prev: dict) -> bool:
        """Headshots aren't directly exposed per-kill; return False as safe default."""
        # Some GSI implementations expose headshots via player_state.
        # Without victim info we can't be certain — return False conservatively.
        return False

    # ------------------------------------------------------------------
    # Round phase (freezetime → live → over)
    # ------------------------------------------------------------------

    def _process_round_phase(self, payload: dict):
        round_data = payload.get("round") or {}
        phase = round_data.get("phase", "")

        if phase == self._prev_round_phase:
            return

        old_phase = self._prev_round_phase
        self._prev_round_phase = phase

        logger.debug(f"Round phase: {old_phase} → {phase}")

        if phase == "over":
            self._fire_round_end(payload, round_data)
        
        if self.on_game_phase_change and phase:
            try:
                self.on_game_phase_change(phase, old_phase)
            except Exception as e:
                logger.error(f"Phase change callback error: {e}")

    def _fire_round_end(self, payload: dict, round_data: dict):
        """Build end-of-round report dict and call on_round_end."""
        if not self.on_round_end:
            return

        win_team = round_data.get("win_team", "")
        win_condition = round_data.get("win_condition", "")

        map_data = payload.get("map") or {}
        ct_score = (map_data.get("team_ct") or {}).get("score", 0)
        t_score = (map_data.get("team_t") or {}).get("score", 0)

        # Per-player economic snapshot for post-round report
        all_players = payload.get("allplayers") or {}
        player_reports = []
        for sid, p in all_players.items():
            state = p.get("state") or {}
            weapons = p.get("weapons") or {}
            match_stats = p.get("match_stats") or {}

            has_rifle = any(
                w.get("type") in ("Rifle", "Sniper Rifle")
                for w in weapons.values()
            )
            has_armor = state.get("armor", 0) > 0
            money = state.get("money", 0)

            player_reports.append({
                "name": p.get("name", sid),
                "team": p.get("team", ""),
                "money": money,
                "eco_label": _eco_label(money, has_armor, has_rifle),
                "kills": match_stats.get("kills", 0),
                "deaths": match_stats.get("deaths", 0),
                "assists": match_stats.get("assists", 0),
                "health": state.get("health", 0),
            })

        report = {
            "win_team": win_team,
            "win_condition": win_condition,
            "ct_score": ct_score,
            "t_score": t_score,
            "players": player_reports,
            "map": map_data.get("name", "unknown"),
            "round_number": map_data.get("round", 0),
        }

        try:
            self.on_round_end(report)
        except Exception as e:
            logger.error(f"Round end callback error: {e}")

    # ------------------------------------------------------------------
    # Map phase (warmup → live → halftime → gameover)
    # ------------------------------------------------------------------

    def _process_map_phase(self, payload: dict):
        map_data = payload.get("map") or {}
        phase = map_data.get("phase", "")

        if phase == self._prev_map_phase:
            return

        old_phase = self._prev_map_phase
        self._prev_map_phase = phase

        logger.info(f"Map phase: {old_phase} → {phase}")

        if self.on_game_phase_change and phase:
            # Prefix map phases so bot can distinguish from round phases
            try:
                self.on_game_phase_change(f"map:{phase}", f"map:{old_phase}")
            except Exception as e:
                logger.error(f"Map phase callback error: {e}")

    # ------------------------------------------------------------------
    # Bomb state
    # ------------------------------------------------------------------

    def _process_bomb(self, payload: dict):
        round_data = payload.get("round") or {}
        bomb = round_data.get("bomb", "")

        if bomb == self._prev_bomb_state:
            return
        self._prev_bomb_state = bomb

        if bomb == "planted" and self.on_bomb_planted:
            # Determine site from allplayers position if available — non-trivial.
            # For now we pass an empty string; can be enhanced later.
            try:
                self.on_bomb_planted("")
            except Exception as e:
                logger.error(f"Bomb planted callback error: {e}")

    # ------------------------------------------------------------------
    # Public state accessors (for voice commands)
    # ------------------------------------------------------------------

    def get_score(self) -> dict | None:
        """Returns current score dict or None if no game state."""
        map_data = self.state.get("map")
        if not map_data:
            return None
        return {
            "ct": (map_data.get("team_ct") or {}).get("score", 0),
            "t": (map_data.get("team_t") or {}).get("score", 0),
            "map": map_data.get("name", "unknown"),
            "round": map_data.get("round", 0),
            "phase": map_data.get("phase", ""),
        }

    def get_player_stats(self, name: str) -> dict | None:
        """Looks up a player by name (case-insensitive) and returns their stats."""
        players = self.state.get("allplayers") or {}
        for p in players.values():
            if (p.get("name") or "").lower() == name.lower():
                stats = p.get("match_stats") or {}
                state = p.get("state") or {}
                return {
                    "name": p.get("name"),
                    "team": p.get("team"),
                    "kills": stats.get("kills", 0),
                    "deaths": stats.get("deaths", 0),
                    "assists": stats.get("assists", 0),
                    "health": state.get("health", 0),
                    "money": state.get("money", 0),
                }
        return None

    def is_active(self) -> bool:
        """Returns True if GSI data is fresh (received within last 60s)."""
        provider = self.state.get("provider") or {}
        ts = provider.get("timestamp", 0)
        return (time.time() - ts) < 60
