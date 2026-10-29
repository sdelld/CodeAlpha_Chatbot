"""Chatbot evaluation runner.

    python tests/eval/run_eval.py --engine legacy --label baseline        # the v1 bot, before changes
    python tests/eval/run_eval.py --engine auto   --label after           # v2: Gemini if GEMINI_API_KEY is set, else local
    python tests/eval/run_eval.py --engine local  --label after-local
    python tests/eval/run_eval.py --compare baseline after                # writes the comparison into report.md

Each case is checked automatically (expected facts, forbidden content, expected tool call, reply language).
With a Gemini key, an LLM judge also scores accuracy / helpfulness / tone / language match from 1 to 5.
Outputs: tests/eval/reports/<label>.json|.md, and tests/eval/report.json|.md for the latest run.
"""

import argparse
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

REPORTS = HERE / "reports"
ARABIC = re.compile(r"[؀-ۿ]")
INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalise(text):
    text = (text or "").translate(INDIC).lower()
    text = re.sub(r"(?<=\d)[,٬’'  ](?=\d{3})", "", text)  # 42,999 -> 42999
    text = text.replace("–", "-").replace("—", "-").replace("‑", "-")
    return re.sub(r"\s+", " ", text)


def check_case(case, result):
    reply = normalise(result["reply"])
    missing = []
    for fact in case["expected_facts"]:
        options = fact if isinstance(fact, list) else [fact]
        if not any(normalise(o) in reply for o in options):
            missing.append(" | ".join(options))
    forbidden = [f for f in case["must_not_contain"] if normalise(f) in reply]
    tool_ok = case.get("expected_tool") is None or case["expected_tool"] in result.get("tools", [])
    raw = result["reply"] or ""
    arabic_chars = len(ARABIC.findall(raw))
    latin_chars = len(re.findall(r"[A-Za-z]", raw))
    if case["language"] == "ar":
        lang_ok = arabic_chars > 0
    elif case["language"] == "en":
        lang_ok = arabic_chars <= latin_chars * 0.2
    else:
        lang_ok = bool(raw.strip())
    passed = not missing and not forbidden and tool_ok and lang_ok
    return {"passed": passed, "missing_facts": missing, "forbidden_found": forbidden, "tool_ok": tool_ok,
            "language_ok": lang_ok}


# ---------------- engines ----------------

class LegacyEngine:
    """Adapter for the v1 intent-classifier bot (kept in legacy/ for reproducible baselines)."""

    name = "legacy-v1"

    def __init__(self):
        try:
            from legacy.bot_v1 import ChatBot
        except ImportError:
            from bot import ChatBot  # before the v1 code was moved
        self.bot = ChatBot(seed=0)

    def new_session(self):
        return {"context": None}

    def respond(self, session, text):
        t0 = time.perf_counter()
        r = self.bot.reply(text, context=session["context"])
        session["context"] = r.get("context")
        ms = (time.perf_counter() - t0) * 1000
        tools = ["get_order_status"] if r.get("intent") == "order_lookup" else []
        return {"reply": r["reply"], "tools": tools, "ttft_ms": ms, "latency_ms": ms, "tokens_in": 0,
                "tokens_out": 0, "cost_usd": 0.0, "engine": self.name}


class V2Engine:
    def __init__(self, mode):
        from nova.assistant import Assistant
        self.assistant = Assistant.create(mode=mode)
        self.name = self.assistant.engine_name

    def new_session(self):
        return self.assistant.sessions.new()

    def respond(self, session, text):
        return self.assistant.respond(session, text)


def make_engine(kind):
    return LegacyEngine() if kind == "legacy" else V2Engine(kind)


# ---------------- LLM judge ----------------

JUDGE_PROMPT = """You grade replies from "Nova", the customer-support chatbot of Nova Electronics, an electronics store in Egypt.
Score each criterion from 1 (very poor) to 5 (excellent):
- accuracy: consistent with the expected facts; no invented products, prices, stock or policies.
- helpfulness: answers the question and moves the customer forward (asks one clarifying question only if needed).
- tone: friendly, concise, professional; stays on topic; refuses unsafe/off-topic requests politely.
- language_match: replies in the customer's language (English, Egyptian Arabic, or Arabic for Arabizi input).

Category: {category}
Customer language: {language}
Earlier customer turns: {context}
Customer message: {input}
Facts the reply should contain: {facts}
Things the reply must not say: {forbidden}

Bot reply:
\"\"\"{reply}\"\"\"

Answer with JSON only: {{"accuracy": n, "helpfulness": n, "tone": n, "language_match": n, "comment": "<one sentence>"}}"""


class Judge:
    def __init__(self):
        from nova.llm import GeminiClient
        self.client = GeminiClient.from_env(model_env="GEMINI_JUDGE_MODEL")

    def score(self, case, reply):
        prompt = JUDGE_PROMPT.format(category=case["category"], language=case["language"],
                                     context=case["context"] or "none", input=case["input"],
                                     facts=case["expected_facts"] or "none", forbidden=case["must_not_contain"] or "none",
                                     reply=reply)
        out = self.client.generate_json(prompt)
        return {k: out.get(k) for k in ("accuracy", "helpfulness", "tone", "language_match", "comment")}


# ---------------- run ----------------

def percentile(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def run(engine_kind, label, use_judge, only=None, delay=0.0):
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))["cases"]
    if only:
        cases = [c for c in cases if c["id"] in only or c["category"] in only]
    engine = make_engine(engine_kind)
    judge = None
    if use_judge:
        try:
            judge = Judge()
        except Exception as e:  # no key / SDK missing
            print(f"(LLM judge disabled: {e})")
    results = []
    for i, case in enumerate(cases, 1):
        session = engine.new_session()
        for turn in case["context"]:
            engine.respond(session, turn)
            time.sleep(delay)
        r = engine.respond(session, case["input"])
        check = check_case(case, r)
        row = {"id": case["id"], "category": case["category"], "language": case["language"], "input": case["input"],
               "reply": r["reply"], "tools": r.get("tools", []), "latency_ms": round(r["latency_ms"], 1),
               "ttft_ms": round(r.get("ttft_ms", r["latency_ms"]), 1), "tokens_in": r.get("tokens_in", 0),
               "tokens_out": r.get("tokens_out", 0), "cost_usd": r.get("cost_usd", 0.0), "engine": r.get("engine"),
               **check}
        if judge:
            try:
                row["judge"] = judge.score(case, r["reply"])
            except Exception as e:
                row["judge"] = {"error": str(e)[:200]}
        results.append(row)
        print(f"[{i:>2}/{len(cases)}] {'PASS' if check['passed'] else 'FAIL'} {case['id']:<9} {r['latency_ms']:>7.0f} ms  "
              f"{(r['reply'] or '').replace(chr(10), ' ')[:90]}")
        time.sleep(delay)
    summary = summarise(results, engine.name, label)
    REPORTS.mkdir(exist_ok=True)
    payload = {"summary": summary, "results": results}
    (REPORTS / f"{label}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md = render_markdown(summary, results)
    (REPORTS / f"{label}.md").write_text(md, encoding="utf-8")
    (HERE / "report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (HERE / "report.md").write_text(md, encoding="utf-8")
    print(f"\n{summary['passed']}/{summary['total']} passed ({summary['pass_rate']:.1%}) · "
          f"p50 {summary['latency_p50_ms']:.0f} ms · p95 {summary['latency_p95_ms']:.0f} ms · "
          f"tokens {summary['tokens_in']}/{summary['tokens_out']} · ${summary['cost_usd']:.4f}")
    return payload


def summarise(results, engine_name, label):
    by_cat = defaultdict(lambda: [0, 0])
    for r in results:
        by_cat[r["category"]][1] += 1
        by_cat[r["category"]][0] += r["passed"]
    lat = [r["latency_ms"] for r in results]
    ttft = [r["ttft_ms"] for r in results]
    judged = [r["judge"] for r in results if isinstance(r.get("judge"), dict) and "accuracy" in r["judge"]]
    judge_avg = {}
    for k in ("accuracy", "helpfulness", "tone", "language_match"):
        vals = [j[k] for j in judged if isinstance(j.get(k), int | float)]
        judge_avg[k] = round(statistics.mean(vals), 2) if vals else None
    n = len(results)
    return {
        "label": label, "engine": engine_name, "run_at": time.strftime("%Y-%m-%d %H:%M"), "total": n,
        "passed": sum(r["passed"] for r in results), "pass_rate": sum(r["passed"] for r in results) / n if n else 0,
        "by_category": {k: {"passed": v[0], "total": v[1], "rate": v[0] / v[1]} for k, v in sorted(by_cat.items())},
        "facts_ok_rate": sum(not r["missing_facts"] for r in results) / n if n else 0,
        "tool_ok_rate": sum(r["tool_ok"] for r in results) / n if n else 0,
        "language_ok_rate": sum(r["language_ok"] for r in results) / n if n else 0,
        "latency_p50_ms": percentile(lat, .5), "latency_p95_ms": percentile(lat, .95),
        "ttft_p50_ms": percentile(ttft, .5), "ttft_p95_ms": percentile(ttft, .95),
        "tokens_in": sum(r["tokens_in"] for r in results), "tokens_out": sum(r["tokens_out"] for r in results),
        "cost_usd": round(sum(r["cost_usd"] for r in results), 6),
        "cost_per_conversation_usd": round(sum(r["cost_usd"] for r in results) / n, 6) if n else 0,
        "judge": judge_avg, "judged_cases": len(judged),
    }


def render_markdown(s, results):
    lines = [f"# Chatbot evaluation — {s['label']}", "",
             f"Engine **{s['engine']}** · {s['run_at']} · {s['total']} cases", "",
             "| Metric | Value |", "|---|---|",
             f"| Pass rate | **{s['pass_rate']:.1%}** ({s['passed']}/{s['total']}) |",
             f"| Expected facts present | {s['facts_ok_rate']:.1%} |",
             f"| Correct tool called | {s['tool_ok_rate']:.1%} |",
             f"| Language match | {s['language_ok_rate']:.1%} |",
             f"| Latency p50 / p95 | {s['latency_p50_ms']:.0f} ms / {s['latency_p95_ms']:.0f} ms |",
             f"| Time to first token p50 / p95 | {s['ttft_p50_ms']:.0f} ms / {s['ttft_p95_ms']:.0f} ms |",
             f"| Tokens in / out | {s['tokens_in']:,} / {s['tokens_out']:,} |",
             f"| Est. cost (paid-tier prices) | ${s['cost_usd']:.4f} total · ${s['cost_per_conversation_usd']:.5f} per conversation |"]
    if s["judged_cases"]:
        j = s["judge"]
        lines.append(f"| LLM judge (1-5): accuracy / helpfulness / tone / language | {j['accuracy']} / {j['helpfulness']} / "
                     f"{j['tone']} / {j['language_match']} ({s['judged_cases']} cases) |")
    lines += ["", "## Pass rate by category", "", "| Category | Passed | Rate |", "|---|---|---|"]
    lines += [f"| {k} | {v['passed']}/{v['total']} | {v['rate']:.0%} |" for k, v in s["by_category"].items()]
    failing = [r for r in results if not r["passed"]]
    lines += ["", f"## Failing cases ({len(failing)})", ""]
    if not failing:
        lines.append("None.")
    for r in failing:
        why = []
        if r["missing_facts"]:
            why.append("missing: " + "; ".join(r["missing_facts"]))
        if r["forbidden_found"]:
            why.append("forbidden: " + ", ".join(r["forbidden_found"]))
        if not r["tool_ok"]:
            why.append(f"tool not called (got {r['tools'] or 'none'})")
        if not r["language_ok"]:
            why.append("wrong language")
        reply = (r["reply"] or "").replace("\n", " ")[:220]
        lines.append(f"- **{r['id']}** ({r['category']}) `{r['input']}` — {' · '.join(why)}  \n  > {reply}")
    return "\n".join(lines) + "\n"


def compare(labels):
    runs = [json.loads((REPORTS / f"{lab}.json").read_text(encoding="utf-8"))["summary"] for lab in labels]
    head = "| Metric | " + " | ".join(f"{r['label']} ({r['engine']})" for r in runs) + " |"
    rows = [head, "|---|" + "---|" * len(runs)]

    def row(name, fn):
        rows.append(f"| {name} | " + " | ".join(fn(r) for r in runs) + " |")

    row("Pass rate", lambda r: f"**{r['pass_rate']:.1%}**")
    row("Expected facts present", lambda r: f"{r['facts_ok_rate']:.1%}")
    row("Correct tool called", lambda r: f"{r['tool_ok_rate']:.1%}")
    row("Language match", lambda r: f"{r['language_ok_rate']:.1%}")
    row("Latency p50 / p95", lambda r: f"{r['latency_p50_ms']:.0f} / {r['latency_p95_ms']:.0f} ms")
    row("TTFT p50", lambda r: f"{r['ttft_p50_ms']:.0f} ms")
    row("Tokens in / out", lambda r: f"{r['tokens_in']:,} / {r['tokens_out']:,}")
    row("Cost per conversation", lambda r: f"${r['cost_per_conversation_usd']:.5f}")
    row("LLM judge accuracy", lambda r: str(r["judge"].get("accuracy") or "—"))
    cats = sorted({c for r in runs for c in r["by_category"]})
    for c in cats:
        row(f"· {c}", lambda r, c=c: f"{r['by_category'][c]['passed']}/{r['by_category'][c]['total']}"
            if c in r["by_category"] else "—")
    table = "\n".join(rows)
    report = HERE / "report.md"
    body = report.read_text(encoding="utf-8") if report.exists() else ""
    body = re.sub(r"\n## Before vs after\n.*?(?=\n## |\Z)", "\n", body, flags=re.S)
    body = body.replace("\n## Pass rate by category", f"\n## Before vs after\n\n{table}\n\n## Pass rate by category", 1)
    report.write_text(body, encoding="utf-8")
    print(table)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="auto", choices=["legacy", "auto", "local", "gemini"])
    ap.add_argument("--label", default=None)
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--only", nargs="*", help="case ids or categories")
    ap.add_argument("--delay", type=float, default=0.0, help="seconds between requests (free-tier rate limits)")
    ap.add_argument("--compare", nargs="+", metavar="LABEL")
    a = ap.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    if a.compare:
        compare(a.compare)
    else:
        run(a.engine, a.label or a.engine, use_judge=not a.no_judge and a.engine != "legacy", only=a.only, delay=a.delay)
