import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config

_ear = None


class _VoiceRequestHandler(BaseHTTPRequestHandler):
    server_version = "MumbleButlerVoice/1.0"

    def _send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        ear = _ear
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "stt_loaded": bool(ear and ear.model is not None)})
            return
        self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path != "/transcribe":
            self._send_json(404, {"error": "Not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": "Invalid Content-Length header"})
            return

        if content_length <= 0:
            self._send_json(400, {"error": "Request body is required"})
            return

        try:
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "Body must be valid JSON"})
            return

        pcm_base64 = data.get("pcm_base64")
        if not isinstance(pcm_base64, str) or not pcm_base64.strip():
            self._send_json(400, {"error": "Field 'pcm_base64' must be a non-empty string"})
            return

        try:
            raw_pcm = base64.b64decode(pcm_base64, validate=True)
        except (ValueError, TypeError):
            self._send_json(400, {"error": "Field 'pcm_base64' must be valid base64"})
            return

        ear = _ear
        if ear is None or ear.model is None:
            self._send_json(503, {"error": "Voice recognition is not loaded"})
            return

        try:
            transcript = ear.transcribe(raw_pcm)
        except Exception as e:
            print(f"Voice recognition failed: {e}")
            self._send_json(500, {"error": "Voice recognition failed"})
            return

        self._send_json(200, {"transcript": transcript})

    def log_message(self, format, *args):
        if getattr(config, "VOICE_API_LOG_REQUESTS", False):
            super().log_message(format, *args)


def create_voice_api_server(host=None, port=None, ear=None):
    global _ear
    host = host or config.VOICE_API_HOST
    port = port or config.VOICE_API_PORT
    using_shared_ear = ear is not None
    if ear is None:
        print("👂 Initializing voice recognition for API...")
        try:
            from modules.ears import Ear
            ear = Ear()
        except Exception as e:
            print(f"❌ Voice recognition init error: {e}")
            ear = None
    _ear = ear
    server = ThreadingHTTPServer((host, port), _VoiceRequestHandler)
    print(f"🌐 Voice API listening on http://{host}:{port} (shared_ear={using_shared_ear})")
    return server


def run_voice_api_server(host=None, port=None, ear=None):
    server = create_voice_api_server(host=host, port=port, ear=ear)
    server.serve_forever()
