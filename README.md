# CodeAlpha — Task 4: AI Customer-Support Chatbot

A retrieval-based AI chatbot for an online electronics store ("Nova Electronics"). It answers customer
questions instantly and plugs into any website with **one `<script>` tag**.

**Stack:** Python · scikit-learn · Flask · vanilla JS widget · Docker · Gunicorn

## How each requirement is met

| Requirement | How |
|---|---|
| AI chatbot (retrieval-based) | A machine-learning intent classifier (TF-IDF word + character n-grams → logistic regression) picks the best-matching intent and returns its prepared answer (`bot.py`). |
| Instant responses on websites | Replies in ~20 ms. REST endpoint `POST /api/chat`, with CORS so the widget can be used from other domains. |
| Trained on predefined input patterns for commercial use | `data/intents.json`: 24 store intents (orders, shipping, returns, refunds, payments, installments, warranty, stock, discounts, store location, account help, human handoff…) with ~270 example phrasings. |
| Seamless website integration | `static/widget.js` is a self-contained chat bubble (no libraries): typing indicator, quick-reply chips, conversation kept while the tab is open, keyboard accessible, full-screen on phones. The demo store page at `/` shows it in use. |
| Optimised and tested for accuracy | `evaluate.py` measures accuracy on **50 held-out messages the model never saw** (including typos and off-topic questions). Adding varied training phrasings raised it from **84% → 92%**, with the confidence threshold tuned to 0.25. 17 automated tests. |
| User engagement | Suggestion chips after answers, 👍/👎 feedback on every reply, human-agent handoff, an order-tracking conversation (asks for the order number, then looks it up), and `/api/stats` (messages, fallback rate, helpful rate, top intents). Unanswered questions are logged to `logs/unanswered.jsonl` so new patterns can be added. |

### Typos and off-topic questions
Character n-grams let the bot understand "hw long does shiping take" and "retrun policy?". When it isn't
confident, or the message shares no words with its training data ("explain quantum physics"), it says it doesn't
know and offers help options instead of guessing.

## Run locally

```bash
pip install -r requirements.txt
```
```bash
python app.py
```
Open http://127.0.0.1:5060 and click the chat bubble. Try: "where is my order" then "12345",
"can I pay in installments?", "hw long does shiping take", "talk to a human".

## Measure accuracy

```bash
python evaluate.py --tune
```

## Tests

```bash
python -m pytest -q
```

## Add it to any website

```html
<script src="https://YOUR-BOT-URL/static/widget.js" data-api="https://YOUR-BOT-URL" defer></script>
```
Set `ALLOWED_ORIGINS=https://your-shop.com` on the server to only accept that site.
`window.NovaChat.open()` opens the chat from your own buttons.

## Improve the bot
1. Read `logs/unanswered.jsonl` and the 👎 entries in `logs/feedback.jsonl`.
2. Add those phrasings as patterns (or a new intent) in `data/intents.json`.
3. Run `python evaluate.py` to confirm accuracy didn't drop, then redeploy. The model retrains on startup (about a second).

## Deploy to the cloud

**Render (free, simplest):** push to GitHub → New Web Service → pick the repo → Runtime: Docker → Deploy.

**Google Cloud Run (auto-scales):**
```bash
gcloud run deploy codealpha-chatbot --source . --allow-unauthenticated --max-instances 5
```

**AWS Elastic Beanstalk:** `eb init -p docker codealpha-chatbot` then `eb create chatbot-prod`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `ALLOWED_ORIGINS` | `*` | Comma-separated sites allowed to call the API |
| `RATE_LIMIT_PER_MIN` | `30` | Messages per minute per IP (per server) |
| `LOG_DIR` | `./logs` | Where unanswered questions and feedback go |

## API

`POST /api/chat` `{"message": "...", "context": null}` →
`{"reply", "intent", "confidence", "suggestions", "context", "handoff", "id", "latency_ms"}`.
Send the returned `context` back with the next message (this keeps the server stateless, so it scales horizontally).

`POST /api/feedback` `{"id", "intent", "helpful": true|false}` · `GET /api/stats` · `GET /healthz`
