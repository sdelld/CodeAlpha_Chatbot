import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot import ChatBot, normalize  # noqa: E402


@pytest.fixture(scope="module")
def bot():
    return ChatBot(seed=0)


@pytest.fixture()
def client(bot, tmp_path, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "LOG_DIR", tmp_path)
    return app_module.create_app(bot).test_client()


def test_normalize_handles_slang_and_punctuation():
    assert normalize("Where R U?!") == "where are you"
    assert normalize("thx!!") == "thanks"


@pytest.mark.parametrize("text,tag", [
    ("hello", "greeting"),
    ("how much is shipping", "shipping_cost"),
    ("I want to return my order", "returns"),
    ("can I pay with paypal?", "payment_methods"),
    ("talk to a human", "human_agent"),
])
def test_known_questions(bot, text, tag):
    assert bot.classify(text)[0] == tag


def test_typos_are_tolerated(bot):
    assert bot.classify("hw long does shiping take")[0] == "shipping_time"


@pytest.mark.parametrize("text", ["explain quantum physics", "what is the capital of france", "", "?!"])
def test_off_topic_falls_back(bot, text):
    assert bot.reply(text)["intent"] == "fallback"


def test_held_out_accuracy_at_least_85_percent(bot):
    samples = json.loads((ROOT / "data" / "test_set.json").read_text(encoding="utf-8"))["samples"]
    correct = sum(bot.classify(text)[0] == tag for text, tag in samples)
    assert correct / len(samples) >= 0.85


def test_order_tracking_flow(bot):
    first = bot.reply("where is my order")
    assert first["context"] == "awaiting_order_id"
    second = bot.reply("12345", context=first["context"])
    assert "NV12345" in second["reply"] and "shipped" in second["reply"]
    assert "couldn't find" in bot.reply("status of NV99999")["reply"]


def test_chat_api(client):
    r = client.post("/api/chat", json={"message": "do you ship internationally"})
    data = r.get_json()
    assert r.status_code == 200 and data["intent"] == "international_shipping" and data["id"]
    assert r.headers["Access-Control-Allow-Origin"] == "*"
    assert client.post("/api/chat", json={}).status_code == 400


def test_feedback_and_stats(client):
    client.post("/api/chat", json={"message": "hi"})
    client.post("/api/chat", json={"message": "tell me a joke about penguins"})
    assert client.post("/api/feedback", json={"id": "x", "intent": "greeting", "helpful": True}).status_code == 200
    assert client.post("/api/feedback", json={"helpful": "yes"}).status_code == 400
    stats = client.get("/api/stats").get_json()
    assert stats["messages"] == 2 and stats["helpful_rate"] == 1.0


def test_rate_limit(client):
    import app as app_module
    statuses = [client.post("/api/chat", json={"message": "hi"}).status_code
                for _ in range(app_module.RATE_LIMIT + 1)]
    assert statuses[-1] == 429


def test_demo_site_embeds_widget(client):
    html = client.get("/").get_data(as_text=True)
    assert "widget.js" in html
