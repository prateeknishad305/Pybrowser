from __future__ import annotations

import argparse

from pybroswer.server import serve


def main() -> None:
    parser = argparse.ArgumentParser(prog="pybroswer", description="Local Chromium REST for PyDroid")
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve_p = sub.add_parser("serve", help="Start Chromium on this PC and expose REST for phones")
    serve_p.add_argument("--host", default="0.0.0.0")
    serve_p.add_argument("--port", type=int, default=5173)
    serve_p.add_argument("--headed", action="store_true", help="Show the browser window")

    args = parser.parse_args()
    if args.cmd == "serve":
        serve(host=args.host, port=args.port, headless=not args.headed)


if __name__ == "__main__":
    main()
