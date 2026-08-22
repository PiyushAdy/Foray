"""CLI entry point: `foray start`.

Spins up the local web server and opens the UI in the default browser.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser


def _find_free_port(preferred: int) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return sock.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("no available port")


def _open_browser_later(url: str, delay: float = 1.2) -> None:
    def _open() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="foray",
        description="Foray: the local intelligence layer for your codebase.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=7420, help="bind port (default 7420)")
    parser.add_argument("--no-browser", action="store_true", help="do not auto-open the browser")
    parser.add_argument("--demo", action="store_true", help="read-only hosted showcase mode")
    parser.add_argument("--demo-repos", default="", help="path to demo_repos.yaml override")
    args = parser.parse_args(argv)

    if args.demo:
        os.environ["FORAY_DEMO"] = "1"
    if args.demo_repos:
        os.environ["FORAY_DEMO_REPOS"] = args.demo_repos

    import uvicorn

    port = _find_free_port(args.port)
    if port != args.port:
        print(f"port {args.port} busy, using {port}", file=sys.stderr)

    url = f"http://{args.host if args.host != '0.0.0.0' else 'localhost'}:{port}"
    print(f"Foray listening on {url}")

    if not args.no_browser:
        _open_browser_later(url)

    uvicorn.run(
        "foray.main:app",
        host=args.host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
