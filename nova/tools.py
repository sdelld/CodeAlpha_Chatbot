"""Tools the assistant can call. Each returns plain JSON built only from the knowledge base."""

import json
import re
import threading
import time
import uuid

from .config import settings
from .knowledge import get_knowledge

CATEGORIES = ["phone", "laptop", "headphones", "tablet", "smartwatch", "gaming", "tv", "accessory"]
_ticket_lock = threading.Lock()

# Words that point to a category or a need (English after glossary translation).
CATEGORY_WORDS = {
    "phone": ["phone", "phones", "mobile", "smartphone"],
    "laptop": ["laptop", "laptops", "notebook", "macbook", "chromebook"],
    "headphones": ["headphone", "headphones", "earbuds", "earphones", "headset", "buds"],
    "tablet": ["tablet", "tablets", "ipad", "tab"],
    "smartwatch": ["smartwatch", "smartwatches", "watch", "band", "fitness tracker"],
    "gaming": ["console", "playstation", "handheld"],
    "tv": ["tv", "tvs", "television", "screen"],
    "accessory": ["accessory", "accessories", "charger", "case", "power bank", "mouse", "keyboard", "hub", "controller"],
}
NEED_WORDS = {  # need -> words in the request; needs are matched against product tags
    "noise cancelling": ["noise", "anc", "cancel", "cancelling", "canceling"],
    "travel": ["flight", "flights", "travel", "plane", "trip"],
    "students": ["student", "students", "university", "college", "school", "study"],
    "gaming": ["gaming", "game", "games", "gamer", "console"],
    "camera": ["camera", "photo", "photos", "photography", "pictures"],
    "battery": ["battery", "long lasting", "all day"],
    "kids": ["kid", "kids", "child", "children"],
    "fitness": ["running", "run", "runs", "fitness", "gym", "sport", "workout"],
    "creator": ["video editing", "editing", "4k video", "videos", "design", "creator", "edit"],
    "budget": ["cheap", "budget", "affordable", "cheapest", "low price"],
    "premium": ["best", "flagship", "premium", "top"],
}


def _card(p, detail=False):
    card = {
        "id": p["id"],
        "name": p["name"],
        "brand": p["brand"],
        "category": p["category"],
        "price_egp": p["price"],
        "in_stock": p["stock"] > 0,
        "stock_online": p["stock"],
        "warranty_months": p["warranty_months"],
        "key_specs": dict(list(p["specs"].items())[:4]),
    }
    if p["stock"] == 0:
        card["restock_date"] = p.get("restock_date")
    if detail:
        kb = get_knowledge()
        card["specs"] = p["specs"]
        card["tags"] = p["tags"]
        card["recommended_accessories"] = [_card(kb.products[a]) for a in p["accessories"] if a in kb.products]
    return card


def detect_category(text):
    low = text.lower()
    for cat, words in CATEGORY_WORDS.items():
        if any(re.search(r"(?<![a-z])" + re.escape(w) + r"s?(?![a-z])", low) for w in words):
            return cat
    return None


def detect_needs(text):
    low = text.lower()
    return [
        need
        for need, words in NEED_WORDS.items()
        if any(re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low) for w in words)
    ]


def _relevance(p, query, needs):
    q = query.lower()
    haystack = " ".join([p["name"], p["brand"], p["category"], " ".join(p["tags"])]).lower()
    score = sum(1.0 for w in set(re.findall(r"[a-z0-9]+", q)) if len(w) > 2 and w in haystack)
    tags = " ".join(p["tags"]).lower()
    for need in needs:
        if need == "premium":
            score += p["price"] / 50000
        elif need != "budget" and need in tags:
            score += 3
    return score


def search_products(query="", category=None, max_price=None, min_price=None, in_stock_only=False, limit=4):
    """Search the catalogue. Returns up to `limit` product cards, best match first."""
    kb = get_knowledge()
    category = category if category in CATEGORIES else detect_category(query or "")
    needs = detect_needs(query or "")
    items = list(kb.products.values())
    if category:
        items = [p for p in items if p["category"] == category]
        if category != "accessory" and not needs and not query:
            items = [p for p in items if p["category"] != "accessory"]
    if max_price:
        items = [p for p in items if p["price"] <= max_price]
    if min_price:
        items = [p for p in items if p["price"] >= min_price]
    if in_stock_only:
        items = [p for p in items if p["stock"] > 0]
    scored = [(p, _relevance(p, query or "", needs)) for p in items]
    if not category and query:
        scored = [(p, s) for p, s in scored if s > 0]

    def price_key(p):
        if "budget" in needs:
            return p["price"]  # cheapest first
        return -p["price"] if max_price else p["price"]  # with a budget, the best you can get within it

    scored.sort(key=lambda ps: (ps[0]["stock"] == 0, -ps[1], price_key(ps[0])))
    return {
        "query": query,
        "category": category,
        "max_price": max_price,
        "results": [_card(p) for p, _ in scored[: max(1, min(limit, 8))]],
        "total_matches": len(scored),
    }


def get_product(product_id):
    p = get_knowledge().product(product_id)
    if not p:
        return {"error": f"No product with id {product_id}. Use search_products to find ids."}
    return _card(p, detail=True)


def check_stock(product_id, branch=None):
    kb = get_knowledge()
    p = kb.product(product_id)
    if not p:
        return {"error": f"No product with id {product_id}."}
    out = {
        "id": p["id"],
        "name": p["name"],
        "online_stock": p["stock"],
        "in_stock_online": p["stock"] > 0,
        "branches": {kb.branches[b]["name"]: n for b, n in p["branch_stock"].items()},
    }
    if p["stock"] == 0:
        out["restock_date"] = p.get("restock_date")
    if branch:
        bid = branch if branch in kb.branches else kb.branch_from_text(branch)
        if bid:
            out["requested_branch"] = {"branch": kb.branches[bid]["name"], "units": p["branch_stock"].get(bid, 0)}
    return out


def compare_products(product_ids):
    kb = get_knowledge()
    products = [kb.product(pid) for pid in product_ids[:4]]
    missing = [pid for pid, p in zip(product_ids, products, strict=False) if not p]
    products = [p for p in products if p]
    keys = list(dict.fromkeys(k for p in products for k in p["specs"]))
    return {
        "products": [
            {
                "id": p["id"],
                "name": p["name"],
                "price_egp": p["price"],
                "in_stock": p["stock"] > 0,
                "warranty_months": p["warranty_months"],
                "specs": {k: p["specs"].get(k, "—") for k in keys},
                "good_for": p["tags"],
            }
            for p in products
        ],
        "price_difference_egp": (max(p["price"] for p in products) - min(p["price"] for p in products))
        if len(products) > 1
        else 0,
        **({"not_found": missing} if missing else {}),
    }


def get_order_status(order_id):
    kb = get_knowledge()
    oid = re.sub(r"[^A-Za-z0-9]", "", order_id or "").upper()
    if re.fullmatch(r"\d{5}", oid):
        oid = "NV" + oid
    order = kb.orders.get(oid)
    if not order:
        return {"order_id": oid, "found": False}
    items = [kb.products[i]["name"] for i in order["items"] if i in kb.products]
    out = {"order_id": oid, "found": True, **{k: v for k, v in order.items() if k not in ("id", "items")}, "items": items}
    if order.get("branch"):
        out["branch"] = kb.branches[order["branch"]]["name"]
    return out


def create_support_ticket(issue, contact, name=None, order_id=None, category="general"):
    if not contact or not re.search(r"\d{8,}|@", contact):
        return {"created": False, "error": "A phone number or email is required to open a ticket."}
    ticket = {
        "ticket_id": "T-" + uuid.uuid4().hex[:6].upper(),
        "issue": issue[:1000],
        "contact": contact[:120],
        "name": (name or "")[:80],
        "order_id": order_id,
        "category": category,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    with _ticket_lock, open(settings.log_dir / "tickets.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(ticket, ensure_ascii=False) + "\n")
    return {"created": True, "ticket_id": ticket["ticket_id"], "response_time": "within 24 hours"}


REGISTRY = {
    "search_products": search_products,
    "get_product": get_product,
    "check_stock": check_stock,
    "compare_products": compare_products,
    "get_order_status": get_order_status,
    "create_support_ticket": create_support_ticket,
}

# JSON-schema declarations for the LLM (Gemini function calling).
DECLARATIONS = [
    {
        "name": "search_products",
        "description": "Search the Nova Electronics catalogue by need, category and budget. Use for any request to find, list or recommend products.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What the customer wants in English keywords, e.g. 'noise cancelling headphones for flights'",
                },
                "category": {"type": "string", "enum": CATEGORIES},
                "max_price": {"type": "integer", "description": "Maximum price in EGP (the customer's budget)"},
                "min_price": {"type": "integer"},
                "in_stock_only": {"type": "boolean"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_product",
        "description": "Full details, specs, warranty and compatible accessories for one product id (e.g. 'LP-001').",
        "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]},
    },
    {
        "name": "check_stock",
        "description": "Online and per-branch stock for a product id, and restock date if out of stock.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "branch": {"type": "string", "description": "nasr-city | maadi | zayed | alexandria"},
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "compare_products",
        "description": "Side-by-side comparison of 2-4 product ids.",
        "parameters": {
            "type": "object",
            "properties": {"product_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["product_ids"],
        },
    },
    {
        "name": "get_order_status",
        "description": "Status, carrier and ETA for an order number like NV12345.",
        "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    },
    {
        "name": "create_support_ticket",
        "description": "Open a ticket for a human agent (complaints, billing problems, damaged items). Needs the customer's phone or email.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue": {"type": "string"},
                "contact": {"type": "string", "description": "phone number or email"},
                "name": {"type": "string"},
                "order_id": {"type": "string"},
                "category": {"type": "string", "enum": ["delivery", "billing", "product_fault", "staff", "general"]},
            },
            "required": ["issue", "contact"],
        },
    },
]


def call(name, args):
    fn = REGISTRY.get(name)
    if fn is None:
        return {"error": f"Unknown tool {name}"}
    try:
        return fn(**(args or {}))
    except TypeError as e:
        return {"error": f"Bad arguments for {name}: {e}"}
