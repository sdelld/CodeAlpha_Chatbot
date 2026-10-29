"""Local engine: deterministic routing + retrieval + tools + bilingual templates. No API key, no cost.

Used on its own in free mode, and as the fallback when the LLM is unavailable (timeouts, rate limits, outages).
Every fact it states comes from the knowledge base or a tool result.
"""

import re
from dataclasses import dataclass, field

from . import tools
from .knowledge import CATEGORY_LABELS, get_knowledge, money
from .lang import normalise_numbers, reply_language, to_english_terms
from .memory import remember, remember_products
from .safety import is_gibberish, is_injection

T = {
    "greet": {
        "en": "Hi! 👋 I'm Nova, the Nova Electronics assistant. I can find products, compare them, check stock and prices, track orders and explain delivery, payment, warranty and returns. What are you looking for today?",
        "ar": "أهلاً بيك! 👋 أنا نوفا، مساعد نوفا إلكترونيكس. أقدر أساعدك تلاقي منتج أو تقارن بين منتجين، أشوفلك السعر والمخزون، أتابع طلبك، وأشرحلك التوصيل والدفع والضمان والاسترجاع. بتدوّر على إيه النهارده؟",
    },
    "thanks": {"en": "You're welcome! Anything else I can help with?", "ar": "العفو! أي خدمة تانية؟"},
    "bye": {"en": "Thanks for visiting Nova Electronics — have a great day!", "ar": "شكرًا لزيارتك نوفا إلكترونيكس — يومك سعيد!"},
    "clarify": {
        "en": "Sorry, I didn't get that. Could you rephrase? I can help you find a product, check a price or stock, track an order, or explain delivery, payment, warranty and returns.",
        "ar": "معلش مفهمتش قصدك. ممكن توضّح أكتر؟ أقدر أساعدك تلاقي منتج، أشوف سعر أو مخزون، أتابع طلب، أو أشرح التوصيل والدفع والضمان والاسترجاع.",
    },
    "offtopic": {
        "en": "I'm Nova's shopping assistant, so I can only help with Nova Electronics — products, prices, orders, delivery, payment, warranty and returns. Is there something you're shopping for?",
        "ar": "أنا مساعد التسوق بتاع نوفا، فبقدر أساعد بس في حاجات نوفا إلكترونيكس — المنتجات والأسعار والطلبات والتوصيل والدفع والضمان والاسترجاع. بتدوّر على حاجة معينة؟",
    },
    "injection": {
        "en": "I can't share my internal instructions or change how I work, and I can't change prices or apply discounts. I'm happy to help with products, orders, delivery, payment, warranty or returns.",
        "ar": "مقدرش أشارك التعليمات الداخلية أو أغيّر طريقة شغلي، ومقدرش أغيّر الأسعار أو أطبّق خصومات. بس يسعدني أساعدك في المنتجات والطلبات والتوصيل والدفع والضمان والاسترجاع.",
    },
    "ask_order": {
        "en": "Sure — what's your order number? It looks like NV12345 and it's in your confirmation SMS/email.",
        "ar": "أكيد — ممكن رقم الطلب؟ شكله كده NV12345 وموجود في رسالة التأكيد.",
    },
    "not_carry": {
        "en": "Sorry, we don't carry {thing} at Nova Electronics. We sell phones, laptops, tablets, headphones, smartwatches, gaming, TVs and accessories.",
        "ar": "للأسف مش بنبيع {thing} في نوفا إلكترونيكس. إحنا عندنا موبايلات ولابتوبات وتابلت وسماعات وساعات ذكية وألعاب وشاشات وإكسسوارات.",
    },
    "unknown_product": {
        "en": "I couldn't find \"{thing}\" in our catalogue — we don't carry it.",
        "ar": 'مالقتش "{thing}" في المنتجات عندنا — مش متوفر عندنا.',
    },
    "name": {"en": "Your name is {name} 😊", "ar": "اسمك {name} 😊"},
    "name_unknown": {"en": "You haven't told me your name yet.", "ar": "لسه مقولتليش اسمك."},
    "need_clarify": {
        "en": "Happy to help! What kind of product are you looking for (phone, laptop, headphones…) and roughly what's your budget?",
        "ar": "يسعدني أساعدك! بتدوّر على أنهي نوع (موبايل، لابتوب، سماعات…) وميزانيتك تقريبًا كام؟",
    },
}

STATUS = {
    "shipped": (
        "shipped with {carrier} (tracking {tracking}) and should arrive by {eta}",
        "اتشحن مع {carrier} (رقم التتبع {tracking}) ومتوقع يوصل يوم {eta}",
    ),
    "processing": (
        "is being prepared (processing) and should ship soon — estimated delivery {eta}",
        "بيتجهز دلوقتي (قيد التجهيز) وهيتشحن قريب — التوصيل المتوقع {eta}",
    ),
    "delivered": ("was delivered on {delivered}", "اتسلّم يوم {delivered}"),
    "cancelled": ("was cancelled. {note}", "اتلغى. {note}"),
    "ready_for_pickup": (
        "is ready for pickup at {branch} — bring your ID and order number",
        "جاهز للاستلام من {branch} — هات بطاقتك ورقم الطلب",
    ),
}

GREETING = re.compile(
    r"^\s*(hi|hello|hey|hiya|good (morning|afternoon|evening)|salam|ahlan|ezayak|ezayek|اهلا|أهلا|مرحبا|السلام عليكم|ازيك|إزيك|صباح|مساء|هاي)\b",
    re.I,
)
IDENTITY = re.compile(
    r"who (am i talking|are you)|are you (a )?(bot|human|robot)|what can you do|your name|انت مين|إنت مين|enta meen", re.I
)
THANKS = re.compile(r"^\s*(thanks|thank you|thx|shokran|shukran|شكرا|شكرًا|متشكر)", re.I)
BYE = re.compile(r"^\s*(bye|goodbye|see you|مع السلامة|سلام|bye bye)\b", re.I)
ASK_NAME = re.compile(r"what'?s my name|what is my name|do you know my name|اسمي ايه|اسمي إيه|esmy eh", re.I)
ORDER_WORDS = re.compile(r"\border\b|track|tracking|shipment|package|parcel|طلبي|الطلب|اوردر|أوردر|talaby|ordery", re.I)
COMPLAINT = re.compile(
    r"complain|complaint|rude|angry|unacceptable|terrible|charged twice|double charged|overcharged|scam|worst"
    r"|faulty|broken|stopped working|not working|doesn't work|defect|no sound|damaged|شكوى|زعلان|عطلان|بايظ|مش شغال|اتكسر",
    re.I,
)
CONTACT = re.compile(r"(?:\+?20)?0?1[0125]\d{8}|[\w.+-]+@[\w-]+\.[\w.]+")
COMPARE = re.compile(
    r"compare|\bvs\.?\b|versus|difference|better|\bor the\b|\bor\b|which one|which is|ولا|مقارنة|الفرق|أحسن|احسن|wala|walla", re.I
)
STOCK = re.compile(r"in stock|stock|available|availability|back in|be back|restock|branch|متوفر|موجود|متاح|mawgood|fy far3", re.I)
ACCESSORY_Q = re.compile(r"accessor|go (well )?with|compatible|إكسسوار|اكسسوار", re.I)
PRONOUN = re.compile(
    r"\b(it|its|it's|that one|this one|them|those|which one|the one)\b|\bده\b|\bدي\b|\bدول\b|\bdah\b|\bdy\b", re.I
)
SEARCHY = re.compile(
    r"do you (have|sell|carry)|show me|recommend|suggest|looking for|i need|i want|need a|want a|best|cheap|gift|which .* should|عندكم|عايز|عاوز|محتاج|ارشحلي|رشحلي|3ayez|3awez|3andko",
    re.I,
)
UNKNOWN_PRODUCT = re.compile(
    r"(?:how much is|price of|do you have|do you sell|is) (?:the |a |an )?([A-Za-z][\w\- ]{2,30}?\d[\w\-]*)", re.I
)
NOT_CARRY = re.compile(r"do you (?:sell|have|carry) (?:any )?([a-z][a-z ]{2,30}?)(?:\?|$| in | for )", re.I)

POLICY_ROUTES = [
    (re.compile(r"price match|cheaper (?:elsewhere|somewhere)|match (?:the|a) price|competitor", re.I), "policy:price_match"),
    (
        re.compile(r"install?ments?|monthly payment|pay (?:over time|monthly)|valu\b|zero interest|0%", re.I),
        "policy:installments",
    ),
    (re.compile(r"warrant|guarantee|repair|nova care", re.I), "policy:warranty"),
    (re.compile(r"\breturn|refund|exchange|send (?:it )?back", re.I), "policy:returns"),
    (re.compile(r"payment|pay with|pay by|cash|visa|mastercard|meeza|fawry|instapay|apple pay|\bcard\b", re.I), "policy:payment"),
    (
        re.compile(r"ship|deliver|delivery|shipping|arrive|express|same.day|abroad|outside egypt|saudi|uae|kuwait", re.I),
        "policy:shipping",
    ),
    (re.compile(r"cancel|change (?:the |my )?(?:delivery )?address", re.I), "policy:orders"),
    (re.compile(r"gift card|voucher", re.I), "policy:gift_cards"),
    (re.compile(r"trade.?in|old phone|exchange my old", re.I), "policy:trade_in"),
    (re.compile(r"password|log ?in|account|sign up", re.I), "policy:account"),
    (re.compile(r"student (?:discount|offer)|university id|\.edu", re.I), "policy:student_offer"),
    (
        re.compile(
            r"hotline|phone number|contact|customer service|support|whatsapp|talk to (?:a )?(?:human|person|agent)|real person|agent",
            re.I,
        ),
        "support",
    ),
    (re.compile(r"branch|store|shop|showroom|location|address|where are you|open|close|hours|working hours", re.I), "branch"),
    (
        re.compile(r"original|genuine|fake|refurbished|used|click.?(?:and|&).?collect|pick ?up|friday|setup|data transfer", re.I),
        "faq",
    ),
]


@dataclass
class Reply:
    text: str
    tools: list = field(default_factory=list)
    products: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)
    intent: str = ""


def t(key, lang, **kw):
    return T[key][lang].format(**kw)


class LocalEngine:
    name = "local"

    def __init__(self, retriever=None):
        self.kb = get_knowledge()
        self.retriever = retriever

    # ---------- entry point ----------
    def reply(self, session, text):
        lang_in = session.language
        lang = reply_language(lang_in)
        norm = normalise_numbers(text)
        english = to_english_terms(norm)

        if is_injection(text):
            r = Reply(t("injection", lang), intent="injection")
            mentioned = self.kb.find_products_in_text(norm)
            if mentioned:
                p = self.kb.products[mentioned[0]]
                r.text += "\n\n" + (
                    f"For reference, the official price of the {p['name']} is {money(p['price'])}."
                    if lang == "en"
                    else f"وللعلم، السعر الرسمي لـ {p['name']} هو {money(p['price'], 'ar')}."
                )
            return r
        if is_gibberish(text):
            return Reply(t("clarify", lang), intent="gibberish", suggestions=self._default_suggestions(lang))

        remember(session, text)
        facts = session.facts

        if ASK_NAME.search(text):
            return Reply(t("name", lang, name=facts["name"]) if facts.get("name") else t("name_unknown", lang), intent="memory")
        if THANKS.search(text) and len(text.split()) <= 5:
            return Reply(t("thanks", lang), intent="thanks")
        if BYE.search(text) and len(text.split()) <= 4:
            return Reply(t("bye", lang), intent="bye")

        # Orders
        order = re.search(r"\bNV\s?-?(\d{5})\b", text, re.I)
        complaint = COMPLAINT.search(english)
        if not complaint and (order or (facts.get("awaiting_order") and re.fullmatch(r"\s*#?\s*\d{5}\s*", text))):
            facts.pop("awaiting_order", None)
            oid = "NV" + (order.group(1) if order else re.sub(r"\D", "", text))
            if is_injection(text):
                return Reply(t("injection", lang), intent="injection")
            return self._order(oid, lang)

        # Complaints (with contact details -> open a ticket) take priority over a plain order lookup
        if complaint:
            return self._complaint(text, english, lang)

        if (
            ORDER_WORDS.search(english)
            and re.search(
                r"where|status|track|when|arriv|update|late|yet|hasn't|didn't|فين|fein|feen|emta|امتى|وصل", english, re.I
            )
            and not self.kb.find_products_in_text(norm)
        ):
            facts["awaiting_order"] = True
            return Reply(t("ask_order", lang), intent="order_status")

        # Products named in the message (or referred to as "it"/"which one")
        mentioned = self.kb.find_products_in_text(norm)
        follow_up = not mentioned and PRONOUN.search(text) and facts.get("products")
        if follow_up:
            mentioned = (
                facts["products"][-2:] if COMPARE.search(english) and len(facts["products"]) >= 2 else facts["products"][-1:]
            )
        if len(mentioned) >= 2 and (COMPARE.search(english) or len(mentioned) == 2):
            return self._compare(mentioned[:3], english, lang)
        if mentioned:
            pid = mentioned[0]
            if ACCESSORY_Q.search(english):
                return self._accessories(pid, lang)
            if STOCK.search(english) or self.kb.branch_from_text(text):
                return self._stock(pid, self.kb.branch_from_text(text), lang)
            return self._product_info(pid, lang)

        if (GREETING.search(text) or IDENTITY.search(text)) and (len(text.split()) <= 6 or IDENTITY.search(text)):
            return Reply(t("greet", lang), intent="greeting", suggestions=self._default_suggestions(lang))

        # Product-like names we don't sell ("iPhone 16", "Nova X2")
        m = UNKNOWN_PRODUCT.search(text)
        if m and not tools.detect_category(m.group(1)) and not any(r.search(english) for r, _ in POLICY_ROUTES[:5]):
            return self._unknown_product(m.group(1).strip(), english, lang)

        # Policies, branches, FAQs
        policy = self._policy(english, text, lang)
        if policy and not (tools.detect_category(english) and SEARCHY.search(english)):
            return policy

        # Search / recommendation
        category = tools.detect_category(english)
        needs = tools.detect_needs(english)
        wants = SEARCHY.search(english) or re.search(r"recommend|what do you suggest|which should|ارشح|رشح", english, re.I)
        if category or needs or (wants and facts.get("category")):
            return self._search(english, category or (facts.get("category") if wants else None), needs, lang, session)
        m = NOT_CARRY.search(english)
        if m:
            return Reply(
                t("not_carry", lang, thing=m.group(1).strip()),
                intent="product_search",
                suggestions=self._default_suggestions(lang),
            )
        if wants:
            return Reply(t("need_clarify", lang), intent="clarify")
        if GREETING.search(text):
            return Reply(t("greet", lang), intent="greeting", suggestions=self._default_suggestions(lang))
        return Reply(t("offtopic", lang), intent="out_of_scope", suggestions=self._default_suggestions(lang))

    # ---------- handlers ----------
    def _order(self, oid, lang):
        r = tools.get_order_status(oid)
        rep = Reply("", tools=["get_order_status"], intent="order_status")
        if not r["found"]:
            rep.text = (
                f"I couldn't find order {r['order_id']}. Please double-check the number in your confirmation SMS/email, or call 16999 and we'll look into it."
                if lang == "en"
                else f"مالقتش الطلب {r['order_id']}. اتأكد من الرقم في رسالة التأكيد، أو كلّمنا على 16999 وهنشوفه."
            )
            return rep
        en, ar = STATUS[r["status"]]
        fields = {k: r.get(k, "") for k in ("carrier", "tracking", "eta", "delivered", "note", "branch")}
        items = ", ".join(r["items"])
        rep.text = (
            f"Order {r['order_id']} ({items}) {en.format(**fields)}."
            if lang == "en"
            else f"الطلب {r['order_id']} ({items}) {ar.format(**fields)}."
        )
        rep.suggestions = ["Talk to a human", "Return policy"] if lang == "en" else ["كلّم موظف", "سياسة الاسترجاع"]
        return rep

    def _complaint(self, text, english, lang):
        contact = CONTACT.search(text)
        is_fault = re.search(
            r"faulty|broken|stopped working|not working|doesn't work|defect|no sound|damaged|screen|عطلان|بايظ|مش شغال",
            english,
            re.I,
        )
        policy = self.kb.policies["warranty" if is_fault else "returns"]
        if contact:
            name = re.search(r"(?:my name is|i am|i'm|اسمي)\s+([A-Za-z؀-ۿ]+)", text, re.I)
            order = re.search(r"\bNV\s?-?(\d{5})\b", text, re.I)
            r = tools.create_support_ticket(
                issue=text,
                contact=contact.group(0),
                name=name.group(1) if name else None,
                order_id=("NV" + order.group(1)) if order else None,
                category="product_fault" if is_fault else "general",
            )
            msg = (
                f"I'm really sorry about this. I've opened complaint ticket {r['ticket_id']} and our team will contact you on {contact.group(0)} within 24 hours."
                if lang == "en"
                else f"آسفين جدًا على اللي حصل. فتحت لك شكوى برقم {r['ticket_id']} وفريقنا هيكلمك على {contact.group(0)} خلال 24 ساعة."
            )
            return Reply(msg, tools=["create_support_ticket"], intent="complaint")
        if lang == "en":
            first = self._best_sentences(policy["text"], english, 2)
            msg = (
                f"I'm really sorry about that. {first}\n\nIf you share your phone number or email I can open a ticket for our support team, "
                f"or call our hotline 16999."
            )
        else:
            msg = f"آسفين جدًا على كده. {policy['text_ar']}\n\nلو تبعتلي رقم موبايلك أو إيميلك أفتحلك تذكرة لفريق خدمة العملاء، أو كلّمنا على 16999."
        return Reply(
            msg,
            intent="complaint",
            suggestions=["Open a ticket", "Return policy"] if lang == "en" else ["افتح تذكرة", "سياسة الاسترجاع"],
        )

    def _line(self, card, lang, specs=2):
        spec = ", ".join(str(v) for v in list(card["key_specs"].values())[:specs])
        if lang == "en":
            stock = "in stock" if card["in_stock"] else f"out of stock (back {card.get('restock_date') or 'soon'})"
            return f"• **{card['name']}** — {money(card['price_egp'])} — {spec} — {stock}"
        stock = "متوفر" if card["in_stock"] else f"غير متوفر حاليًا (يرجع {card.get('restock_date') or 'قريب'})"
        return f"• **{card['name']}** — {money(card['price_egp'], 'ar')} — {spec} — {stock}"

    def _search(self, english, category, needs, lang, session):
        facts = session.facts
        budget = facts.get("budget")
        around = re.search(r"around|about|حوالي|تقريبا", english, re.I)
        max_price = int(budget * 1.1) if budget and around else budget
        query = " ".join([english] + facts.get("needs", []))
        res = tools.search_products(
            query=query,
            category=category,
            max_price=max_price,
            in_stock_only=bool(re.search(r"available now|in stock|متوفر", english, re.I)),
        )
        cards = res["results"][: 2 if "budget" in needs else 3]
        rep = Reply("", tools=["search_products"], products=cards, intent="product_search")
        if not cards:
            label = CATEGORY_LABELS.get(category, ("products", "منتجات"))
            rep.text = (
                f"I couldn't find {label[0]} within {money(max_price)}."
                if lang == "en" and max_price
                else f"I couldn't find matching {label[0]}."
                if lang == "en"
                else f"مالقتش {label[1]} في حدود {money(max_price, 'ar')}."
                if max_price
                else f"مالقتش {label[1]} مناسبة."
            )
            return rep
        remember_products(session, [c["id"] for c in cards])
        best = cards[0]
        lines = "\n".join(self._line(c, lang) for c in cards)
        if lang == "en":
            intro = f"Here's what I'd suggest{f' within {money(max_price)}' if max_price else ''}:"
            pick = f"My pick: the **{best['name']}**." + (
                " " + self._accessory_hint(best["id"], lang) if self._accessory_hint(best["id"], lang) else ""
            )
            rep.suggestions = [
                f"Compare {cards[0]['name']} and {cards[1]['name']}" if len(cards) > 1 else f"Is the {best['name']} in stock?",
                f"Accessories for {best['name']}",
            ]
        else:
            within = f" في حدود {money(max_price, 'ar')}" if max_price else ""
            intro = f"دي اقتراحاتي{within}:"
            pick = f"ترشيحي: **{best['name']}**."
            rep.suggestions = [f"قارن {cards[0]['name']} و {cards[1]['name']}" if len(cards) > 1 else f"{best['name']} متوفر؟"]
        rep.text = f"{intro}\n{lines}\n\n{pick}"
        return rep

    def _accessory_hint(self, pid, lang):
        p = self.kb.products[pid]
        if not p["accessories"]:
            return ""
        a = self.kb.products[p["accessories"][0]]
        return (
            f"Pairs well with the {a['name']} ({money(a['price'])})."
            if lang == "en"
            else f"وممكن معاه {a['name']} ({money(a['price'], 'ar')})."
        )

    def _product_info(self, pid, lang):
        card = tools.get_product(pid)
        specs = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in list(card["specs"].items())[:5])
        hint = self._accessory_hint(pid, lang)
        if lang == "en":
            stock = (
                "In stock" if card["in_stock"] else f"Currently out of stock — expected back {card.get('restock_date') or 'soon'}"
            )
            text = (
                f"The **{card['name']}** costs **{money(card['price_egp'])}**. {stock}. Warranty: {card['warranty_months']} months.\n"
                f"Key specs — {specs}." + (f"\n\n{hint}" if hint else "")
            )
            sugg = [f"Is the {card['name']} in stock in my branch?", f"Accessories for {card['name']}"]
        else:
            stock = "متوفر" if card["in_stock"] else f"غير متوفر حاليًا — متوقع يرجع {card.get('restock_date') or 'قريب'}"
            text = (
                f"سعر **{card['name']}** هو **{money(card['price_egp'], 'ar')}**. {stock}. الضمان {card['warranty_months']} شهر.\n"
                f"أهم المواصفات — {specs}." + (f"\n\n{hint}" if hint else "")
            )
            sugg = [f"{card['name']} متوفر؟"]
        return Reply(
            text,
            tools=["get_product"],
            products=[{k: v for k, v in card.items() if k != "recommended_accessories"}],
            intent="product_info",
            suggestions=sugg,
        )

    def _accessories(self, pid, lang):
        card = tools.get_product(pid)
        acc = card["recommended_accessories"]
        if not acc:
            text = (
                f"There are no specific accessories listed for the {card['name']}."
                if lang == "en"
                else f"مفيش إكسسوارات مخصوصة لـ {card['name']}."
            )
            return Reply(text, tools=["get_product"], intent="accessories")
        lines = "\n".join(self._line(a, lang, specs=1) for a in acc)
        text = (
            f"Accessories that go well with the **{card['name']}**:\n{lines}"
            if lang == "en"
            else f"إكسسوارات مناسبة لـ **{card['name']}**:\n{lines}"
        )
        return Reply(text, tools=["get_product"], products=acc, intent="accessories")

    def _stock(self, pid, branch, lang):
        r = tools.check_stock(pid, branch)
        name = r["name"]
        if lang == "en":
            if not r["in_stock_online"]:
                text = f"The **{name}** is currently out of stock" + (
                    f" — we expect it back on {r['restock_date']}." if r.get("restock_date") else "."
                )
                text += " I can suggest similar products in the meantime."
            elif r.get("requested_branch"):
                b = r["requested_branch"]
                text = (
                    f"Yes — the {b['branch']} branch has {b['units']} units of the **{name}** in stock right now."
                    if b["units"]
                    else f"The {b['branch']} branch has none right now, but the **{name}** is in stock online ({r['online_stock']} units) and at other branches."
                )
            else:
                text = (
                    f"Yes, the **{name}** is in stock — {r['online_stock']} units online. Branches: "
                    + ", ".join(f"{k.split(' — ')[0]} ({v})" for k, v in r["branches"].items())
                    + "."
                )
        else:
            if not r["in_stock_online"]:
                text = f"**{name}** غير متوفر حاليًا" + (
                    f" — متوقع يرجع يوم {r['restock_date']}." if r.get("restock_date") else "."
                )
            elif r.get("requested_branch"):
                b = r["requested_branch"]
                text = (
                    f"أيوه — {b['branch']} عنده {b['units']} قطع من **{name}** دلوقتي."
                    if b["units"]
                    else f"{b['branch']} مفيهوش دلوقتي، بس **{name}** متوفر أونلاين ({r['online_stock']} قطعة) وفي فروع تانية."
                )
            else:
                text = f"أيوه، **{name}** متوفر — {r['online_stock']} قطعة أونلاين."
        return Reply(text, tools=["check_stock"], intent="stock")

    def _compare(self, ids, english, lang):
        r = tools.compare_products(ids)
        ps = r["products"]
        keys = list(dict.fromkeys(k for p in ps for k in p["specs"]))[:6]
        header = " vs ".join(f"**{p['name']}** ({money(p['price_egp'], lang)})" for p in ps)
        rows = [f"• {k.replace('_', ' ')}: " + " | ".join(str(p["specs"].get(k, "—")) for p in ps) for k in keys]
        verdict = self._verdict(ps, english, lang)
        if lang == "en":
            text = f"{header}\n" + "\n".join(rows) + f"\n• price difference: {money(r['price_difference_egp'])}\n\n{verdict}"
        else:
            text = f"{header}\n" + "\n".join(rows) + f"\n• فرق السعر: {money(r['price_difference_egp'], 'ar')}\n\n{verdict}"
        cards = [tools._card(self.kb.products[p["id"]]) for p in ps]
        return Reply(text, tools=["compare_products"], products=cards, intent="comparison")

    def _verdict(self, ps, english, lang):
        def first_number(v):
            m = re.search(r"\d+(?:\.\d+)?", str(v))
            return float(m.group()) if m else 0

        if re.search(r"battery", english, re.I):
            best = max(ps, key=lambda p: first_number(p["specs"].get("battery", 0)))
            return (
                f"The **{best['name']}** has the longer battery life ({best['specs'].get('battery')})."
                if lang == "en"
                else f"**{best['name']}** بطاريته أطول ({best['specs'].get('battery')})."
            )
        if re.search(r"cheap|budget|price|أرخص|ارخص", english, re.I):
            best = min(ps, key=lambda p: p["price_egp"])
            return f"The **{best['name']}** is the cheaper option." if lang == "en" else f"**{best['name']}** أرخص."
        for need in ("gaming", "students", "fitness", "travel", "noise cancelling", "camera", "creator"):
            if need in tools.detect_needs(english):
                fits = [p for p in ps if need in " ".join(p["good_for"])]
                if fits:
                    best = fits[0]
                    break
        else:
            best = None
        if best is None and re.search(r"run|gps|outdoor", english, re.I):
            best = next((p for p in ps if "dual-band" in str(p["specs"].get("gps", ""))), None)
        if best is None and re.search(r"gaming|game|console", english, re.I):
            best = max(
                ps,
                key=lambda p: (
                    first_number(re.search(r"(\d+)\s*hz", str(p["specs"]), re.I).group(1))
                    if re.search(r"(\d+)\s*hz", str(p["specs"]), re.I)
                    else 0
                ),
            )
        if best is None and re.search(r"student|university|college|budget", english, re.I):
            best = min(ps, key=lambda p: p["price_egp"])
        if best is None:
            cheap = min(ps, key=lambda p: p["price_egp"])
            pricey = max(ps, key=lambda p: p["price_egp"])
            return (
                f"Pick the **{pricey['name']}** if you want the higher-end specs, or save {money(pricey['price_egp'] - cheap['price_egp'])} with the **{cheap['name']}**."
                if lang == "en"
                else f"لو عايز مواصفات أعلى خد **{pricey['name']}**، ولو عايز توفر {money(pricey['price_egp'] - cheap['price_egp'], 'ar')} خد **{cheap['name']}**."
            )
        return (
            f"For what you described, I'd go with the **{best['name']}**."
            if lang == "en"
            else f"للي إنت محتاجه، أنا أرشح **{best['name']}**."
        )

    def _unknown_product(self, thing, english, lang):
        text = t("unknown_product", lang, thing=thing)
        category = tools.detect_category(english) or (
            "phone" if re.search(r"iphone|galaxy|pixel|xiaomi|nova|orbit", thing, re.I) else None
        )
        rep = Reply(text, intent="unknown_product")
        if category:
            res = tools.search_products(query="", category=category)
            cards = res["results"][:2]
            if cards:
                rep.tools = ["search_products"]
                rep.products = cards
                rep.text += ("\n\nSimilar options we carry:\n" if lang == "en" else "\n\nبدائل متوفرة عندنا:\n") + "\n".join(
                    self._line(c, lang) for c in cards
                )
        return rep

    def _policy(self, english, raw, lang):
        doc_id = next((d for r, d in POLICY_ROUTES if r.search(english)), None)
        if doc_id is None:
            return None
        docs = {d.id: d for d in self.kb.documents}
        if doc_id == "branch":
            bid = self.kb.branch_from_text(raw)
            if bid:
                doc = docs[f"branch:{bid}"]
            else:
                lines = [
                    f"• {b['name']} — {b['hours']}" if lang == "en" else f"• {b['name_ar']} — {b['hours_ar']}"
                    for b in self.kb.branches.values()
                ]
                return Reply(
                    ("We have 4 branches:\n" if lang == "en" else "عندنا 4 فروع:\n") + "\n".join(lines), intent="branches"
                )
        elif doc_id == "faq":
            hits = self.retriever.search(english, k=1, kinds={"faq"}) if self.retriever else []
            if not hits:
                return None
            doc = hits[0]["doc"]
        else:
            doc = docs[doc_id]
        if lang == "ar" and doc.text_ar:
            text = doc.text_ar
        elif doc.kind == "faq":
            text = doc.text[len(doc.title) :].strip()
        elif doc.kind == "branch":
            text = doc.text
        else:
            text = self._best_sentences(doc.text, english, 2)
        return Reply(text, intent="policy", suggestions=self._policy_suggestions(doc.id, lang))

    @staticmethod
    def _best_sentences(text, query, n):
        sentences = re.split(r"(?<=[.!?])\s+", text)
        words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}
        stems = {w[:5] for w in words}

        def score(s):
            sw = set(re.findall(r"[a-z0-9]+", s.lower()))
            return sum(1 for w in sw if w in words or w[:5] in stems)

        ranked = sorted(range(len(sentences)), key=lambda i: (-score(sentences[i]), i))
        chosen = sorted(ranked[:n]) if score(sentences[ranked[0]]) > 0 else list(range(min(n, len(sentences))))
        return " ".join(sentences[i] for i in chosen)

    @staticmethod
    def _policy_suggestions(doc_id, lang):
        en = {
            "policy:shipping": ["Payment methods", "Return policy"],
            "policy:returns": ["Warranty", "Talk to a human"],
            "policy:warranty": ["Return policy", "Branches"],
            "policy:payment": ["Installments", "Delivery time"],
            "policy:installments": ["Payment methods", "Laptops under 30000 EGP"],
        }
        ar = {
            "policy:shipping": ["طرق الدفع", "سياسة الاسترجاع"],
            "policy:returns": ["الضمان", "كلّم موظف"],
            "policy:payment": ["التقسيط", "مدة التوصيل"],
        }
        return (en if lang == "en" else ar).get(doc_id, [])

    @staticmethod
    def _default_suggestions(lang):
        return (
            ["Noise cancelling headphones", "Laptops under 30000 EGP", "Track my order"]
            if lang == "en"
            else ["سماعات بعزل ضوضاء", "لابتوب للجامعة", "تتبع طلبي"]
        )
