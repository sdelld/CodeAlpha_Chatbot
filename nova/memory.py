"""Per-session conversation memory.

Keeps the last few turns verbatim plus a compact fact sheet (name, budget, category, needs, products
discussed, pending questions). The fact sheet is what lets long conversations stay cheap: older turns are
dropped from the prompt but what mattered in them is kept.
"""

import re
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from .config import settings
from .knowledge import get_knowledge
from .lang import normalise_numbers, to_english_terms
from .tools import detect_category, detect_needs

BUDGET = re.compile(
    r"(?:budget|under|below|less than|max(?:imum)?|up to|around|about|within|ميزانيتي|ميزانية|تحت|حوالي|في حدود|lehad|ta7t)"
    r"\D{0,15}?(\d{3,7})|(\d{3,7})\s*(?:egp|le|l\.e|pounds?|جنيه|ج\.م|geneh|gneh)",
    re.I,
)
NAME = re.compile(r"(?:my name is|i am|i'm|call me|اسمي|ana esmy|esmy)\s+([A-Za-z؀-ۿ]{2,20})", re.I)
NOT_NAMES = {"a", "an", "the", "looking", "student", "interested", "trying", "going", "not", "here", "fine", "good"}


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    turns: list = field(default_factory=list)  # [{"role": "user"|"assistant", "text": str}]
    facts: dict = field(default_factory=dict)
    summary: str = ""
    earlier: list = field(default_factory=list)  # older customer questions folded out of the prompt
    language: str = "en"
    last_seen: float = field(default_factory=time.time)

    def add(self, role, text):
        self.turns.append({"role": role, "text": text})
        if len(self.turns) > settings.history_turns * 2:
            self._summarise_overflow()

    def _summarise_overflow(self):
        """Fold the oldest turns into a one-line summary (no LLM call needed: the fact sheet carries the meaning)."""
        old = self.turns[: -settings.history_turns * 2]
        self.turns = self.turns[-settings.history_turns * 2 :]
        self.earlier += [t["text"][:60] for t in old if t["role"] == "user"]
        self.earlier = self.earlier[-10:]
        self.summary = "Earlier the customer asked: " + " / ".join(self.earlier)

    def recent(self):
        return self.turns[-settings.history_turns * 2 :]

    def fact_sheet(self):
        kb = get_knowledge()
        f = self.facts
        lines = []
        if f.get("name"):
            lines.append(f"Customer name: {f['name']}")
        if f.get("budget"):
            lines.append(f"Budget: up to {f['budget']:,} EGP")
        if f.get("category"):
            lines.append(f"Looking for: {f['category']}")
        if f.get("needs"):
            lines.append(f"Needs/preferences: {', '.join(f['needs'])}")
        if f.get("products"):
            lines.append(
                "Products discussed (most recent last): "
                + ", ".join(f"{kb.products[p]['name']} [{p}]" for p in f["products"] if p in kb.products)
            )
        if f.get("order_id"):
            lines.append(f"Order mentioned: {f['order_id']}")
        if self.summary:
            lines.append(self.summary)
        return "\n".join(lines)


def remember(session, text):
    """Update the fact sheet from a customer message."""
    kb = get_knowledge()
    norm = normalise_numbers(text)
    english = to_english_terms(norm)
    f = session.facts
    m = BUDGET.search(norm)
    budget_now = None
    if m:
        value = int(m.group(1) or m.group(2))
        if 300 <= value <= 500_000:
            budget_now = value
    m = NAME.search(text)
    if m and m.group(1).lower() not in NOT_NAMES:
        f["name"] = m.group(1).capitalize() if m.group(1).isascii() else m.group(1)
    cat = detect_category(english)
    if cat:
        if f.get("category") and cat != f["category"] and budget_now is None:
            f.pop("budget", None)  # a laptop budget doesn't apply to headphones
        f["category"] = cat
    if budget_now is not None:
        f["budget"] = budget_now
    needs = detect_needs(english)
    if needs:
        f["needs"] = list(dict.fromkeys(f.get("needs", []) + needs))[-5:]
    mentioned = kb.find_products_in_text(norm)
    if mentioned:
        f["products"] = [p for p in f.get("products", []) if p not in mentioned] + mentioned
        f["products"] = f["products"][-6:]
    m = re.search(r"\bNV\s?-?(\d{5})\b", text, re.I)
    if m:
        f["order_id"] = "NV" + m.group(1)


def remember_products(session, product_ids):
    f = session.facts
    f["products"] = ([p for p in f.get("products", []) if p not in product_ids] + list(product_ids))[-6:]


class SessionStore:
    """In-memory sessions with TTL. Swap for Redis to share sessions across several app instances."""

    def __init__(self, ttl=None, max_sessions=10_000):
        self.ttl = ttl or settings.session_ttl_s
        self.max = max_sessions
        self._data = OrderedDict()
        self._lock = threading.Lock()

    def new(self):
        s = Session()
        with self._lock:
            self._data[s.id] = s
            self._evict()
        return s

    def get(self, session_id):
        with self._lock:
            s = self._data.get(session_id or "")
            if s is None or time.time() - s.last_seen > self.ttl:
                return None
            s.last_seen = time.time()
            self._data.move_to_end(session_id)
            return s

    def get_or_create(self, session_id):
        return self.get(session_id) or self.new()

    def _evict(self):
        now = time.time()
        while self._data and (len(self._data) > self.max or now - next(iter(self._data.values())).last_seen > self.ttl):
            self._data.popitem(last=False)

    def __len__(self):
        return len(self._data)
