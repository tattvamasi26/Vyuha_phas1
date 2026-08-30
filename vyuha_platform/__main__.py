"""Run the platform: ``.venv/Scripts/python -m vyuha_platform``."""

from __future__ import annotations

import argparse
import webbrowser

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser(prog="vyuha_platform", description="Vyuha Operations Platform")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--open", action="store_true", help="open a browser once it is up")
    ap.add_argument("--reload", action="store_true", help="auto-reload on code change")
    ap.add_argument("command", nargs="?", default="serve", choices=["serve", "seed"],
                    help="'seed' rebuilds the demo workspace, then exits")
    args = ap.parse_args()

    if args.command == "seed":
        from .demo_seed import main as seed
        seed()
        return

    url = f"http://{args.host}:{args.port}"
    print(f"\n  Vyuha Operations Platform  ->  {url}\n  Ctrl-C to stop.\n")
    if args.open:
        webbrowser.open(url)
    uvicorn.run("vyuha_platform.app:app", host=args.host, port=args.port,
                reload=args.reload, log_level="info")


if __name__ == "__main__":
    main()
