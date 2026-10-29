import json
import os
import threading
import time
import uuid
from collections import Counter, defaultdict, deque
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from bot import ChatBot

LOG_DIR = Path(os.environ.get("LOG_DIR", Path(__file__).resolve().parent / "logs"))
RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MIN", "30"))


def create_app(bot=None):
    app = Flask(__name__)
    app.config["ALLOWED_ORIGINS"] = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",")]
    app.bot = bot or ChatBot()
    stats = Counter()
    recent = defaultdict(deque)
    lock = threading.Lock()
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    def log(name, record):
        # Unanswered questions and feedback are reviewed to add new patterns and retrain.
        record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with lock, open(LOG_DIR / name, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def rate_limited(ip):
        now = time.monotonic()
        with lock:
            q = recent[ip]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= RATE_LIMIT:
                return True
            q.append(now)
            return False

    @app.after_request
    def cors(resp):
        # Lets the widget call this API from the store's own domain.
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

    @app.route("/api/chat", methods=["POST", "OPTIONS"])
    def chat():
        if request.method == "OPTIONS":
            return "", 204
        if rate_limited(request.remote_addr or "?"):
            return jsonify(error="Too many messages, please slow down."), 429
        body = request.get_json(silent=True) or {}
        message = str(body.get("message", "")).strip()
        if not message:
            return jsonify(error="message is required"), 400

        started = time.perf_counter()
        result = app.bot.reply(message, context=body.get("context"))
        result["id"] = uuid.uuid4().hex
        result["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)

        with lock:
            stats["messages"] += 1
            stats[f"intent:{result['intent']}"] += 1
            if result["handoff"]:
                stats["handoffs"] += 1
        if result["intent"] == "fallback":
            log("unanswered.jsonl", {"message": message[:500], "confidence": result["confidence"]})
        return jsonify(result)

    @app.route("/api/feedback", methods=["POST", "OPTIONS"])
    def feedback():
        if request.method == "OPTIONS":
            return "", 204
        body = request.get_json(silent=True) or {}
        helpful = body.get("helpful")
        if not isinstance(helpful, bool):
            return jsonify(error="helpful must be true or false"), 400
        with lock:
            stats["feedback_up" if helpful else "feedback_down"] += 1
        log("feedback.jsonl", {"id": str(body.get("id", ""))[:64], "intent": str(body.get("intent", ""))[:64],
                               "helpful": helpful})
        return jsonify(ok=True)

    @app.get("/api/stats")
    def api_stats():
        with lock:
            total = stats["messages"]
            up, down = stats["feedback_up"], stats["feedback_down"]
            return jsonify(
                messages=total,
                fallback_rate=round(stats["intent:fallback"] / total, 3) if total else 0,
                handoffs=stats["handoffs"],
                helpful_rate=round(up / (up + down), 3) if up + down else None,
                top_intents=[(k[7:], v) for k, v in stats.most_common() if k.startswith("intent:")][:5],
            )

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5060)
