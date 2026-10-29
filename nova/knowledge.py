"""Structured store knowledge: products, policies, branches, FAQs, orders (JSON files in data/knowledge)."""

import json
import re
from dataclasses import dataclass, field
from functools import cached_property

from .config import settings

CATEGORY_LABELS = {
    "phone": ("phones", "موبايلات"),
    "laptop": ("laptops", "لابتوبات"),
    "headphones": ("headphones", "سماعات"),
    "tablet": ("tablets", "تابلت"),
    "smartwatch": ("smartwatches", "ساعات ذكية"),
    "gaming": ("gaming", "ألعاب"),
    "tv": ("TVs", "شاشات"),
    "accessory": ("accessories", "إكسسوارات"),
}


def money(amount, lang="en"):
    return f"{amount:,} جنيه" if lang == "ar" else f"{amount:,} EGP"


@dataclass
class Doc:
    """A retrievable chunk of knowledge."""

    id: str
    kind: str  # product | policy | branch | faq
    title: str
    text: str
    text_ar: str = ""
    meta: dict = field(default_factory=dict)


class Knowledge:
    def __init__(self, data_dir=None):
        base = (data_dir or settings.data_dir) / "knowledge"
        self.products_raw = json.loads((base / "products.json").read_text(encoding="utf-8"))
        self.store = json.loads((base / "store.json").read_text(encoding="utf-8"))
        self.orders = {o["id"]: o for o in json.loads((base / "orders.json").read_text(encoding="utf-8"))["orders"]}
        self.products = {p["id"]: p for p in self.products_raw["products"]}
        self.currency = self.products_raw["currency"]
        self.policies = {p["id"]: p for p in self.store["policies"]}
        self.branches = {b["id"]: b for b in self.store["branches"]}

    # ---------- lookups ----------
    def product(self, pid):
        return self.products.get((pid or "").upper())

    @cached_property
    def _name_index(self):
        """Lower-case product names and useful aliases -> id, longest first (so 'nova x1 pro' beats 'nova x1')."""
        aliases = {}
        for p in self.products.values():
            name = p["name"].lower()
            aliases[name] = p["id"]
            aliases[name.replace('"', "")] = p["id"]
            stripped = re.sub(r"\b(console|gaming|headset|4k|qled|oled)\b", "", name).strip()
            stripped = re.sub(r"\s+", " ", stripped)
            if len(stripped) > 4:
                aliases.setdefault(stripped, p["id"])
        aliases.update(
            {
                "vertex g16": "LP-002",
                "play 5": "GM-001",
                "vertex play 5": "GM-001",
                "airbook": "LP-001",
                "buds pro": "HP-002",
                "anc 700": "HP-001",
                "lumen 55": "TV-001",
                "lumen 65": "TV-002",
                "55 qled": "TV-001",
                "65 oled": "TV-002",
                "fold z": "PH-005",
                "orbit lite": "PH-004",
                "tab s9": "TB-001",
                "tab a8": "TB-002",
                "watch 3": "SW-001",
                "band 8": "SW-002",
                "creator 16": "LP-004",
                "study 15": "LP-003",
                "x1 pro": "PH-001",
            }
        )
        return sorted(aliases.items(), key=lambda kv: -len(kv[0]))

    def find_products_in_text(self, text):
        """Product ids mentioned in free text, in order of appearance."""
        low = " " + re.sub(r"[^\w\s\"-]", " ", text.lower()) + " "
        found = []
        for alias, pid in self._name_index:
            for m in re.finditer(r"(?<![\w])" + re.escape(alias) + r"(?![\w])", low):
                found.append((m.start(), pid))
                low = low[: m.start()] + " " * len(alias) + low[m.end() :]  # don't match "nova x1" inside "nova x1 pro"
        seen, ordered = set(), []
        for _, pid in sorted(found):
            if pid not in seen:
                seen.add(pid)
                ordered.append(pid)
        return ordered

    def branch_from_text(self, text):
        low = text.lower()
        keys = {
            "nasr-city": ["nasr", "city stars", "مدينة نصر", "سيتي ستارز"],
            "maadi": ["maadi", "المعادي", "معادي"],
            "zayed": ["zayed", "arkan", "زايد", "أركان"],
            "alexandria": ["alex", "san stefano", "اسكندرية", "إسكندرية", "الإسكندرية"],
        }
        for bid, words in keys.items():
            if any(w in low for w in words):
                return bid
        return None

    # ---------- documents for retrieval ----------
    @cached_property
    def documents(self):
        docs = []
        for p in self.products.values():
            specs = "; ".join(f"{k}: {v}" for k, v in p["specs"].items())
            stock = "in stock" if p["stock"] > 0 else f"out of stock (restock {p.get('restock_date', 'TBA')})"
            docs.append(
                Doc(
                    id=p["id"],
                    kind="product",
                    title=p["name"],
                    text=(
                        f"{p['name']} by {p['brand']} — {CATEGORY_LABELS[p['category']][0]}. Price {p['price']:,} EGP. "
                        f"{stock}. Warranty {p['warranty_months']} months. Specs: {specs}. Good for: {', '.join(p['tags'])}."
                    ),
                    meta={"category": p["category"], "price": p["price"]},
                )
            )
        for pol in self.store["policies"]:
            docs.append(
                Doc(id=f"policy:{pol['id']}", kind="policy", title=pol["title"], text=pol["text"], text_ar=pol.get("text_ar", ""))
            )
        for b in self.store["branches"]:
            docs.append(
                Doc(
                    id=f"branch:{b['id']}",
                    kind="branch",
                    title=b["name"],
                    text=f"Branch {b['name']}. Address: {b['address']}. Opening hours: {b['hours']}. Phone {b['phone']}.",
                    text_ar=f"{b['name_ar']}. العنوان: {b['address']}. المواعيد: {b['hours_ar']}. تليفون {b['phone']}.",
                )
            )
        s = self.store["support"]
        docs.append(
            Doc(
                id="support",
                kind="policy",
                title="Customer support contact",
                text=f"Customer support hotline {s['phone']}, WhatsApp {s['whatsapp']}, email {s['email']}. Hours: {s['hours']}.",
                text_ar=f"خدمة العملاء على الخط الساخن {s['phone']} أو واتساب {s['whatsapp']}. المواعيد: {s['hours_ar']}.",
            )
        )
        for i, f in enumerate(self.store["faqs"]):
            docs.append(Doc(id=f"faq:{i}", kind="faq", title=f["q"], text=f"{f['q']} {f['a']}", text_ar=f.get("a_ar", "")))
        return docs

    @cached_property
    def known_amounts(self):
        """Every money amount that exists in the data — used to catch invented prices in model output."""
        amounts = {p["price"] for p in self.products.values()}
        for o in self.orders.values():
            amounts.add(o["total"])
        prices = sorted({p["price"] for p in self.products.values()})
        # Amounts legitimately derived from prices: differences, monthly installments, Nova Care+ (10%).
        amounts |= {abs(a - b) for a in prices for b in prices if a != b}
        amounts |= {round(p / n) for p in prices for n in (6, 12, 24)} | {round(p * 0.1) for p in prices}
        for d in self.documents:
            if d.kind != "product":
                amounts.update(int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", d.text) if x.replace(",", "").isdigit())
        return amounts


_kb = None


def get_knowledge():
    global _kb
    if _kb is None:
        _kb = Knowledge()
    return _kb
