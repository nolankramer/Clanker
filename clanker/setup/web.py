"""Web-based setup wizard — lightweight HTTP server with REST API.

Serves a single-page wizard UI and exposes JSON endpoints for connection
testing, entity discovery, and config generation.  No external web
framework required — uses Python's stdlib ``http.server``.

Usage::

    clanker-setup --web          # default port 8471
    clanker-setup --web --port 9000
"""

from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from clanker.setup.wizard import (
    discover_entities,
    generate_config,
    generate_env,
    infer_rooms,
    save_config,
    test_anthropic,
    test_frigate,
    test_ha,
    test_ollama,
    test_openai,
)

_STATIC_DIR = Path(__file__).parent / "static"


class _Handler(BaseHTTPRequestHandler):
    """HTTP request handler for the setup wizard."""

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default stderr logging."""

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._serve_file("index.html", "text/html")
        elif self.path == "/api/health":
            self._json_response({"ok": True})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        body = self._read_body()
        routes: dict[str, Any] = {
            "/api/test/ha": self._handle_test_ha,
            "/api/test/anthropic": self._handle_test_anthropic,
            "/api/test/openai": self._handle_test_openai,
            "/api/test/ollama": self._handle_test_ollama,
            "/api/test/frigate": self._handle_test_frigate,
            "/api/discover": self._handle_discover,
            "/api/voice/install-component": self._handle_install_component,
            "/api/discover/ha": self._handle_discover_ha,
            "/api/deploy/test-ssh": self._handle_test_ssh,
            "/api/deploy/ssh": self._handle_deploy_ssh,
            "/api/config/save": self._handle_save,
        }
        handler = routes.get(self.path)
        if handler:
            handler(body)
        else:
            self.send_error(404)

    # ------------------------------------------------------------------
    # API handlers
    # ------------------------------------------------------------------

    def _handle_test_ha(self, body: dict[str, Any]) -> None:
        result = test_ha(body.get("url", ""), body.get("token", ""))
        self._json_response(result)

    def _handle_test_anthropic(self, body: dict[str, Any]) -> None:
        result = test_anthropic(body.get("api_key", ""))
        self._json_response(result)

    def _handle_test_openai(self, body: dict[str, Any]) -> None:
        result = test_openai(body.get("api_key", ""), body.get("base_url"))
        self._json_response(result)

    def _handle_test_ollama(self, body: dict[str, Any]) -> None:
        result = test_ollama(body.get("base_url", "http://localhost:11434"))
        self._json_response(result)

    def _handle_test_frigate(self, body: dict[str, Any]) -> None:
        result = test_frigate(body.get("url", ""))
        self._json_response(result)

    def _handle_discover(self, body: dict[str, Any]) -> None:
        url = body.get("url", "")
        token = body.get("token", "")
        entities = discover_entities(url, token)
        rooms = infer_rooms(entities)
        self._json_response({"entities": entities, "rooms": rooms})

    def _handle_discover_ha(self, body: dict[str, Any]) -> None:
        from clanker.setup.discovery import discover_ha

        scan = body.get("scan_subnet", False)
        results = discover_ha(scan_subnet=scan, timeout=body.get("timeout", 3.0))
        self._json_response({"instances": results})

    def _handle_test_ssh(self, body: dict[str, Any]) -> None:
        from clanker.setup.remote import test_ssh

        result = test_ssh(body.get("host", ""))
        self._json_response(result)

    def _handle_deploy_ssh(self, body: dict[str, Any]) -> None:
        from clanker.setup.remote import deploy_docker

        result = deploy_docker(
            body.get("host", ""),
            ha_config_path=body.get("ha_config_path", "/config"),
            install_dir=body.get("install_dir", "/opt/clanker"),
        )
        self._json_response(result)

    def _handle_install_component(self, body: dict[str, Any]) -> None:
        from clanker.setup.voice import add_clanker_to_ha_config, install_ha_component

        ha_dir = body.get("ha_config_dir", "/config")
        result = install_ha_component(ha_dir)
        if result["ok"]:
            clanker_url = body.get("clanker_url", "http://localhost:8472")
            cfg_result = add_clanker_to_ha_config(ha_dir, clanker_url)
            result["config_message"] = cfg_result["message"]
        self._json_response(result)

    def _handle_save(self, body: dict[str, Any]) -> None:
        answers = body.get("answers", {})
        yaml_content = generate_config(answers)
        env_content = generate_env(answers)
        try:
            paths = save_config(yaml_content, env_content)
            self._json_response({"ok": True, "paths": paths})
        except Exception as exc:
            self._json_response({"ok": False, "message": str(exc)})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            return {}

    def _json_response(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _serve_file(self, filename: str, content_type: str) -> None:
        filepath = _STATIC_DIR / filename
        if not filepath.exists():
            self.send_error(404, f"File not found: {filename}")
            return
        data = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_server(port: int = 8471) -> None:
    """Start the setup wizard web server and open a browser."""
    server = HTTPServer(("127.0.0.1", port), _Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Clanker setup wizard running at {url}")
    print("Press Ctrl+C to stop.\n")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
