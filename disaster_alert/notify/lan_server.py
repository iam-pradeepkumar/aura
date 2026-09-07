"""Lightweight HTTP server showing active disaster alerts on the LAN."""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

logger = logging.getLogger(__name__)

AlertProvider = Callable[[], list[dict[str, Any]]]


class _AlertHandler(BaseHTTPRequestHandler):
    server_version = "DisasterAlert/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("LAN server: %s", format % args)

    def do_GET(self) -> None:
        provider: AlertProvider = getattr(self.server, "alert_provider", lambda: [])
        status_fn: Callable[[], dict[str, Any]] = getattr(
            self.server, "status_provider", lambda: {}
        )
        if self.path in ("/", "/alerts"):
            alerts = provider()
            status = status_fn()
            html = _render_page(alerts, status)
            self._respond(200, html, "text/html; charset=utf-8")
        elif self.path == "/api/alerts":
            body = json.dumps({"alerts": provider()})
            self._respond(200, body, "application/json")
        else:
            self._respond(404, "Not found", "text/plain")

    def _respond(self, code: int, body: str, content_type: str) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _render_page(alerts: list[dict[str, Any]], status: dict[str, Any]) -> str:
    rows = ""
    for a in alerts:
        rows += (
            f"<tr><td>{a.get('severity','')}</td>"
            f"<td>{a.get('title','')}</td>"
            f"<td>{a.get('message','')}</td>"
            f"<td>{a.get('timestamp','')}</td></tr>"
        )
    if not rows:
        rows = "<tr><td colspan='4'>No active alerts</td></tr>"
    loc = (status.get("location") or {}).get("name", "monitoring site")
    last_poll = status.get("last_poll") or "never"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Disaster Alerts</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #0f1419; color: #e8eaed; }}
h1 {{ color: #f4b400; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #333; padding: 0.5rem; text-align: left; }}
th {{ background: #1a2332; }}
.meta {{ color: #9aa0a6; margin-bottom: 1rem; }}
</style></head><body>
<h1>Disaster Alert Monitor</h1>
<p class="meta">Location: {loc} &mdash; Last poll: {last_poll}</p>
<table>
<thead><tr><th>Severity</th><th>Title</th><th>Message</th><th>Time (UTC)</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<p class="meta">Single-node mode: laptop engine is primary poller.</p>
</body></html>"""


class LanAlertServer:
    """Serve alert status page on a local HTTP port (default 8765)."""

    def __init__(
        self,
        port: int = 8765,
        alert_provider: AlertProvider | None = None,
        status_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._port = port
        self._alert_provider = alert_provider or (lambda: [])
        self._status_provider = status_provider or (lambda: {})
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server:
            return
        self._server = ThreadingHTTPServer(("0.0.0.0", self._port), _AlertHandler)
        self._server.alert_provider = self._alert_provider
        self._server.status_provider = self._status_provider
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("LAN alert server listening on port %d", self._port)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None
        self._thread = None
