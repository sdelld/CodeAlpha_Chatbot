"""Retrieval-based chatbot: classifies a message into one of the intents in data/intents.json
and answers with that intent's predefined response.

Model: TF-IDF features over words (meaning) + character n-grams (robust to typos such as
"shiping" or "retrun"), fed into a logistic-regression classifier. If the classifier is not
confident enough, the bot says it doesn't know instead of guessing.
"""
import json
import random
import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_THRESHOLD = 0.25

SLANG = {
    "u": "you", "ur": "your", "r": "are", "thx": "thanks", "ty": "thank you", "pls": "please",
    "plz": "please", "cant": "can't", "dont": "don't", "wont": "won't", "im": "i'm", "whats": "what's",
    "hw": "how", "wanna": "want to", "gonna": "going to",
}

ORDER_ID = re.compile(r"\bNV[\s-]?(\d{5})\b", re.IGNORECASE)

# Stand-in for a real order database / API.
DEMO_ORDERS = {
    "NV12345": "shipped on Monday and is out for delivery today 🚚",
    "NV67890": "being packed at our warehouse and will ship within 24 hours 📦",
    "NV24680": "was delivered yesterday at 14:32 ✅",
}

FALLBACK = {
    "reply": "Sorry, I'm not sure I understood that. I can help with orders, shipping, returns, "
             "payments, warranty and store info — or connect you with a human.",
    "suggestions": ["Track my order", "Return policy", "Talk to a human"],
}


def normalize(text):
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    return " ".join(SLANG.get(w, w) for w in text.split())


def build_model():
    features = FeatureUnion([
        ("words", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True)),
    ])
    return Pipeline([("features", features), ("clf", LogisticRegression(C=20, max_iter=5000))])


def load_intents(path=DATA_DIR / "intents.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class ChatBot:
    def __init__(self, intents=None, threshold=DEFAULT_THRESHOLD, seed=None):
        data = intents or load_intents()
        self.business = data.get("business", "our store")
        self.intents = {i["tag"]: i for i in data["intents"]}
        self.threshold = threshold
        self.random = random.Random(seed)

        texts, labels = [], []
        for intent in data["intents"]:
            for pattern in intent["patterns"]:
                texts.append(normalize(pattern))
                labels.append(intent["tag"])
        self.model = build_model().fit(texts, labels)
        self.word_vocab = self.model.named_steps["features"].transformer_list[0][1].vocabulary_

    def classify(self, text):
        """Return (tag, confidence). tag is 'fallback' when the bot should not answer."""
        clean = normalize(text)
        if not clean:
            return "fallback", 0.0
        probs = self.model.predict_proba([clean])[0]
        best = probs.argmax()
        tag, confidence = self.model.classes_[best], float(probs[best])
        # Out-of-scope guard: a message sharing no vocabulary with the training data
        # ("explain quantum physics") is unknown, however the probabilities fall.
        known_words = sum(1 for w in clean.split() if w in self.word_vocab)
        if confidence < self.threshold or known_words == 0:
            return "fallback", confidence
        return tag, confidence

    def reply(self, text, context=None):
        text = (text or "").strip()[:500]

        order = ORDER_ID.search(text)
        if order:
            return self._order_status("NV" + order.group(1))
        if context == "awaiting_order_id" and re.fullmatch(r"#?\s*\d{5}", text):
            return self._order_status("NV" + re.sub(r"\D", "", text))

        tag, confidence = self.classify(text)
        if tag == "fallback":
            return {"reply": FALLBACK["reply"], "intent": "fallback", "confidence": round(confidence, 3),
                    "suggestions": FALLBACK["suggestions"], "context": None, "handoff": False}

        intent = self.intents[tag]
        return {
            "reply": self.random.choice(intent["responses"]),
            "intent": tag,
            "confidence": round(confidence, 3),
            "suggestions": intent.get("suggestions", []),
            "context": intent.get("context_set"),
            "handoff": intent.get("handoff", False),
        }

    def _order_status(self, order_id):
        status = DEMO_ORDERS.get(order_id.upper())
        if status:
            msg = f"Order {order_id.upper()} {status}"
        else:
            msg = (f"I couldn't find order {order_id.upper()}. Please double-check the number in your "
                   "confirmation email, or I can connect you with a human.")
        return {"reply": msg, "intent": "order_lookup", "confidence": 1.0,
                "suggestions": ["Talk to a human"] if not status else [], "context": None, "handoff": False}
