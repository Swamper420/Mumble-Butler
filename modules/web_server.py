import os
import re
import json
import logging
import threading
from urllib.parse import parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

import config

logger = logging.getLogger("BotWebServer")

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in separate threads for non-blocking HTTP handling."""
    daemon_threads = True


class ConfigManager:
    """Dynamically inspects, categorizes, and updates bot configuration settings."""
    
    # Categorization mapping based on variable name patterns
    CATEGORY_PATTERNS = [
        ("Web Server", ["WEB_SERVER_"]),
        ("Connection & Server", ["SERVER_", "BOT_", "PASSWORD", "TARGET_CHANNEL", "IGNORED_USERS", "RECONNECT_DELAY"]),
        ("Paths & Files", ["STATS_FILE", "CHIME_FILE", "MUSIC_HISTORY_FILE", "CHATTERBOX_VOICE_DIR"]),
        ("LLM & Ollama", ["OLLAMA_", "LLM_", "WEB_SEARCH_"]),
        ("AI Models & Audio", ["MOONSHINE_", "WAKEWORD_", "SILENCE_THRESHOLD", "MIN_AUDIO_LENGTH", "POLL_RATE"]),
        ("Voice & TTS", ["ACTIVATION_KEYWORDS", "MEMORY_ENABLED", "SYSTEM_PROMPT", "SHUTUP_KEYWORDS", "CHATTERBOX_", "FAST_AUDIO_", "FAST_WAKEWORD_", "FAST_ACTION_"]),
        ("Triggers & Commands", ["VOICE_TRIGGERS", "MUMBLE_COMMANDS", "TEXT_TRIGGERS"]),
        ("Recommender", ["RECOMMENDER_"]),
    ]

    @classmethod
    def get_all_config(cls):
        """Discovers all configurable variables in config.py dynamically."""
        config_items = []
        for name in dir(config):
            if name.startswith("_") or not name.isupper():
                continue
            
            value = getattr(config, name)
            
            # Categorize
            category = "Other / Custom"
            for cat_name, prefixes in cls.CATEGORY_PATTERNS:
                if any(name.startswith(p) for p in prefixes):
                    category = cat_name
                    break
                    
            val_type = type(value).__name__
            
            config_items.append({
                "key": name,
                "value": value,
                "type": val_type,
                "category": category,
                "display_val": cls.format_for_display(value)
            })
            
        return config_items

    @classmethod
    def format_for_display(cls, value):
        if isinstance(value, (list, tuple)):
            return ", ".join(str(v) for v in value)
        elif isinstance(value, dict):
            return json.dumps(value, indent=2)
        elif value is None:
            return ""
        return str(value)

    @classmethod
    def update_config_var(cls, key, raw_value):
        """Updates a configuration variable in memory and persists to .env."""
        if not hasattr(config, key) or not key.isupper():
            return False, f"Invalid configuration key: '{key}'"

        current_val = getattr(config, key)
        curr_type = type(current_val)

        try:
            # Cast new value to appropriate type
            if curr_type == bool:
                new_val = str(raw_value).strip().lower() in ("true", "1", "yes", "on")
            elif curr_type == int:
                new_val = int(raw_value)
            elif curr_type == float:
                new_val = float(raw_value)
            elif curr_type == list:
                if isinstance(raw_value, str):
                    new_val = [item.strip() for item in raw_value.split(",") if item.strip()]
                else:
                    new_val = list(raw_value)
            elif curr_type == dict:
                new_val = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
            else:
                new_val = str(raw_value)

            # Update memory
            setattr(config, key, new_val)
            
            # Persist to .env
            cls._update_env_file(key, raw_value if not isinstance(raw_value, dict) else json.dumps(raw_value))

            logger.info(f"Updated config {key} = {new_val}")
            return True, f"Successfully updated '{key}'!"
        except Exception as e:
            logger.error(f"Failed to update config {key}: {e}")
            return False, f"Error updating '{key}': {e}"

    @classmethod
    def _update_env_file(cls, key, env_val_str):
        """Persists the key-value pair to the .env file."""
        env_path = os.path.abspath(".env")
        lines = []
        key_found = False

        if isinstance(env_val_str, (list, tuple)):
            val_formatted = ",".join(str(x) for x in env_val_str)
        else:
            val_formatted = str(env_val_str).replace("\n", "\\n")

        # Read existing lines if .env exists
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith(f"{key}="):
                        lines.append(f"{key}={val_formatted}\n")
                        key_found = True
                    else:
                        lines.append(line)

        if not key_found:
            lines.append(f"{key}={val_formatted}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)


class WebRequestHandler(BaseHTTPRequestHandler):
    """HTMX-enabled HTTP Request Handler for Bot Control and Config Panel."""
    
    bot_instance = None

    def log_message(self, format, *args):
        # Silence routine HTTP access logs to keep bot terminal clean
        pass

    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path == "/":
            self.serve_index()
        elif path == "/api/status":
            self.serve_status_partial()
        elif path == "/api/config":
            self.serve_config_partial()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path == "/api/config/update":
            content_len = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_len).decode("utf-8")
            params = parse_qs(post_body)
            
            key = params.get("key", [""])[0].strip()
            value = params.get("value", [""])[0]

            success, message = ConfigManager.update_config_var(key, value)
            self.serve_toast_partial(success, message)
        elif path == "/api/bot/action":
            content_len = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_len).decode("utf-8")
            params = parse_qs(post_body)
            action = params.get("action", [""])[0]

            self.handle_bot_action(action)
        else:
            self.send_error(404, "Not Found")

    def serve_index(self):
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mumble-Butler Dashboard</title>
    <!-- HTMX CDN -->
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <style>
        :root {{
            --bg-main: #0b0f19;
            --bg-card: #151c2c;
            --bg-input: #1e293b;
            --border-color: #2e3d52;
            --accent: #6366f1;
            --accent-hover: #4f46e5;
            --accent-glow: rgba(99, 102, 241, 0.25);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --success: #10b981;
            --error: #ef4444;
            --warning: #f59e0b;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }}

        body {{
            background-color: var(--bg-main);
            color: var(--text-main);
            padding: 2rem 1rem;
            min-height: 100vh;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border-color);
        }}

        header h1 {{
            font-size: 1.8rem;
            font-weight: 700;
            background: linear-gradient(135deg, #a855f7, #6366f1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}

        .badge {{
            font-size: 0.75rem;
            padding: 0.25rem 0.6rem;
            border-radius: 9999px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .badge-live {{
            background: rgba(16, 185, 129, 0.15);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}

        #toast-container {{
            position: fixed;
            top: 1rem;
            right: 1rem;
            z-index: 1000;
        }}

        .toast {{
            padding: 0.85rem 1.25rem;
            border-radius: 8px;
            font-weight: 500;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
            animation: slideIn 0.2s ease-out;
            margin-bottom: 0.5rem;
        }}

        .toast-success {{
            background: #064e3b;
            color: #6ee7b7;
            border: 1px solid #047857;
        }}

        .toast-error {{
            background: #7f1d1d;
            color: #fca5a5;
            border: 1px solid #dc2626;
        }}

        @keyframes slideIn {{
            from {{ transform: translateX(100%); opacity: 0; }}
            to {{ transform: translateX(0); opacity: 1; }}
        }}

        .grid {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 1.5rem;
        }}

        @media (min-width: 1024px) {{
            .grid {{
                grid-template-columns: 350px 1fr;
            }}
        }}

        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
        }}

        .card h2 {{
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 1rem;
            color: var(--text-main);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .status-list {{
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }}

        .status-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.5rem 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }}

        .status-label {{
            color: var(--text-muted);
            font-size: 0.9rem;
        }}

        .status-value {{
            font-family: monospace;
            font-weight: 600;
            font-size: 0.95rem;
        }}

        .btn {{
            background: var(--accent);
            color: white;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
        }}

        .btn:hover {{
            background: var(--accent-hover);
            box-shadow: 0 0 10px var(--accent-glow);
        }}

        .btn-sm {{
            padding: 0.25rem 0.6rem;
            font-size: 0.8rem;
        }}

        .btn-outline {{
            background: transparent;
            border: 1px solid var(--border-color);
            color: var(--text-main);
        }}

        .btn-outline:hover {{
            background: var(--bg-input);
        }}

        .category-group {{
            margin-bottom: 2rem;
        }}

        .category-title {{
            font-size: 1rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--accent);
            margin-bottom: 0.75rem;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 0.35rem;
        }}

        .config-table {{
            width: 100%;
            border-collapse: collapse;
        }}

        .config-row {{
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            transition: background 0.15s ease;
        }}

        .config-row:hover {{
            background: rgba(255, 255, 255, 0.02);
        }}

        .config-cell {{
            padding: 0.85rem 0.5rem;
            vertical-align: middle;
        }}

        .config-key {{
            font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
            font-size: 0.85rem;
            color: #e2e8f0;
            font-weight: 600;
        }}

        .config-type {{
            font-size: 0.7rem;
            color: var(--text-muted);
            font-family: monospace;
        }}

        .config-input {{
            background: var(--bg-input);
            border: 1px solid var(--border-color);
            color: var(--text-main);
            padding: 0.5rem 0.75rem;
            border-radius: 6px;
            width: 100%;
            font-family: monospace;
            font-size: 0.85rem;
            transition: border-color 0.15s ease;
        }}

        .config-input:focus {{
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 0 2px var(--accent-glow);
        }}

        textarea.config-input {{
            min-height: 70px;
            resize: vertical;
        }}

        .form-flex {{
            display: flex;
            gap: 0.5rem;
            align-items: center;
        }}

        .pulse-dot {{
            width: 8px;
            height: 8px;
            background-color: var(--success);
            border-radius: 50%;
            display: inline-block;
            box-shadow: 0 0 8px var(--success);
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>
                🤖 Mumble-Butler Web Control
                <span class="badge badge-live"><span class="pulse-dot"></span> HTMX Active</span>
            </h1>
            <div style="font-size: 0.85rem; color: var(--text-muted);">Auto-updating Configuration Panel</div>
        </header>

        <div id="toast-container"></div>

        <div class="grid">
            <!-- Sidebar: Live Bot Status -->
            <div>
                <div class="card" hx-get="/api/status" hx-trigger="every 3s" hx-swap="innerHTML">
                    <!-- Loaded via HTMX -->
                    <div style="color: var(--text-muted);">Loading status...</div>
                </div>
            </div>

            <!-- Main: Dynamic Configuration Section -->
            <div>
                <div class="card">
                    <h2>
                        ⚙️ System Configuration
                        <span style="font-size: 0.75rem; font-weight: normal; color: var(--text-muted);">
                            Auto-discovers backend settings dynamically
                        </span>
                    </h2>
                    <div id="config-container" hx-get="/api/config" hx-trigger="load, every 10s" hx-swap="innerHTML">
                        <div style="color: var(--text-muted); padding: 1rem 0;">Discovering configuration settings...</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def serve_status_partial(self):
        bot = WebRequestHandler.bot_instance
        status_dict = bot.get_status() if bot else {}
        
        status_html = f"""<h2>
            📊 Bot Health & Metrics
            <button class="btn btn-sm btn-outline" hx-get="/api/status" hx-target="closest .card" hx-swap="innerHTML">Refresh</button>
        </h2>
        <div class="status-list">"""
        
        for k, v in status_dict.items():
            color_style = ""
            if v in ("Connected", "Online", "Ready", "Active", "ON"):
                color_style = "color: var(--success);"
            elif v in ("Disconnected", "Offline", "Error", "OFF"):
                color_style = "color: var(--error);"

            status_html += f"""
            <div class="status-item">
                <span class="status-label">{k}</span>
                <span class="status-value" style="{color_style}">{v}</span>
            </div>"""

        if bot:
            status_html += f"""
            <div style="margin-top: 1.25rem; padding-top: 1rem; border-top: 1px solid var(--border-color);">
                <div style="font-size: 0.85rem; font-weight: 600; margin-bottom: 0.5rem;">Control Actions</div>
                <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                    <form hx-post="/api/bot/action" hx-target="#toast-container" hx-swap="beforeend">
                        <input type="hidden" name="action" value="toggle_listen">
                        <button type="submit" class="btn btn-sm btn-outline">
                            {'🔇 Disable Listening' if bot.listening_enabled else '🎙️ Enable Listening'}
                        </button>
                    </form>
                </div>
            </div>"""

        status_html += "</div>"
        
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(status_html.encode("utf-8"))

    def serve_config_partial(self):
        config_items = ConfigManager.get_all_config()
        
        # Group items by category
        categories = {}
        for item in config_items:
            cat = item["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(item)

        html = ""
        for cat_name, items in categories.items():
            html += f"""<div class="category-group">
                <div class="category-title">{cat_name}</div>
                <table class="config-table">
                    <tbody>"""
            
            for item in items:
                key = item["key"]
                val = item["display_val"]
                val_type = item["type"]

                # Use textarea for system prompt or dicts, input for standard strings/numbers/bools
                if val_type == "dict" or len(val) > 60 or "\n" in val:
                    input_field = f"""<textarea name="value" class="config-input">{val}</textarea>"""
                elif val_type == "bool":
                    is_true = str(val).lower() == "true"
                    input_field = f"""<select name="value" class="config-input">
                        <option value="True" {'selected' if is_true else ''}>True</option>
                        <option value="False" {'selected' if not is_true else ''}>False</option>
                    </select>"""
                else:
                    input_field = f"""<input type="text" name="value" value="{val}" class="config-input">"""

                html += f"""
                <tr class="config-row">
                    <td class="config-cell" style="width: 30%;">
                        <div class="config-key">{key}</div>
                        <div class="config-type">Type: {val_type}</div>
                    </td>
                    <td class="config-cell">
                        <form hx-post="/api/config/update" hx-target="#toast-container" hx-swap="beforeend" class="form-flex">
                            <input type="hidden" name="key" value="{key}">
                            {input_field}
                            <button type="submit" class="btn btn-sm">Save</button>
                        </form>
                    </td>
                </tr>"""

            html += """</tbody></table></div>"""

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def serve_toast_partial(self, success, message):
        css_class = "toast-success" if success else "toast-error"
        html = f"""<div class="toast {css_class}" onclick="this.remove()">
            {'✅' if success else '❌'} {message}
        </div>
        <script>
            setTimeout(() => {{
                const toasts = document.querySelectorAll('.toast');
                if (toasts.length > 0) toasts[0].remove();
            }}, 4000);
        </script>"""
        
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def handle_bot_action(self, action):
        bot = WebRequestHandler.bot_instance
        success = False
        message = "No active bot instance"

        if bot:
            if action == "toggle_listen":
                bot.listening_enabled = not bot.listening_enabled
                state = "enabled" if bot.listening_enabled else "disabled"
                success = True
                message = f"Voice listening has been {state}."

        self.serve_toast_partial(success, message)


class BotWebServer:
    """Manages the background HTTP web server thread for Mumble-Butler."""

    def __init__(self, bot_instance=None, host=None, port=None):
        self.bot = bot_instance
        self.host = host or getattr(config, "WEB_SERVER_HOST", "0.0.0.0")
        self.port = port or getattr(config, "WEB_SERVER_PORT", 8080)
        self.server = None
        self.thread = None

        WebRequestHandler.bot_instance = self.bot

    def start(self):
        if not getattr(config, "WEB_SERVER_ENABLED", True):
            logger.info("Web server is disabled in config.")
            return

        try:
            self.server = ThreadedHTTPServer((self.host, self.port), WebRequestHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            logger.info(f"🌐 Bot Web Interface running at http://{self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to start Bot Web Server on port {self.port}: {e}")

    def stop(self):
        if self.server:
            logger.info("Stopping Web Server...")
            self.server.shutdown()
            self.server.server_close()
            self.server = None
            logger.info("Web Server stopped.")
