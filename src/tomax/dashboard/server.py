"""Serve the interactive dashboard on localhost: committed dist/ plus injected data.json."""

from __future__ import annotations

import json
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _inject_lang(html: str, lang: str) -> str:
    """Set <html lang="..."> (best-effort) and inject a window.__LANG__ script.

    The script runs before the deferred module bundle, so the React app can
    read window.__LANG__ synchronously at startup.
    """
    if 'lang="en"' in html:
        html = html.replace('lang="en"', f'lang="{lang}"', 1)
    script = f"<script>window.__LANG__={json.dumps(lang)};</script>"
    tag_start = html.find("<html")
    if tag_start == -1:
        return script + html
    tag_end = html.find(">", tag_start)
    if tag_end == -1:
        return script + html
    return html[: tag_end + 1] + script + html[tag_end + 1 :]


class _DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, data_bytes: bytes, html_bytes: bytes, dist_dir: Path, **kwargs) -> None:
        self._data_bytes = data_bytes
        self._html_bytes = html_bytes
        super().__init__(*args, directory=str(dist_dir), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        path = self.path.split("?", 1)[0]
        if path == "/data.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(self._data_bytes)))
            self.end_headers()
            self.wfile.write(self._data_bytes)
            return
        # Serve the lang-injected index.html for "/", "/index.html", and any
        # unknown client-side route (SPA fallback).
        translated = Path(self.translate_path(self.path))
        if path in ("/", "/index.html") or (not translated.exists() and "." not in Path(path).name):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(self._html_bytes)))
            self.end_headers()
            self.wfile.write(self._html_bytes)
            return
        super().do_GET()

    def log_message(self, *args) -> None:  # keep the console quiet
        pass


def make_server(
    data: dict,
    *,
    dist_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    lang: str = "en",
) -> ThreadingHTTPServer:
    """Build (but do not start) the localhost dashboard server."""
    html_text = (dist_dir / "index.html").read_text(encoding="utf-8")
    handler = partial(
        _DashboardHandler,
        data_bytes=json.dumps(data).encode("utf-8"),
        html_bytes=_inject_lang(html_text, lang).encode("utf-8"),
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
    lang: str = "en",
) -> None:
    """Serve the dashboard until interrupted (Ctrl-C)."""
    server = make_server(data, dist_dir=dist_dir, host=host, port=port, lang=lang)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}"
    print(f"tomax: dashboard serving at {url} (Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
