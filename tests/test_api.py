"""HTTP API tests (local engine)."""

import json

import pytest

from app import create_app
from nova.assistant import Assistant


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from nova.config import settings

    monkeypatch.setattr(settings, "log_dir", tmp_path)
    return create_app(Assistant.create("local")).test_client()


def sse(resp):
    events = []
    for block in resp.get_data(as_text=True).strip().split("\n\n"):
        data = next(line for line in block.split("\n") if line.startswith("data: "))
        events.append(json.loads(data[6:]))
    return events


def test_stream_endpoint(client):
    r = client.post("/api/chat/stream", json={"message": "show me laptops under 30000"})
    assert r.mimetype == "text/event-stream"
    events = sse(r)
    assert events[0]["type"] == "meta" and events[-1]["type"] == "done"
    assert any(e["type"] == "products" for e in events)
    assert "Vertex Study 15" in events[-1]["reply"]


def test_session_memory_across_requests(client):
    first = client.post("/api/chat", json={"message": "tell me about the AirBook 14"}).get_json()
    second = client.post("/api/chat", json={"message": "how much does it cost?", "session_id": first["session_id"]}).get_json()
    assert "54,999" in second["reply"]


def test_json_endpoint_and_validation(client):
    r = client.post("/api/chat", json={"message": "where is my order NV12345?"}).get_json()
    assert r["tools"] == ["get_order_status"] and "shipped" in r["reply"]
    assert client.post("/api/chat", json={}).status_code == 400
    assert client.post("/api/chat/stream", json={"message": ""}).status_code == 400


def test_feedback_and_stats(client):
    client.post("/api/chat", json={"message": "hi"})
    assert client.post("/api/feedback", json={"helpful": True, "message": "hi"}).status_code == 200
    assert client.post("/api/feedback", json={"helpful": "yes"}).status_code == 400
    s = client.get("/api/stats").get_json()
    assert s["messages"] == 1 and s["helpful_rate"] == 1.0 and s["engine"] == "local"


def test_request_log_written(client, tmp_path):
    client.post("/api/chat", json={"message": "what is your return policy?"})
    record = json.loads((tmp_path / "requests.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert {"ttft_ms", "latency_ms", "tokens_in", "tokens_out", "cost_usd", "tools", "retrieval_hits"} <= set(record)


def test_rate_limit(client):
    import app as app_module

    codes = [client.post("/api/chat", json={"message": "hi"}).status_code for _ in range(app_module.RATE_LIMIT + 1)]
    assert codes[-1] == 429


def test_cors_and_health(client):
    r = client.get("/healthz")
    assert r.get_json()["status"] == "ok"
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.headers["Access-Control-Allow-Origin"] == "*"


def test_demo_site(client):
    assert "widget.js" in client.get("/").get_data(as_text=True)
