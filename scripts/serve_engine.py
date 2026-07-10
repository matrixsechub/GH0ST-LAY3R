"""
Ghost Layer Studio — Local Engine HTTP Service Entrypoint

# ADVANCEMENT: Local HTTP adapter
Starts the stdlib-only local HTTP adapter for ecosystem callers.

Run:  python -m scripts.serve_engine
"""

from __future__ import annotations
import argparse

from integrations.http_service import run_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Ghost Layer local HTTP service")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
