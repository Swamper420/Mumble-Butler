import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
from modules.brain import Brain

_brain = None


class _LLMRequestHandler(BaseHTTPRequestHandler):
    server_version = "MumbleButlerLLM/1.0"

    def _send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        brain = _brain
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "llm_loaded": bool(brain and brain.llm is not None)})
            return
        self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path != "/query":
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

        prompt = data.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            self._send_json(400, {"error": "Field 'prompt' must be a non-empty string"})
            return

        max_tokens = data.get("max_tokens", config.LLM_API_DEFAULT_MAX_TOKENS)
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            self._send_json(400, {"error": "Field 'max_tokens' must be a positive integer"})
            return

        brain = _brain
        if brain is None or brain.llm is None:
            self._send_json(503, {"error": "LLM is not loaded"})
            return

        try:
            # Brain.generate_response uses an internal lock, so this call is safe under ThreadingHTTPServer.
            response = brain.generate_response(prompt.strip(), max_tokens=max_tokens)
        except Exception as e:
            print(f"LLM processing failed: {e}")
            self._send_json(500, {"error": "LLM processing failed"})
            return
        self._send_json(200, {"response": response})

    def log_message(self, format, *args):
        if getattr(config, "LLM_API_LOG_REQUESTS", False):
            super().log_message(format, *args)


def run_llm_api_server(host=None, port=None):
    global _brain
    host = host or config.LLM_API_HOST
    port = port or config.LLM_API_PORT
    print("🧠 Initializing LLM for API...")
    _brain = Brain()
    server = ThreadingHTTPServer((host, port), _LLMRequestHandler)
    print(f"🌐 LLM API listening on http://{host}:{port}")
    server.serve_forever()
