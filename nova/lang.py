"""Language handling: English, Egyptian Arabic and Arabizi (Arabic written in Latin letters + digits)."""

import re

ARABIC = re.compile(r"[؀-ۿ]")
INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

# Common Egyptian Arabizi words; digits inside words (3, 2, 7, 5, 8) are the strongest signal.
ARABIZI_WORDS = {
    "ezayak",
    "ezayek",
    "izayak",
    "ahlan",
    "3ayez",
    "3ayza",
    "3awez",
    "3ayzeen",
    "momken",
    "mumkin",
    "b",
    "bkam",
    "bekam",
    "kam",
    "fein",
    "fen",
    "feen",
    "fi",
    "fih",
    "fiha",
    "mesh",
    "msh",
    "mish",
    "ana",
    "enta",
    "enty",
    "eh",
    "eih",
    "leh",
    "a2sat",
    "a2asat",
    "ta2seet",
    "ta2set",
    "sama3a",
    "sama3at",
    "mobile",
    "el",
    "law",
    "3andko",
    "3ndko",
    "3ando",
    "keda",
    "kda",
    "tamam",
    "shokran",
    "shukran",
    "ya",
    "ba2a",
    "7aga",
    "7elw",
    "ghaly",
    "rekhis",
    "ra5is",
    "3ala",
    "ma3a",
    "ma3aya",
    "talab",
    "talaby",
    "ordery",
    "wesel",
    "wasal",
    "emta",
    "imta",
    "delwa2ty",
    "naharda",
    "bokra",
    "salam",
    "sabah",
    "masa2",
    "el5er",
    "elkheir",
    "elfol",
    "wala",
    "walla",
    "aw",
    "a7san",
    "afdal",
    "garanty",
    "daman",
}
ARABIZI_DIGIT = re.compile(r"[a-z][2357689]|[2357689][a-z]")

# Arabic / Arabizi shopping vocabulary -> English search terms (used by retrieval and the local engine).
GLOSSARY = {
    "سماعة": "headphones",
    "سماعات": "headphones",
    "هيدفون": "headphones",
    "ايربودز": "earbuds",
    "sama3a": "headphones",
    "sama3at": "headphones",
    "عزل": "noise cancelling",
    "ضوضاء": "noise cancelling",
    "الضوضاء": "noise cancelling",
    "لابتوب": "laptop",
    "لاب": "laptop",
    "لابتوبات": "laptop",
    "كمبيوتر": "laptop",
    "laptob": "laptop",
    "lab": "laptop",
    "موبايل": "phone",
    "موبايلات": "phone",
    "تليفون": "phone",
    "فون": "phone",
    "mobile": "phone",
    "mobil": "phone",
    "تابلت": "tablet",
    "ايباد": "tablet",
    "ساعة": "smartwatch",
    "ساعات": "smartwatch",
    "شاشة": "tv",
    "تلفزيون": "tv",
    "بلايستيشن": "console",
    "جيمنج": "gaming",
    "العاب": "gaming",
    "ألعاب": "gaming",
    "شاحن": "charger",
    "جراب": "case",
    "باور": "power bank",
    "كاميرا": "camera",
    "بطارية": "battery",
    "battaria": "battery",
    "سعر": "price",
    "بكام": "price",
    "بكم": "price",
    "b kam": "price",
    "bkam": "price",
    "kam": "price",
    "متوفر": "in stock",
    "موجود": "in stock",
    "mawgood": "in stock",
    "متاح": "in stock",
    "استرجاع": "return",
    "الاسترجاع": "return",
    "ترجيع": "return",
    "استبدال": "exchange",
    "رجع": "return",
    "ضمان": "warranty",
    "الضمان": "warranty",
    "daman": "warranty",
    "garanty": "warranty",
    "شحن": "shipping",
    "الشحن": "shipping",
    "توصيل": "delivery",
    "التوصيل": "delivery",
    "tawseel": "delivery",
    "قسط": "installments",
    "تقسيط": "installments",
    "اقساط": "installments",
    "أقساط": "installments",
    "a2sat": "installments",
    "a2asat": "installments",
    "ta2seet": "installments",
    "ta2set": "installments",
    "دفع": "payment",
    "الدفع": "payment",
    "فيزا": "card",
    "كاش": "cash on delivery",
    "فرع": "branch",
    "فروع": "branch",
    "عنوان": "address",
    "مواعيد": "hours",
    "طلب": "order",
    "طلبي": "order",
    "اوردر": "order",
    "ordery": "order",
    "talaby": "order",
    "شكوى": "complaint",
    "مشكلة": "problem",
    "طالب": "student",
    "جامعة": "university",
    "للجامعة": "university student",
    "طفل": "kids",
    "اطفال": "kids",
    "عيال": "kids",
    "جري": "running",
    "رياضة": "fitness",
    "هدية": "gift",
    "رخيص": "cheap",
    "ارخص": "cheap",
    "rekhis": "cheap",
    "غالي": "premium",
    "احسن": "best",
    "أحسن": "best",
    "a7san": "best",
    "مقارنة": "compare",
    "ولا": "vs",
    "wala": "vs",
    "walla": "vs",
    "الفرق": "difference",
    "اسكندرية": "alexandria",
    "إسكندرية": "alexandria",
    "لإسكندرية": "alexandria",
    "للإسكندرية": "alexandria",
    "الإسكندرية": "alexandria",
    "المعادي": "maadi",
    "زايد": "zayed",
    "السعودية": "saudi arabia",
    "برا": "abroad",
    "مصر": "egypt",
}


def detect(text):
    """'ar' if Arabic script dominates, 'arabizi' if Latin Egyptian chat, else 'en'."""
    if not text:
        return "en"
    if ARABIC.search(text):
        return "ar"
    words = re.findall(r"[a-z0-9]+", text.lower())
    if not words:
        return "en"
    hits = sum(
        1 for w in words if w in ARABIZI_WORDS or ARABIZI_DIGIT.search(w) and not re.fullmatch(r"nv\d+|\d+[a-z]{1,2}|[a-z]\d+", w)
    )
    return "arabizi" if hits >= max(1, len(words) // 3) else "en"


def reply_language(lang):
    """Arabizi users get Egyptian Arabic replies (clearer than replying in Arabizi)."""
    return "ar" if lang in ("ar", "arabizi") else "en"


def normalise_numbers(text):
    """Arabic-Indic digits -> 0-9; '25 ألف', '25k', '25 alf' -> 25000; remove thousands separators."""
    t = text.translate(INDIC)
    t = re.sub(r"(?<=\d)[,٬](?=\d{3})", "", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s*(?:ألف|الف|آلاف|الاف|alf|k)\b", lambda m: str(int(float(m.group(1)) * 1000)), t, flags=re.I)
    return t


def to_english_terms(text):
    """Append English equivalents of Arabic/Arabizi shopping words so keyword search works in any language."""
    low = text.lower()
    extra = []
    for word, eng in GLOSSARY.items():
        if (ARABIC.search(word) and word in low) or re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", low):
            extra.append(eng)
    return text if not extra else f"{text} {' '.join(dict.fromkeys(extra))}"
