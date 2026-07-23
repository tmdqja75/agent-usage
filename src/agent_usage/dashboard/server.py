"""Serve the interactive dashboard on localhost: committed dist/ plus injected data.json."""

from __future__ import annotations

import json
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, data_bytes: bytes, dist_dir: Path, **kwargs) -> None:
        self._data_bytes = data_bytes
        super().__init__(*args, directory=str(dist_dir), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if self.path.split("?", 1)[0] == "/data.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(self._data_bytes)))
            self.end_headers()
            self.wfile.write(self._data_bytes)
            return
        super().do_GET()

    def send_head(self):  # SPA fallback: unknown path -> index.html
        path = self.translate_path(self.path)
        if not Path(path).exists() and "." not in Path(self.path).name:
            self.path = "/index.html"
        return super().send_head()

    def log_message(self, *args) -> None:  # keep the console quiet
        pass


def make_server(
    data: dict, *, dist_dir: Path, host: str = "127.0.0.1", port: int = 8000
) -> ThreadingHTTPServer:
    """Build (but do not start) the localhost dashboard server."""
    handler = partial(
        _DashboardHandler,
        data_bytes=json.dumps(data).encode("utf-8"),
        dist_dir=dist_dir,
    )
    return ThreadingHTTPServer((host, port), handler)


def serve(
    data: dict,
    *,
    dist_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = True,
) -> None:
    """Serve the dashboard until interrupted (Ctrl-C)."""
    server = make_server(data, dist_dir=dist_dir, host=host, port=port)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}"
    print(f"agent-usage: dashboard serving at {url} (Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
