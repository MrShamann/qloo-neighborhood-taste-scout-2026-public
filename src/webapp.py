"""Original loopback-only Qloo Agentic contest browser demo.

All three selectable scenes are invented. A real provider path is explicitly
gated and cannot silently downgrade to mock.
"""
from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .taste_scout import GuardError, live_flow, offline_flow, valid_input
from .taste_bridge import bridge_catalogue, live_bridge, offline_bridge

ROOT = Path(__file__).resolve().parents[1]
SCENES = ROOT / "fixtures" / "scenarios.json"
MEDIA = {
    "/": (ROOT / "web" / "index.html", "text/html; charset=utf-8"),
    "/styles.css": (ROOT / "web" / "styles.css", "text/css; charset=utf-8"),
    "/app.js": (ROOT / "web" / "app.js", "text/javascript; charset=utf-8"),
}
MAX_POST = 256
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; "
       "connect-src 'self'; img-src 'self'; base-uri 'none'; "
       "form-action 'none'; frame-ancestors 'none'; object-src 'none'")


def select_scene(scene_id: str) -> dict:
    if type(scene_id) is not str or len(scene_id) > 40:
        raise GuardError("unknown predefined synthetic scene")
    catalogue = json.loads(SCENES.read_text())
    for item in catalogue["scenes"]:
        if item["id"] == scene_id:
            return item
    raise GuardError("unknown predefined synthetic scene")


def scene_request(scene: dict) -> dict:
    return valid_input({"mode": "synthetic_group", "interest_artist": scene["artist"],
                        "city": scene["city"], "limit": scene["limit"]})


def catalogue() -> list[dict]:
    raw = json.loads(SCENES.read_text())
    return [{k: item[k] for k in ("id", "name", "deck", "city", "artist", "visual", "mission")}
            for item in raw["scenes"]]


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "QlooTasteScoutLocal/1.0"
    sys_version = ""

    def log_message(self, *args):
        # No profile/request content or upstream response in server logs.
        return

    def _send(self, status: int, content: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        self.wfile.write(content)

    def _json(self, status: int, obj: dict):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _allowed_host(self):
        port = self.server.server_port
        return self.headers.get("Host", "") in (f"localhost:{port}", f"127.0.0.1:{port}")

    def _allowed_origin(self, origin: str) -> bool:
        port = self.server.server_port
        return origin in ("", f"http://localhost:{port}",
                          f"http://127.0.0.1:{port}")

    def _provider_ready(self) -> bool:
        return bool(os.environ.get("QLOO_API_KEY") and
                    os.environ.get("QLOO_EVENT_QUOTA_APPROVED")=="YES")

    def _allow_live(self) -> bool:
        # Local sponsor mode still checks the real quota gate in live_bridge.
        return True

    def do_GET(self):
        if not self._allowed_host():
            self._json(403, {"error":"INVALID_LOOPBACK_HOST"})
            return
        url = urlsplit(self.path)
        if url.scheme or url.netloc or len(self.path)>2048:
            self._json(400, {"error":"INVALID_URL"})
            return
        # A chat-opened local page can append ?utm_source=chatgpt.com.
        # Permit static URL queries; never permit API query parameters.
        if url.path.startswith("/api/") and url.query:
            self._json(400, {"error":"API_QUERY_NOT_ALLOWED"})
            return
        if url.path == "/api/bridges":
            self._json(200,{
                "bridges":bridge_catalogue(),
                "source":"ORIGINAL CURATED TWO-ARTIST DEMO",
                "provider_ready":self._provider_ready(),
                "event_key_exposed":False,
                "live_call_count":0,
            })
            return
        if url.path == "/api/scenes":
            self._json(200, {
                "scenes": catalogue(),
                "source": "INDEPENDENT SYNTHETIC DEMO",
                "provider_ready": self._provider_ready(),
                "sponsor_api": "Qloo Taste AI",
                "live_call_count": 0,
            })
            return
        if url.path not in MEDIA:
            self._json(404, {"error":"NOT_FOUND"})
            return
        f, ctype = MEDIA[url.path]
        self._send(200, f.read_bytes(), ctype)

    def do_POST(self):
        if not self._allowed_host():
            self._json(403, {"error":"INVALID_LOOPBACK_HOST"})
            return
        if urlsplit(self.path).path not in {"/api/execute","/api/bridge"} or urlsplit(self.path).query:
            self._json(404, {"error":"NOT_FOUND"})
            return
        origin = self.headers.get("Origin", "")
        if not self._allowed_origin(origin):
            self._json(403, {"error":"CROSS_ORIGIN_DENIED"})
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            self._json(415, {"error":"JSON_CONTENT_TYPE_REQUIRED"})
            return
        length = self.headers.get("Content-Length", "")
        if not length.isascii() or not length.isdecimal() or not (1 <= int(length) <= MAX_POST):
            self._json(413, {"error":"REQUEST_TOO_LARGE_OR_MISSING"})
            return
        try:
            value = json.loads(self.rfile.read(int(length)))
            if type(value) is not dict:
                raise GuardError("unexpected request shape")
            if self.path=="/api/bridge":
                if set(value)!={"bridge_id","mode"}:
                    raise GuardError("unexpected dual-taste request fields")
                if value["mode"]=="mock":
                    out=offline_bridge(value["bridge_id"])
                elif value["mode"]=="live":
                    if not self._allow_live():
                        raise GuardError("hosted live provider calls are not cleared")
                    out=live_bridge(value["bridge_id"])
                else:
                    raise GuardError("unsupported bridge mode")
                self._json(200,out)
                return
            if set(value)!={"scene_id","mode"}:
                raise GuardError("unexpected single-taste request fields")
            scene = select_scene(value["scene_id"])
            brief = scene_request(scene)
            if value["mode"] == "mock":
                result = offline_flow(brief, scene["replay"])
            elif value["mode"] == "live":
                if not self._allow_live():
                    raise GuardError("hosted live provider calls are not cleared")
                result = live_flow(brief)
            else:
                raise GuardError("only mock or explicitly gated live mode allowed")
            # Never reuse client-submitted PII, location or user prompt.
            result["scene_id"] = scene["id"]
            result["brief"] = {"city":scene["city"], "interest_artist":scene["artist"],
                               "mission":scene["mission"]}
            self._json(200, result)
        except (GuardError, ValueError, TypeError, KeyError):
            self._json(422, {"error":"VALIDATION_OR_PROVIDER_GATE_BLOCKED"})

    def do_OPTIONS(self):
        self._json(405, {"error":"CORS_DISABLED"})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8879)
    args = p.parse_args()
    if not (1024 <= args.port <= 65535):
        p.error("Port must be between 1024 and 65535")
    with ThreadingHTTPServer(("127.0.0.1", args.port), DemoHandler) as server:
        print(f"QLOO_SYNTHETIC_DEMO=http://127.0.0.1:{args.port}/", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
