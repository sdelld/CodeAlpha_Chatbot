"""Guards: prompt-injection detection, gibberish detection, and a price-grounding check on model output."""

import re

from .lang import ARABIC, INDIC

INJECTION = re.compile(
    r"ignore (?:all |your |the |any )?(?:previous |prior |above )?(?:instructions|rules|prompt)|disregard (?:your|the|all)"
    r"|system prompt|your (?:instructions|prompt|rules) (?:word|verbatim)|print your|reveal your|developer mode"
    r"|you are now|act as (?:an? )?(?:ai|dan|unrestricted)|\bdan\b|jailbreak|no restrictions|admin override"
    r"|^\s*system\s*:|\[system\]|<\s*system\s*>|pretend (?:you are|to be)"
    r"|تجاهل (?:كل )?(?:التعليمات|القواعد)|التعليمات (?:اللي|التي) عندك|انسى التعليمات|اكتب لي التعليمات",
    re.I | re.M,
)

PRICE_NEAR_CURRENCY = re.compile(r"(\d[\d,٬]*)\s*(?:egp|le\b|l\.e|pounds?|جنيه|ج\.م)|(?:egp|جنيه)\s*(\d[\d,٬]*)", re.I)


def is_injection(text):
    return bool(INJECTION.search(text or ""))


def is_gibberish(text):
    t = (text or "").strip()
    if not t:
        return True
    if re.search(r"\d{3,}", t):
        return False  # order numbers, prices, phone numbers
    letters = re.findall(r"[A-Za-z؀-ۿ]", t)
    if not letters:
        return True  # only symbols / emoji / punctuation
    if ARABIC.search(t):
        return False
    words = re.findall(r"[a-z]+", t.lower())
    if not words:
        return True
    vowelless = sum(1 for w in words if len(w) >= 4 and not re.search(r"[aeiouy]", w))
    consonant_runs = sum(1 for w in words if re.search(r"[bcdfghjklmnpqrstvwxz]{5,}", w))
    return (vowelless + consonant_runs) >= max(1, len(words) // 2 + (len(words) > 2))


def ungrounded_prices(reply, allowed):
    """Money amounts in the reply that don't exist in the store data / tool results (likely hallucinated)."""
    bad = []
    for m in PRICE_NEAR_CURRENCY.finditer((reply or "").translate(INDIC)):
        raw = (m.group(1) or m.group(2)).replace(",", "").replace("٬", "")
        if raw.isdigit():
            value = int(raw)
            if value >= 100 and value not in allowed:
                bad.append(value)
    return bad
