"""Command line: `fieldguide build` and `fieldguide serve`."""

from __future__ import annotations

import argparse
import functools
import http.server
import socket
import sys
import threading
from pathlib import Path

DEFAULT_PORT = 8101


def _kb(n: int) -> str:
    return f"{n / 1024:,.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:,.2f} MB"


def cmd_build(args: argparse.Namespace) -> int:
    from .site import build_site

    stats = build_site(Path(args.pdf), Path(args.out), page_images=args.page_images, title=args.title,
                       source_url=args.source_url)
    print(f"Read {stats.pages} pages from {Path(args.pdf).name}")
    print(f"Sections:        {stats.sections}")
    print(f"Index terms:     {stats.terms:,}")
    print(f"sections.json:   {_kb(stats.sections_bytes)}")
    print(f"index.json:      {_kb(stats.index_bytes)}")
    if args.page_images:
        print(f"Page images:     {_kb(stats.images_bytes)}")
    print(f"Total download:  {_kb(stats.total_bytes)} in {stats.files} files")
    print(f"Wrote {args.out}")
    return 0


class _Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".webmanifest": "application/manifest+json",
        ".js": "text/javascript",
        ".json": "application/json",
        ".svg": "image/svg+xml",
    }

    def end_headers(self) -> None:
        # The service worker decides what is fresh; the browser cache should not.
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:  # quieter log
        sys.stderr.write("%s\n" % (fmt % args))


def cmd_serve(args: argparse.Namespace) -> int:
    root = Path(args.dir)
    if not (root / "index.html").exists():
        print(f"{root} has no index.html; run `fieldguide build` first", file=sys.stderr)
        return 1
    handler = functools.partial(_Handler, directory=str(root))
    servers = [http.server.ThreadingHTTPServer((args.host, args.port), handler)]
    if args.host == "127.0.0.1" and socket.has_ipv6:
        # Browsers try "localhost" as ::1 first. Without an IPv6 listener every
        # request waits for that attempt to fail, which makes caching slow.
        try:
            servers.append(_IPv6Server(("::1", args.port), handler))
        except OSError:
            pass
    for extra in servers[1:]:
        threading.Thread(target=extra.serve_forever, daemon=True).start()
    host = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
    print(f"Serving {root} at http://{host}:{args.port}/", flush=True)
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for s in servers:
            s.server_close()
    return 0


class _IPv6Server(http.server.ThreadingHTTPServer):
    address_family = socket.AF_INET6


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fieldguide", description="Turn a PDF manual into an offline search app.")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="extract a PDF and write the web app")
    b.add_argument("pdf")
    b.add_argument("--out", default="site")
    b.add_argument("--page-images", action="store_true", help="include a low-resolution image of every page")
    b.add_argument("--title", help="guide title (default: the PDF's own title)")
    b.add_argument("--source-url", help="where the original PDF can be downloaded")
    b.set_defaults(func=cmd_build)
    s = sub.add_parser("serve", help="serve the built site")
    s.add_argument("dir", nargs="?", default="site")
    s.add_argument("--port", type=int, default=DEFAULT_PORT)
    s.add_argument("--host", default="127.0.0.1")
    s.set_defaults(func=cmd_serve)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
