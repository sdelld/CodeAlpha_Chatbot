"""Nova Electronics chatbot server.

POST /api/chat/stream   {"message", "session_id"?} -> text/event-stream (meta, token, tool, products, suggestions, replace, done)
POST /api/chat          same input -> JSON (non-streaming)
POST /api/feedback      {"id", "helpful": bool}
GET  /api/stats         usage, latency, tokens, cost, tools, fallbacks
GET  /healthz
"""

import json
import logging
import os
import threading
import time
from collections import defaultdict, deque

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from nova.assistant import Assistant
from nova.config import settings

RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MIN", "30"))
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app(assistant=None):
    app = Flask(__name__)
    app.config["ALLOWED_ORIGINS"] = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",")]
    app.assistant = assistant or Assistant.create(settings.engine)
    feedback = defaultdict(int)
    recent = defaultdict(deque)
    lock = threading.Lock()
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    def client_ip():
        return request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "?"

    def rate_limited():
        now = time.monotonic()
        with lock:
            q = recent[client_ip()]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= RATE_LIMIT:
                return True
            q.append(now)
            return False

    def read_message():
        body = request.get_json(silent=True) or {}
        message = str(body.get("message", "")).strip()
        session = app.assistant.sessions.get_or_create(str(body.get("session_id", ""))[:64])
        return message, session

    @app.after_request
    def cors(resp):
        if request.path.startswith("/api/"):
            origin = request.headers.get("Origin")
            allowed = app.config["ALLOWED_ORIGINS"]
            if "*" in allowed:
                resp.headers["Access-Control-Allow-Origin"] = "*"
            elif origin in allowed:
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            resp.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
        return resp

    @app.get("/")
    def demo_site():
        return render_template("index.html")

    @app.route("/api/chat/stream", methods=["POST", "OPTIONS"])
    def chat_stream():
        if request.method == "OPTIONS":
            return "", 204
        if rate_limited():
            return jsonify(error="Too many messages, please slow down."), 429
        message, session = read_message()
        if not message:
            return jsonify(error="message is required"), 400

        def events():
            for ev in app.assistant.stream(session, message):
                yield f"event: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"

        return Response(
            stream_with_context(events()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.route("/api/chat", methods=["POST", "OPTIONS"])
    def chat():
        if request.method == "OPTIONS":
            return "", 204
        if rate_limited():
            return jsonify(error="Too many messages, please slow down."), 429
        message, session = read_message()
        if not message:
            return jsonify(error="message is required"), 400
        return jsonify(app.assistant.respond(session, message))

    @app.route("/api/feedback", methods=["POST", "OPTIONS"])
    def post_feedback():
        if request.method == "OPTIONS":
            return "", 204
        body = request.get_json(silent=True) or {}
        helpful = body.get("helpful")
        if not isinstance(helpful, bool):
            return jsonify(error="helpful must be true or false"), 400
        with lock:
            feedback["up" if helpful else "down"] += 1
            with open(settings.log_dir / "feedback.jsonl", "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "session": str(body.get("session_id", ""))[:64],
                            "message": str(body.get("message", ""))[:300],
                            "helpful": helpful,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        return jsonify(ok=True)

    @app.get("/api/stats")
    def stats():
        s = app.assistant.stats
        n = s["messages"]
        up, down = feedback["up"], feedback["down"]
        return jsonify(
            engine=app.assistant.engine_name,
            messages=n,
            active_sessions=len(app.assistant.sessions),
            avg_latency_ms=round(s["latency_ms_total"] / n, 1) if n else None,
            tokens_in=s["tokens_in"],
            tokens_out=s["tokens_out"],
            est_cost_usd=round(s["cost_micro_usd"] / 1e6, 4),
            cache_hits=s["cache_hits"],
            llm_fallbacks=s["fallbacks"],
            tools={k[5:]: v for k, v in s.items() if k.startswith("tool:")},
            engines={k[7:]: v for k, v in s.items() if k.startswith("engine:")},
            helpful_rate=round(up / (up + down), 3) if up + down else None,
        )

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok", engine=app.assistant.engine_name)

    return app


app = create_app() if os.environ.get("NOVA_NO_AUTOCREATE") != "1" else None

if __name__ == "__main__":
    app.run(debug=False, port=5060, threaded=True)
