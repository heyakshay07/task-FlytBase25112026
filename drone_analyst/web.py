"""Small HTTP service for deploying the analyst on Render or another host."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .agent import SecurityAnalystAgent
from .indexer import FrameIndex
from .simulator import read_feed


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Drone Security Analyst</title>
<style>body{font:16px system-ui;max-width:760px;margin:40px auto;padding:0 16px}textarea{width:100%;height:80px}button{margin-top:10px;padding:8px 18px}pre{white-space:pre-wrap;background:#f4f4f4;padding:14px}</style></head>
<body><h1>Drone Security Analyst</h1>
<p>Ask a question about the indexed video.</p>
<textarea id="q" placeholder="What objects were in the video?"></textarea><br>
<button onclick="ask()">Ask</button><pre id="answer"></pre>
<script>async function ask(){const q=document.getElementById('q').value;const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});const d=await r.json();document.getElementById('answer').textContent=d.answer||d.error||'No answer';}</script>
</body></html>"""


def load_agent() -> SecurityAnalystAgent:
    db_path = os.getenv("DRONE_DB", "output/13261636_analysis.db")
    feed_path = os.getenv("DRONE_FEED", "data/13261636_feed.jsonl")
    index = FrameIndex(db_path)
    agent = SecurityAnalystAgent(index)
    if index.stats()["frames"] == 0 and Path(feed_path).is_file():
        agent.ingest_many(read_feed(feed_path))
    return agent


def serve(host: str = "0.0.0.0", port: int | None = None) -> None:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, content_type: str, body: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send(200, "application/json", json.dumps({"status": "ok"}))
                return
            if parsed.path == "/ask":
                question = parse_qs(parsed.query).get("q", [""])[0].strip()
                self._answer(question)
                return
            if parsed.path == "/":
                self._send(200, "text/html; charset=utf-8", PAGE)
                return
            self._send(404, "application/json", json.dumps({"error": "not found"}))

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/ask":
                self._send(404, "application/json", json.dumps({"error": "not found"}))
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(length) or b"{}")
                question = str(data.get("question", "")).strip()
            except (ValueError, json.JSONDecodeError):
                self._send(400, "application/json", json.dumps({"error": "invalid JSON"}))
                return
            self._answer(question)

        def _answer(self, question: str) -> None:
            if not question:
                self._send(400, "application/json", json.dumps({"error": "question is required"}))
                return
            try:
                agent = load_agent()
                result = agent.ask(question)
                self._send(200, "application/json", json.dumps({"answer": result.text}))
            except Exception as exc:
                self._send(500, "application/json", json.dumps({"error": str(exc)}))

        def log_message(self, format: str, *args) -> None:
            return

    listen_port = port or int(os.getenv("PORT", "8000"))
    print(f"Drone analyst listening on {host}:{listen_port}", flush=True)
    ThreadingHTTPServer((host, listen_port), Handler).serve_forever()


if __name__ == "__main__":
    serve()
