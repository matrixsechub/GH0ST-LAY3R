"""
Ghost Layer Studio — Local HTTP Service Adapter

# ADVANCEMENT: Local HTTP adapter
Stdlib-only local HTTP server exposing Ghost Layer ecosystem contracts on
localhost. No auth, no external network calls, no stack trace exposure.
"""

from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Tuple, Type
from urllib.parse import urlparse

from core.commands import ALLOWED_CATEGORIES, parse_command
from core.contracts import (
    ECOSYSTEM_REQUEST_VERSION,
    ECOSYSTEM_RESPONSE_VERSION,
    ENGINE_CONTRACT_VERSION,
    normalize_ecosystem_request,
    validate_ecosystem_request,
)
from core.engine import GhostLayerEngine, create_default_engine
from core.types import ENGINE_VERSION
from integrations.ecosystem import run_ecosystem_request

SERVICE_NAME = "ghost-layer-local"

_ROUTES = (
    ("GET", "/health"),
    ("GET", "/contracts"),
    ("POST", "/run"),
    ("POST", "/run-diagnostics"),
    ("POST", "/validate-request"),
    ("POST", "/validate-command"),
)


def create_handler(engine: Optional[GhostLayerEngine] = None) -> Type[BaseHTTPRequestHandler]:
    """
    Return an HTTP request handler class bound to a shared engine instance.

    Creates the default engine once when *engine* is None so repeated requests
    do not recreate the pipeline unnecessarily.
    """
    shared_engine = engine if engine is not None else create_default_engine()

    class GhostLayerHTTPRequestHandler(BaseHTTPRequestHandler):
        """Local-only HTTP handler for Ghost Layer ecosystem endpoints."""

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
            content_length = self.headers.get("Content-Length")
            if content_length is None:
                return None, "missing Content-Length header"
            try:
                length = int(content_length)
            except ValueError:
                return None, "invalid Content-Length header"
            if length <= 0:
                return None, "empty request body"
            raw = self.rfile.read(length)
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None, "malformed JSON body"
            if not isinstance(parsed, dict):
                return None, "request body must be a JSON object"
            return parsed, None

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/health":
                self._handle_health()
                return
            if path == "/contracts":
                self._handle_contracts()
                return
            self._send_json(404, {"status": "error", "error": "not found", "path": path})

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            handlers = {
                "/run": self._handle_run,
                "/run-diagnostics": self._handle_run_diagnostics,
                "/validate-request": self._handle_validate_request,
                "/validate-command": self._handle_validate_command,
            }
            handler = handlers.get(path)
            if handler is None:
                self._send_json(404, {"status": "error", "error": "not found", "path": path})
                return
            handler()

        def do_PUT(self) -> None:
            self._method_not_allowed()

        def do_DELETE(self) -> None:
            self._method_not_allowed()

        def do_PATCH(self) -> None:
            self._method_not_allowed()

        def _method_not_allowed(self) -> None:
            self._send_json(405, {"status": "error", "error": "method not allowed"})

        def _handle_health(self) -> None:
            self._send_json(
                200,
                {
                    "status": "ok",
                    "service": SERVICE_NAME,
                    "engine_version": ENGINE_VERSION,
                    "contract_version": ECOSYSTEM_RESPONSE_VERSION,
                },
            )

        def _handle_contracts(self) -> None:
            self._send_json(
                200,
                {
                    "status": "ok",
                    "engine_contract_version": ENGINE_CONTRACT_VERSION,
                    "ecosystem_request_version": ECOSYSTEM_REQUEST_VERSION,
                    "ecosystem_response_version": ECOSYSTEM_RESPONSE_VERSION,
                    "supported_commands": sorted(ALLOWED_CATEGORIES),
                },
            )

        def _handle_run(self) -> None:
            body, error = self._read_json_body()
            if error is not None:
                self._send_json(400, {"status": "error", "error": error})
                return
            request = dict(body)
            options = request.get("options")
            if not isinstance(options, dict):
                options = {}
                request["options"] = options
            if "include_diagnostics" not in options:
                options["include_diagnostics"] = False
            response = run_ecosystem_request(request, engine=shared_engine)
            self._send_json(200, response)

        def _handle_run_diagnostics(self) -> None:
            body, error = self._read_json_body()
            if error is not None:
                self._send_json(400, {"status": "error", "error": error})
                return
            request = dict(body)
            options = request.get("options")
            if not isinstance(options, dict):
                options = {}
            options["include_diagnostics"] = True
            request["options"] = options
            response = run_ecosystem_request(request, engine=shared_engine)
            self._send_json(200, response)

        def _handle_validate_request(self) -> None:
            body, error = self._read_json_body()
            if error is not None:
                self._send_json(400, {"status": "error", "error": error})
                return
            normalized = normalize_ecosystem_request(body)
            request_validation = validate_ecosystem_request(normalized)
            command = normalized.get("command", "")
            command_validation = (
                parse_command(command)
                if isinstance(command, str)
                else parse_command("")
            )
            ok = request_validation["ok"] and command_validation["ok"]
            result = {
                "ok": ok,
                "request_validation": request_validation,
                "command_validation": command_validation,
            }
            if not ok:
                errors = list(request_validation.get("errors", []))
                if not command_validation["ok"] and command_validation.get("error"):
                    errors.append(command_validation["error"])
                result["errors"] = errors
                self._send_json(400, result)
                return
            self._send_json(200, result)

        def _handle_validate_command(self) -> None:
            body, error = self._read_json_body()
            if error is not None:
                self._send_json(400, {"status": "error", "error": error})
                return
            command = body.get("command", "")
            if not isinstance(command, str):
                self._send_json(
                    400,
                    {"status": "error", "error": "field 'command' must be a string"},
                )
                return
            result = parse_command(command)
            if not result["ok"]:
                self._send_json(400, result)
                return
            self._send_json(200, result)

    return GhostLayerHTTPRequestHandler


def run_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    engine: Optional[GhostLayerEngine] = None,
) -> None:
    """Start the local Ghost Layer HTTP service (blocks until interrupted)."""
    handler = create_handler(engine)
    server = HTTPServer((host, port), handler)
    print(f"Ghost Layer local service listening on http://{host}:{port}")
    print("Routes:")
    for method, route in _ROUTES:
        print(f"  - {method} {route}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Ghost Layer local service.")
    finally:
        server.server_close()
