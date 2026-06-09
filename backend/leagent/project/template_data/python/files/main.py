"""Lightweight dev server for the Python project scaffold.

Serves a status page at ``/`` and a ``/health`` endpoint for the
supervisor readiness check.  The real project logic lives in ``src/``.

Run directly::

    python main.py --port 8000

Or let the LeAgent supervisor manage the lifecycle automatically.
"""

from __future__ import annotations

import argparse
import json
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from importlib import import_module


class Handler(SimpleHTTPRequestHandler):
    """Minimal request handler with a JSON health endpoint."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json_response({"ok": True, "status": "ready"})
        elif self.path == "/":
            self._serve_index()
        else:
            super().do_GET()

    def _json_response(self, body: dict, *, status: int = 200) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _serve_index(self) -> None:
        try:
            mod = import_module("src")
            project_info = getattr(mod, "__doc__", "") or "Python project"
        except Exception:
            project_info = "Python project"

        html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Python Project</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: system-ui, -apple-system, sans-serif;
           background: #f8fafc; color: #1e293b; padding: 2rem; }}
    .container {{ max-width: 640px; margin: 0 auto; }}
    h1 {{ font-size: 1.5rem; margin-bottom: .5rem; }}
    .badge {{ display: inline-block; padding: .15rem .5rem; border-radius: .25rem;
              background: #dbeafe; color: #1e40af; font-size: .75rem; font-weight: 600; }}
    p {{ margin-top: 1rem; line-height: 1.6; color: #475569; }}
    pre {{ margin-top: 1.5rem; background: #1e293b; color: #e2e8f0; padding: 1rem;
           border-radius: .5rem; overflow-x: auto; font-size: .85rem; }}
    .muted {{ color: #94a3b8; font-size: .85rem; margin-top: 1.5rem; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Python Project <span class="badge">running</span></h1>
    <p>{project_info}</p>
    <pre>python main.py --port {self.server.server_port}</pre>
    <p class="muted">
      Edit files in <code>src/</code> and run tests with <code>pytest</code>.
      This page is served by the built-in dev server in <code>main.py</code>.
    </p>
  </div>
</body>
</html>"""
        payload = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Dev server for the Python project scaffold")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), Handler)
    print(f"Serving on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
