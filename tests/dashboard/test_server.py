import json
import urllib.request
from threading import Thread

from agent_usage.dashboard.server import make_server


def _get(url: str) -> tuple[int, bytes, str]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, resp.read(), resp.headers.get("Content-Type", "")


def test_server_serves_index_and_injects_data_json(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>dash</title>", encoding="utf-8")

    data = {"window": {"start": "2026-07-10", "end": "2026-07-11"}, "tokens": []}
    server = make_server(data, dist_dir=dist, port=0)
    host, port = server.server_address
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        status, body, _ = _get(f"{base}/index.html")
        assert status == 200
        assert b"dash" in body

        status, body, ctype = _get(f"{base}/data.json")
        assert status == 200
        assert ctype.startswith("application/json")
        assert json.loads(body) == data
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_server_binds_loopback_only(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("x", encoding="utf-8")
    server = make_server({}, dist_dir=dist, port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()
